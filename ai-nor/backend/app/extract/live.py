"""Live extraction: one LLM call per case collects every mention of every NOR field (value + verbatim quote),
the backend verifies quotes, normalises values to NOR codes, detects conflicts and scores confidence.

PLAN.md §3 (steps 4-8), §3.1 (code selection), §4 (confidence 0-100).
"""

import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from app import llm
from app.extract.evidence import locate
from app.models import (
    TNM,
    Coding,
    DiagnosisBasis,
    Document,
    Evidence,
    Extracted,
    FieldStatus,
    Laterality,
    MetastasisSite,
    NorReport,
    PartialDate,
)
from app.validate import mkn10, normalize

FieldName = Literal[
    "diagnosis_date", "icd10", "laterality", "morphology_type", "morphology", "grade",
    "cT", "cN", "cM", "pT", "pN", "pM", "lymph_nodes", "sentinel_node", "clinical_stage",
    "metastasis_sites", "disease_extent",
]


class Mention(BaseModel):
    doc: int  # document number as numbered in the prompt
    quote: str  # verbatim, short (max ~15 words)
    value: str  # value as written
    explicit: bool  # stated directly (False = inferred / computed)
    hedged: bool  # "susp.", "v.s.", "nelze vyloučit", "?"


class FieldMentions(BaseModel):
    field: FieldName
    mentions: list[Mention]


class LlmExtraction(BaseModel):
    primary_tumour: str  # short description of the tumour being reported
    other_tumours: list[str]  # other / historical cancers (onkoduplicita) - not reported here
    patient_sex: Literal["M", "F", "unknown"]
    fields: list[FieldMentions]


SYSTEM = """Jsi asistent onkologického registru (NOR, ÚZIS). Z české zdravotnické dokumentace jednoho pacienta vypíšeš
VŠECHNY zmínky údajů pro hlášení „Incidence zhoubného novotvaru“ pro JEDEN hlášený nádor (aktuální primární zhoubný novotvar).

Pole (field):
- diagnosis_date: datum stanovení diagnózy (první histologické / cytologické potvrzení; jinak datum vyšetření nebo zahájení léčby)
- icd10: diagnóza MKN-10 hlášeného nádoru (kód, pokud je uveden, např. C50.4 / C504; jinak slovní diagnóza)
- laterality: strana (vpravo / vlevo / oboustranně / odpadá u nepárového orgánu)
- morphology_type: Histologie nebo Cytologie (podle toho, čím byl nádor ověřen)
- morphology: histologický typ nádoru; pokud je v textu kód morfologie (např. „M1: M81403“ nebo 8140/3), uveď ho ve value
- grade: grading (G1–G4, GX, slovně „středně diferencovaný“, high/low grade, Gleason)
- cT, cN, cM: KLINICKÉ TNM (z vyšetření, zobrazení, MDT před operací)
- pT, pN, pM: PATOLOGICKÉ TNM z histologie resekátu, včetně prefixu y po neoadjuvanci (value jak je psáno, např. „ypT3“)
- lymph_nodes: počet vyšetřených a pozitivních uzlin, jak je psáno (např. „24/19“, „0/14“)
- sentinel_node: výsledek sentinelové uzliny
- clinical_stage: klinické stádium (I–IV, FIGO …)
- metastasis_sites: vzdálené metastázy při diagnóze (orgány); value „žádné“, pokud je výslovně uvedeno, že nejsou
- disease_extent: rozsah onemocnění (lokalizované / pokročilé)

Pravidla:
1. quote = DOSLOVNÁ krátká citace z dokumentu (max ~15 slov), přesně jak je napsaná, aby šla v textu najít.
2. Vypiš všechny zmínky ze všech dokumentů, i když se opakují nebo si odporují – rozpory řeší lékař.
3. Negace: „bez známek meta“ znamená žádné metastázy, ne metastázy. Suspekce („susp.“, „v.s.“, „?“) označ hedged=true.
4. Klinické a patologické TNM nikdy nezaměňuj. Stádium nebo rozsah, které sám odvodíš, označ explicit=false.
5. Starší jiný nádor (onkoduplicita) do polí nepatří – uveď ho jen v other_tumours.
6. Nic si nevymýšlej. Údaj, který v dokumentaci není, vynech (pole bez zmínek nevracej).
7. Klinická diagnóza na žádance před histologií (např. J38.3) není diagnóza nádoru."""

SOURCE_RANK = {"histology": 70, "MDT": 60, "operation": 55, "PZ": 50, "AZ": 50, "other": 45}

_SITES = [
    (r"plic", MetastasisSite.lung), (r"kostn[íi] d[řr]e[ňn]", MetastasisSite.bone_marrow), (r"kost|skelet|obratl", MetastasisSite.bone),
    (r"pleur", MetastasisSite.pleura), (r"jater|játr|hepat", MetastasisSite.liver), (r"periton|karcinomat", MetastasisSite.peritoneum),
    (r"mozk|mozeč|cerebr", MetastasisSite.brain), (r"nadledvin|adrenal", MetastasisSite.adrenal), (r"uzlin|\blu\b", MetastasisSite.lymph_nodes),
    (r"kůž|kož", MetastasisSite.skin),
]


def _prompt(docs: list[Document]) -> str:
    parts = [f"### Dokument {i} (typ: {d.kind}, soubor: {d.filename})\n{d.text}" for i, d in enumerate(docs, 1)]
    return "\n\n".join(parts)


class _M:
    """A verified, normalised mention."""

    def __init__(self, doc: Document, ev: Evidence | None, raw: Mention, value):
        self.doc, self.ev, self.raw, self.value = doc, ev, raw, value


def _collect(out: LlmExtraction, docs: list[Document]) -> dict[str, list[tuple[Document, Evidence | None, Mention]]]:
    by_field: dict[str, list] = defaultdict(list)
    for fm in out.fields:
        for m in fm.mentions:
            if 1 <= m.doc <= len(docs):
                doc = docs[m.doc - 1]
                by_field[fm.field].append((doc, locate(doc, m.quote), m))
    return by_field


def _score(winners: list[_M], *, code_valid: bool | None = None, code_path: str | None = None) -> tuple[int, list[str]]:
    reasons = []
    verified = [w for w in winners if w.ev and w.ev.verified]
    best = max(winners, key=lambda w: SOURCE_RANK.get(w.doc.kind or "other", 45))
    score = SOURCE_RANK.get(best.doc.kind or "other", 45)
    reasons.append(f"zdroj: {best.doc.kind}")
    docs = {w.doc.id for w in verified}
    if len(docs) > 1:
        bonus = min(10 * (len(docs) - 1), 20)
        score += bonus
        reasons.append(f"✓ {len(docs)} dokumenty se shodují (+{bonus})")
    if code_path == "literal":
        score += 10
        reasons.append("✓ kód přímo v textu (+10)")
    elif code_path == "semantic":
        score -= 15
        reasons.append("kód dohledán v číselníku podle názvu (−15)")
    elif code_path == "rules":
        score -= 5
        reasons.append("kód zvolen podle pravidel MKN-10, v textu není (−5)")
    if code_valid:
        score += 10
        reasons.append("✓ kód platný v číselníku (+10)")
    elif code_valid is False:
        score = min(score, 40)
        reasons.append("✗ kód není v číselníku")
    if not any(w.raw.explicit for w in winners):
        score -= 15
        reasons.append("odvozeno, není výslovně v textu (−15)")
    if all(w.raw.hedged for w in winners):
        score -= 30
        reasons.append("nejisté vyjádření v textu (−30)")
    if verified:
        reasons.insert(0, "✓ citace ověřena")
    else:
        score = min(score, 30)
        reasons.insert(0, "✗ citaci se nepodařilo v dokumentu najít")
    return max(0, min(100, score)), reasons


def _field(mentions: list[_M], to_display=str, merge_contained: bool = False, **score_kw) -> Extracted:
    """Pick the winning value, detect conflicts, score. `mentions` already carry normalised values."""
    mentions = [m for m in mentions if m.value is not None]
    if not mentions:
        return Extracted()
    groups: dict[str, list[_M]] = defaultdict(list)
    for m in mentions:
        key = to_display(m.value)
        if merge_contained:  # free text: "karcinom NST" and "karcinom NST prsu" are the same finding
            low = key.lower()
            key = next((k for k in groups if low in k.lower() or k.lower() in low), key)
        groups[key].append(m)
    ranked = sorted(
        groups.values(),
        key=lambda g: (max(SOURCE_RANK.get(m.doc.kind or "other", 45) for m in g), len({m.doc.id for m in g})),
        reverse=True,
    )
    winners = ranked[0]
    score, reasons = _score(winners, **score_kw)
    verified_groups = [g for g in ranked if any(m.ev and m.ev.verified for m in g)]
    conflict = len(verified_groups) > 1
    if conflict:
        reasons.append(f"⚠ rozpor: {len(verified_groups)} různé hodnoty v dokumentech")
    evidence = [m.ev for g in ranked for m in g if m.ev and m.ev.verified]
    return Extracted(
        value=winners[0].value,
        status=FieldStatus.conflict if conflict else FieldStatus.found,
        confidence=score,
        confidence_reasons=reasons,
        evidence=evidence,
        alternatives=[g[0].value for g in ranked[1:]],
    )


def _normalised(items, fn) -> list[_M]:
    out = []
    for doc, ev, m in items:
        v = fn(m.value)
        if v is None:
            v = fn(m.quote)
        out.append(_M(doc, ev, m, v))
    return out


_SITE_SENTENCE = re.compile(r"[^.\n]{0,80}(?:\b(?:kvadrant\w*|lalok\w*|lokalizac\w*|ulo[žz]en\w*|rozhran\w*)|(?-i:\b(?:[HD][ZVK]|[ZV][HDK])K\b))[^.\n]{0,80}", re.IGNORECASE)  # breast quadrant abbreviations (HZK, DKK…), not "dkk" = lower limbs


def _apply_coder(r: NorReport, out: "LlmExtraction", f) -> None:
    """Second step: MKN-10 code chosen with the coding rules (app/extract/coder.py)."""
    from app.extract.coder import choose_icd10

    if not f["icd10"] and not r.icd10.value:
        return
    quotes = [m.quote for _, _, m in f["icd10"]] + [m.quote for _, _, m in f["morphology"]][:3]
    quotes += [m.quote for _, _, m in f["laterality"]][:2]
    # the sub-code depends on the exact site (quadrant, lobe...), which the code quotes often leave out
    docs = list({id(d): d for items in f.values() for d, _, _ in items}.values())
    for d in docs:
        for m in _SITE_SENTENCE.finditer(d.text):
            if (q := " ".join(m.group(0).split())) not in quotes and len(quotes) < 12:
                quotes.append(q)
    literal = r.icd10.value if (r.icd10.value and r.icd10.confidence_reasons and any("přímo v textu" in x for x in r.icd10.confidence_reasons)) else None
    try:
        res = choose_icd10(out.primary_tumour, quotes, literal)
    except Exception as e:  # IRIS / LLM down: keep the first-step result, say so
        r.icd10.confidence_reasons.append(f"pravidla MKN-10 nepoužita ({type(e).__name__})")
        return
    if not res or not res.code:
        if r.icd10.value:
            r.icd10.confidence_reasons.append("pravidla MKN-10: kód nelze jednoznačně určit")
        return
    rule_txt = f"„{res.rule.quote}“ (MKN-10 {res.rule.code}, str. {res.rule.page})" if res.rule else ""
    if not res.valid:
        r.icd10.confidence_reasons.append(f"pravidla MKN-10 navrhla {res.code}, kód ale nelze ověřit")
        return
    if r.icd10.value == res.code:
        r.icd10.confidence = min(100, (r.icd10.confidence or 0) + 10)
        r.icd10.confidence_reasons.append(f"✓ kód potvrzen pravidly MKN-10 (+10) {rule_txt}")
    elif literal and mkn10.is_valid(literal):
        # documents say one code, the rules another -> the clinician decides
        r.icd10.alternatives = [res.code] + [a for a in r.icd10.alternatives if a != res.code]
        r.icd10.confidence = min(r.icd10.confidence or 0, 70)
        r.icd10.confidence_reasons.append(f"⚠ pravidla MKN-10 navrhují {res.code}: {res.reasoning} {rule_txt}")
    elif literal:  # code from the documents does not exist in MKN-10-CZ
        r.icd10.alternatives = [res.code] + [a for a in r.icd10.alternatives if a != res.code]
        r.icd10.confidence_reasons.append(f"návrh podle pravidel MKN-10: {res.code} – {res.reasoning} {rule_txt}")
    else:
        # no code written in the documents (the first step only matched a name in the code list):
        # the rules-based code wins, the name match stays as an alternative (goes to review via the score)
        source = f["icd10"] or f["morphology"]
        if not source:
            r.icd10.confidence_reasons.append(f"pravidla MKN-10 navrhují {res.code}, chybí citace z dokumentace")
            return
        previous = r.icd10.value
        doc, ev, m = source[0]
        r.icd10 = _field([_M(doc, ev, m, res.code)], code_valid=True, code_path="rules")
        if previous and previous != res.code:
            r.icd10.alternatives = [previous]
        r.icd10.confidence_reasons.append(f"{res.reasoning} {rule_txt}")
    if res.rule:
        r.icd10.rules = [res.rule]
    if not res.certain:
        r.icd10.confidence = min(r.icd10.confidence or 0, 70)
        r.icd10.confidence_reasons.append("pravidla MKN-10: model si volbou není jistý")


def extract_live(docs: list[Document]) -> tuple[NorReport, list[str], LlmExtraction]:
    out = llm.structured(SYSTEM, _prompt(docs), LlmExtraction)
    f = _collect(out, docs)
    r = NorReport()
    warnings: list[str] = []

    # --- diagnosis (MKN-10), topography
    icd_ms = _normalised(f["icd10"], normalize.icd10)
    literal = [m for m in icd_ms if m.value]
    if literal:
        r.icd10 = _field(literal, code_valid=all(mkn10.is_valid(m.value) is not False for m in literal) or False, code_path="literal")
    elif f["icd10"]:
        from app.retrieval.codes import MKN10, search_codes

        doc, ev, m = f["icd10"][0]
        hits = search_codes(MKN10, m.value, 1)
        if hits:
            r.icd10 = _field([_M(doc, ev, m, hits[0].code)], code_valid=True, code_path="semantic")
    _apply_coder(r, out, f)
    if r.icd10.value and mkn10.is_valid(r.icd10.value) is False:
        parent = r.icd10.value[:-1].rstrip(".")
        if mkn10.is_valid(parent):
            r.icd10.alternatives = [parent] + [a for a in r.icd10.alternatives if a != parent]
            r.icd10.confidence_reasons.append(f"návrh: {parent} ({r.icd10.value} v MKN-10-CZ neexistuje)")
    if r.icd10.value:
        r.icd10.coding = Coding(system=mkn10.ICD10_SYSTEM, code=r.icd10.value, display=mkn10.lookup(r.icd10.value))
        if re.match(r"C[0-7]\d", r.icd10.value):  # ICD-O topography C00-C80 mirrors MKN-10
            r.topography = r.icd10.model_copy(deep=True)
            r.topography.confidence = max(0, (r.topography.confidence or 0) - 5)
            r.topography.confidence_reasons = r.topography.confidence_reasons + ["topografie převzata z kódu MKN-10 (−5)"]
            r.topography.coding = None

    # --- date, laterality
    r.diagnosis_date = _field(_normalised(f["diagnosis_date"], normalize.partial_date),
                              to_display=lambda d: f"{d.year}-{d.month or 0:02d}-{d.day or 0:02d}")
    r.laterality = _field(_normalised(f["laterality"], normalize.laterality), to_display=lambda v: v.value)

    # --- morphology
    r.morphology_type = _field(_normalised(f["morphology_type"], lambda v: "Cytologie" if "cyto" in v.lower() else ("Histologie" if "histo" in v.lower() else None)))
    morph_items = f["morphology"]
    names = [_M(doc, ev, m, re.sub(r"\(?M?-?\d{4}\s?/?\s?\d\)?", "", m.value).strip(" :,-") or None) for doc, ev, m in morph_items]
    r.morphology_name = _field(names, merge_contained=True)
    codes = _normalised(morph_items, normalize.morphology)
    codes = [c for c in codes if c.value]
    if codes:
        r.morphology_code = _field(codes, code_valid=True, code_path="literal")
    elif r.morphology_name.value:
        from app.retrieval.codes import MORPHOLOGY, search_codes

        hits = search_codes(MORPHOLOGY, r.morphology_name.value, 5)
        if hits:
            doc, ev, m = morph_items[0]
            path = "index" if hits[0].exact else "semantic"
            r.morphology_code = _field([_M(doc, ev, m, hits[0].code)], code_valid=True, code_path=path)
            if hits[0].exact:
                r.morphology_code.confidence_reasons.append(f"✓ přesná shoda názvu s číselníkem: {hits[0].name}")
            r.morphology_code.alternatives = [h.code for h in hits[1:]]
            r.morphology_code.confidence_reasons.append("kandidáti: " + ", ".join(f"{h.code} {h.name[:30]}" for h in hits))

    r.grade = _field(_normalised(f["grade"], lambda v: normalize.grade(v) or normalize.high_grade(v)))

    # --- TNM
    for prefix, tnm in (("c", r.tnm_clinical), ("p", r.tnm_pathological)):
        for part in ("T", "N", "M"):
            items = f[f"{prefix}{part}"]
            setattr(tnm, part.lower(), _field(_normalised(items, lambda v, p=part: normalize.tnm(v, p))))
            if prefix == "p" and any(normalize.y_prefix(m.value) for _, _, m in items):
                tnm.y_prefix = True

    # --- lymph nodes, sentinel, stage, metastases, extent
    nodes = _normalised(f["lymph_nodes"], normalize.lymph_nodes)
    r.pn_examined = _field([_M(n.doc, n.ev, n.raw, n.value[0] if n.value else None) for n in nodes])
    r.pn_positive = _field([_M(n.doc, n.ev, n.raw, n.value[1] if n.value else None) for n in nodes])
    r.sentinel_node = _field(_normalised(f["sentinel_node"], normalize.sentinel))
    r.clinical_stage = _field(_normalised(f["clinical_stage"], lambda v: (m.group(1).upper() if (m := re.search(r"\b((?:IV|III|II|I)[ABC]?)\b", v)) else None)))

    def sites(v: str):
        t = v.lower()
        if re.search(r"žádn|bez|nejsou|neprokáz|negat", t):
            return ()
        found = tuple(sorted({s for p, s in _SITES if re.search(p, t)}, key=lambda s: s.value))
        return found or None

    met = _field(_normalised(f["metastasis_sites"], sites), to_display=lambda v: ",".join(str(s.value) for s in v))
    if met.value is not None:
        met.value = list(met.value)
        met.alternatives = [list(a) for a in met.alternatives]
    r.metastasis_sites = met
    r.disease_extent = _field(_normalised(f["disease_extent"], normalize.disease_extent))
    if r.disease_extent.status == FieldStatus.missing:
        # derive from TNM (never auto: explicit=False keeps it below the threshold -> review)
        m_values = [x.value for x in (r.tnm_pathological.m, r.tnm_clinical.m) if x.value]
        src = r.tnm_pathological.m if r.tnm_pathological.m.value else r.tnm_clinical.m
        if m_values and src.evidence:
            extent = "2" if any(v.startswith("1") for v in m_values) or r.metastasis_sites.value else "1"
            r.disease_extent = Extracted[str](
                value=extent,
                status=FieldStatus.found,
                confidence=60,
                confidence_reasons=[f"odvozeno z M{m_values[0]}: {'pokročilé' if extent == '2' else 'lokalizované'} (−15)", "není výslovně v textu"],
                evidence=src.evidence[:1],
            )

    # --- derived: K dg. vedla vyšetření
    if any(d.kind == "histology" for d in docs) and r.morphology_name.value:
        hist = next(d for d in docs if d.kind == "histology")
        hist_ids = {d.id for d in docs if d.kind == "histology"}
        from_hist = any(e.verified and e.doc_id in hist_ids for e in r.morphology_name.evidence + r.morphology_code.evidence)
        r.diagnosis_basis = Extracted[list[DiagnosisBasis]](
            value=[DiagnosisBasis.clinical_exam, DiagnosisBasis.histology_primary],
            status=FieldStatus.found,
            confidence=88 if from_hist else 70,
            confidence_reasons=[
                "odvozeno: histologie primárního nádoru v dokumentaci (01 + 16 = 17)",
                "✓ morfologie ověřena citací z histologie" if from_hist else "histologie bez ověřené citace morfologie",
            ],
            evidence=r.morphology_name.evidence[:1] or [Evidence(doc_id=hist.id, quote=hist.text[:40], start=0, end=min(40, len(hist.text)), verified=True)],
        )

    # --- case-level warnings
    if out.other_tumours:
        warnings.append("Další (starší) nádor v dokumentaci, nehlásí se zde: " + "; ".join(out.other_tumours))
    # sex vs. diagnosis and birth-number checks: app/validate/rodne_cislo.case_checks (run by extract())
    # _field builds untyped Extracted; re-validate into the typed report
    r = NorReport.model_validate_json(r.model_dump_json(warnings=False))
    return r, warnings, out
