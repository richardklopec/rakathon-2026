"""Live extraction: one LLM call per case collects every mention of every NOR field (value + verbatim quote),
the backend verifies quotes, normalises values to NOR codes, detects conflicts and scores confidence.

PLAN.md §3 (steps 4-8), §3.1 (code selection), §4 (confidence 0-100).
"""

import re
import unicodedata
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from app import llm
from app.extract import derive, nodes
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
    TreatmentEvent,
)
from app.confidence import cap
from app.validate import mkn10, normalize, site, staging

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

SOURCE_RANK = {"histology": 70, "MDT": 60, "operation": 55, "PZ": 50, "AZ": 50, "other": 45, "requisition": 45}
SOURCE_LABEL = {"requisition": "žádanka k histologii (klinická dg.)"}

# Histology reports start with the requisition (průvodní list: "Klinická diagnóza", "KLIN. DIAG.", "DIAGNÓZA: C509")
# written by the clinician before the biopsy; the pathologist's findings start at the first of these headings.
_FINDINGS = re.compile(r"(?im)^\s*(?:NÁLEZ|Makropopis|Mikropopis|Závěr|ZÁVĚR|Bioptick\w* nález|Histologick\w* nález)\b")
_REQUISITION_LINE = re.compile(r"(?i)klinick\w*\s+(?:dg|diag)|klin\.\s*diag|žádank|průvodní list")


def _is_requisition(doc: Document, ev: Evidence | None, quote: str) -> bool:
    """Is this mention from the requisition part of a histology report (the clinician's text, not the pathologist's)?"""
    if doc.kind != "histology":
        return False
    if _REQUISITION_LINE.search(quote):
        return True
    if not (ev and ev.verified):
        return False
    line_start = doc.text.rfind("\n", 0, ev.start) + 1
    line_end = doc.text.find("\n", ev.end)
    if _REQUISITION_LINE.search(doc.text[line_start:line_end if line_end >= 0 else None]):
        return True
    findings = _FINDINGS.search(doc.text)
    return bool(findings) and ev.start < findings.start()

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

    def __init__(self, doc: Document, ev: Evidence | None, raw: Mention, value, kind: str | None = None):
        self.doc, self.ev, self.raw, self.value = doc, ev, raw, value
        self.kind = kind or doc.kind or "other"

    @property
    def rank(self) -> int:
        return SOURCE_RANK.get(self.kind, 45)

    @property
    def source(self) -> str:
        """Agreement counts independent sources: all requisitions are one (the clinician's pre-biopsy diagnosis)."""
        return "requisition" if self.kind == "requisition" else self.doc.id


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
    best = max(winners, key=lambda w: w.rank)
    score = best.rank
    reasons.append(f"zdroj: {SOURCE_LABEL.get(best.kind, best.kind)}")
    sources = {w.source for w in verified}
    if len(sources) > 1:
        bonus = min(10 * (len(sources) - 1), 20)
        score += bonus
        reasons.append(f"✓ {len(sources)} nezávislé zdroje se shodují (+{bonus})")
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


# free-text names: word synonyms and words that do not change the finding, for grouping equivalent names
_NAME_SYNONYMS = {"infiltrujici": "invazivni", "infiltrativni": "invazivni", "ca": "karcinom", "carcinoma": "karcinom"}
_NAME_NOISE = {"a", "s", "se", "prsu", "sin", "dx", "vlevo", "vpravo", "l", "typ", "nadoru"}


def _name_tokens(name: str) -> frozenset[str]:
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c)).lower()
    return frozenset(_NAME_SYNONYMS.get(w, w) for w in re.findall(r"[a-z0-9]+", folded)) - _NAME_NOISE


def _field(mentions: list[_M], to_display=str, merge_contained: bool = False, **score_kw) -> Extracted:
    """Pick the winning value, detect conflicts, score. `mentions` already carry normalised values."""
    mentions = [m for m in mentions if m.value is not None]
    if not mentions:
        return Extracted()
    groups: dict[str, list[_M]] = defaultdict(list)
    for m in mentions:
        key = to_display(m.value)
        if merge_contained:
            # free text: one name containing the other is the same finding ("karcinom NST" / "karcinom NST prsu",
            # "karcinom lobulární infiltrující" / "invazivní lobulární karcinom + LCIS"), word order and synonyms aside
            tokens = _name_tokens(key)
            key = next((k for k in groups if tokens <= _name_tokens(k) or _name_tokens(k) <= tokens), key)
        groups[key].append(m)
    ranked = sorted(groups.values(), key=lambda g: (max(m.rank for m in g), len({m.source for m in g})), reverse=True)
    winners = ranked[0]
    score, reasons = _score(winners, **score_kw)
    verified_groups = [g for g in ranked if any(m.ev and m.ev.verified for m in g)]
    conflict = len(verified_groups) > 1
    if conflict:
        reasons.append(f"⚠ rozpor: {len(verified_groups)} různé hodnoty v dokumentech")
    evidence = [m.ev for g in ranked for m in g if m.ev and m.ev.verified]
    # merged free text: the most complete wording from the most trusted source ("… karcinom + LCIS", not "… karcinom")
    best = max(winners, key=lambda m: (m.rank, len(_name_tokens(str(m.value))))) if merge_contained else winners[0]
    return Extracted(
        value=best.value,
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


_PAIR_ONLY = re.compile(r"\(?\s*\d{1,3}\s*/\s*\d{1,3}\s*\)?")


def _is_fragment(doc: Document, ev: Evidence | None, quote: str) -> bool:
    """A node count taken from a fragment of the PDF layout: the "(2/0)" alone on its line or with no node words around
    (page markers "1/1", a pair placed next to an unrelated sentence)."""
    if not re.search(r"\d\s*/\s*\d", quote):
        return False
    if _PAIR_ONLY.fullmatch(quote.strip()):
        return True
    if ev and ev.verified:
        s, e = doc.text.rfind("\n", 0, ev.start) + 1, doc.text.find("\n", ev.end)
        line = doc.text[s:e if e >= 0 else None]
        return not re.search(r"(?i)uzlin(?!k)|\bLU\b|\bSLN\b|sentinel|\bN\d", line)
    return False


def _node_field(res: "nodes.NodeResult", which: str, warnings: list[str]) -> Extracted | None:
    """pN vyš. / pN poz. from the specimen counts: histology base 70, −5 for a sum of several specimens, +10 for each
    outpatient / MDT summary that agrees (max +20); a summary that disagrees makes it a conflict (review)."""
    value = res.examined if which == "examined" else res.positive
    if value is None:
        return None
    specs = res.specimens
    score, reasons = 70, ["✓ citace ověřena", "zdroj: histologie, počet podle vzorků"]
    if len(specs) > 1:
        score -= 5
        reasons.append("součet vzorků: " + " + ".join(c.label() for c in specs) + " (−5)")
    sval = (lambda s: s.examined) if which == "examined" else (lambda s: s.positive)
    agree = {s.doc.id: s for s in res.summaries if sval(s) == value}
    if agree:
        bonus = min(10 * len(agree), 20)
        score += bonus
        reasons.append(f"✓ souhrn souhlasí: {', '.join(s.doc.filename for s in agree.values())} (+{bonus})")
    others = sorted({sval(s) for s in res.summaries if sval(s) != value and sval(s) is not None})
    if others:
        reasons.append(f"⚠ souhrn uvádí {', '.join(map(str, others))}")
    field = Extracted[int](
        value=value,
        status=FieldStatus.conflict if others else FieldStatus.found,
        confidence=min(score, 100),
        confidence_reasons=reasons,
        evidence=[c.evidence for c in specs] + [s.evidence for s in agree.values()],
        alternatives=others,
    )
    if which == "examined" and (bad := [r for r in res.references if r.examined not in {c.examined for c in specs} | {value}]):
        cap(field, 70, f"⚠ odkaz v jiné zprávě uvádí {', '.join(r.label() for r in bad)}")
    return field


_CODE_FOOTER = re.compile(r"\bM\d\s*:\s*M?-?\d{4}\s?/?\s?\d")  # "M1: M85203" in the histology footer


def _clean_name(value: str) -> str | None:
    """Morphology name without the code and without leftover punctuation ("– karcinom …", "… karcinom;")."""
    name = re.sub(r"\(?M?-?\d{4}\s?/?\s?\d\)?", "", value)
    name = re.sub(r"\s+", " ", name).strip(" :,;.-–—")
    return name or None


CLINICAL_M_CAP = 75  # a clinical M from the documents always goes to review (M0 is never accepted automatically)


def _clinical_m(r: NorReport, docs: list[Document]) -> None:
    """cM from an explicit TNM string ("pT1c N0(0/3) M0") or, as derived, from negative staging; never from silence."""
    cm = r.tnm_clinical.m
    if cm.status != FieldStatus.missing and cm.value not in (None, "X"):
        return  # the LLM found a clinical M; the consistency checks compare it with the rest
    explicit = [h for h in derive.explicit_m(docs) if h.value in ("0", "1")]
    staging = derive.negative_staging(docs)
    if explicit:
        values = sorted({h.value for h in explicit})
        value = "1" if "1" in values else "0"
        hits = [h for h in explicit if h.value == value]
        sources = {h.doc.id for h in hits}
        score = max(SOURCE_RANK.get(h.doc.kind or "other", 45) for h in hits) + min(10 * (len(sources) - 1), 20)
        reasons = ["✓ citace ověřena", f"M{value} výslovně v TNM ({', '.join(dict.fromkeys(h.doc.filename for h in hits))})"]
        evidence = [h.evidence for h in hits]
        if value == "0" and staging:
            score += 10
            reasons.append(f"✓ staging bez vzdálených metastáz ({', '.join(dict.fromkeys(h.doc.filename for h in staging))}, +10)")
            evidence += [h.evidence for h in staging[:2]]
        others = [v for v in values if v != value] + (["X"] if cm.value == "X" else [])
        field = Extracted[str](value=value, status=FieldStatus.conflict if others else FieldStatus.found,
                               confidence=score, confidence_reasons=reasons, evidence=evidence, alternatives=others)
    elif staging and cm.status == FieldStatus.missing:
        field = Extracted[str](
            value="0", status=FieldStatus.found, confidence=60, evidence=[h.evidence for h in staging[:2]],
            confidence_reasons=["✓ citace ověřena", "odvozeno z negativního stagingu: "
                                + "; ".join(h.evidence.quote for h in staging[:2]), "M0 není výslovně uvedeno"],
        )
    else:
        return
    cap(field, CLINICAL_M_CAP, "klinické M vždy ke kontrole")
    r.tnm_clinical.m = field


def _derive_stage(r: NorReport) -> None:
    """Anatomic stage from TNM (validate/staging.py, UICC TNM 8): pT/pN before cT/cN, M from cM (or pM1)."""
    if r.tnm_pathological.y_prefix:
        return  # ypTNM after neoadjuvant therapy is not the stage at diagnosis
    pick = lambda p, c: p if p.value and p.status != FieldStatus.missing else c  # noqa: E731
    t = pick(r.tnm_pathological.t, r.tnm_clinical.t)
    n = pick(r.tnm_pathological.n, r.tnm_clinical.n)
    m = r.tnm_clinical.m if r.tnm_clinical.m.value else r.tnm_pathological.m
    if m is r.tnm_pathological.m and not str(m.value or "").startswith("1"):
        return  # only pM1 says something; pMX / pM0 are not stage inputs
    value = staging.stage((r.icd10.value or "")[:3], t.value, n.value, m.value)
    if not value:
        return
    inputs = [x for x in (t, n, m) if x.value is not None]
    tp = "p" if t is r.tnm_pathological.t else "c"
    np = "p" if n is r.tnm_pathological.n else "c"
    how = f"{tp}T{t.value} + {np}N{n.value} + {'c' if m is r.tnm_clinical.m else 'p'}M{m.value} → {value} (UICC TNM 8)"
    derived_conf = max(0, min(x.confidence or 0 for x in inputs) - 5)
    cs = r.clinical_stage
    if cs.value is None or cs.status == FieldStatus.missing:
        r.clinical_stage = Extracted[str](
            value=value, status=FieldStatus.found, confidence=derived_conf,
            confidence_reasons=["✓ citace ověřena", f"odvozeno: {how}", "jistota = nejnižší jistota vstupů −5"],
            evidence=[x.evidence[0] for x in inputs if x.evidence],
        )
    elif str(cs.value).upper() == value:
        cs.confidence = max(cs.confidence or 0, derived_conf)
        cs.confidence_reasons.append(f"✓ odpovídá TNM: {how}")
    else:
        cs.status = FieldStatus.conflict
        cs.alternatives = [value] + [a for a in cs.alternatives if a != value]
        cs.confidence_reasons.append(f"⚠ podle TNM vychází {value}: {how}")


def _diagnosis_date_fallback(r: NorReport, docs: list[Document]) -> None:
    """Form: "není-li známo, uvést datum vyšetření nebo zahájení léčby". Biopsy date first, then the start of treatment;
    both derived and for review. The start of treatment also goes to report.treatments (consistency: dg ≤ treatment)."""
    biopsy, treatment = derive.first_biopsy(docs), derive.first_treatment(docs)
    if treatment:
        r.treatments.append(TreatmentEvent(
            kind=treatment.kind,
            start=Extracted[PartialDate](value=treatment.value, status=FieldStatus.found, confidence=70,
                                         confidence_reasons=["✓ citace ověřena", "datum u výkonu / léčby"],
                                         evidence=[treatment.evidence]),
        ))
    fallback = biopsy or treatment
    if not fallback:
        return
    label = "datum biopsie (histologické ověření)" if fallback is biopsy else f"datum zahájení léčby ({fallback.kind})"
    dg = r.diagnosis_date
    if dg.status == FieldStatus.missing:
        r.diagnosis_date = Extracted[PartialDate](
            value=fallback.value, status=FieldStatus.found, confidence=65 if fallback is biopsy else 60,
            confidence_reasons=["✓ citace ověřena", f"odvozeno: {label} – datum stanovení dg. v dokumentaci není",
                                "formulář NOR: není-li známo, datum vyšetření nebo zahájení léčby"],
            evidence=[fallback.evidence],
        )
        return
    # a stated date that is less precise (only the year) or later than the biopsy / treatment: offer the derived one
    d, f = dg.value, fallback.value
    vague = d.day is None and d.year == f.year and (d.month is None or d.month == f.month)
    later = (d.year, d.month or 12, d.day or 31) > (f.year, f.month or 1, f.day or 1)
    if (vague or later) and f not in dg.alternatives:
        dg.alternatives = [f] + dg.alternatives
        dg.confidence_reasons.append(f"návrh: {label} {f.day}. {f.month}. {f.year}")


def _codes_in_docs(mentions: list[_M]) -> list[str]:
    """Distinct MKN-10 codes written in the documents with their sources: ["C50.4 (AZ.pdf)", "C50.9 (H1.pdf – žádanka)"]."""
    by_code: dict[str, list[str]] = {}
    for m in mentions:
        if m.value and m.ev and m.ev.verified:
            src = m.doc.filename + (" – žádanka" if m.kind == "requisition" else "")
            if src not in by_code.setdefault(m.value, []):
                by_code[m.value].append(src)
    return [f"{code} ({', '.join(srcs)})" for code, srcs in by_code.items()]


def _check_site(r: NorReport, docs: list[Document], warnings: list[str]) -> None:
    """Deterministic second opinion on the subsite (validate/site.py): the code must match the described site."""
    if not r.icd10.value:
        return
    code = r.icd10.value
    cat = code[:3]
    fit, found = site.check(code, docs)
    if len(found) > 1:
        warnings.append("Popis lokalizace nádoru se v dokumentech liší: "
                        + "; ".join(f"{site.label(cat, s)} → {cat}{s} ({', '.join(files)})" for s, files in found.items()) + ".")
    if fit is False:
        described = [f"{cat}{s}" for s in found if mkn10.is_valid(f"{cat}{s}") is not False]
        cap(r.icd10, 60, f"✗ popis lokalizace v dokumentech ({', '.join(f'{c} {site.label(cat, c[3:])}' for c in described)}) "
                         f"neodpovídá kódu {code}")
        r.icd10.alternatives = described + [a for a in r.icd10.alternatives if a not in described and a != code]
    elif fit:
        sub = code[3:]
        r.icd10.confidence_reasons.append(f"✓ popis lokalizace odpovídá: {site.label(cat, sub)} ({', '.join(found[sub])})")


def _apply_coder(r: NorReport, out: "LlmExtraction", f, docs_all: list[Document], codes_in_docs: list[str]) -> None:
    """Second step: MKN-10 code chosen with the coding rules (app/extract/coder.py)."""
    from app.extract.coder import choose_icd10

    if not f["icd10"] and not r.icd10.value:
        return
    # the sub-code depends on the described site: those lines go first, so the 12-quote limit never cuts them off
    categories = {c[:3] for c in [r.icd10.value or "", *(x.split(" ")[0] for x in codes_in_docs)] if c}
    quotes = list(dict.fromkeys(e.quote for c in sorted(categories) for e in site.descriptions(c, docs_all)))[:4]
    quotes += [m.quote for _, _, m in f["icd10"]] + [m.quote for _, _, m in f["morphology"]][:3]
    quotes += [m.quote for _, _, m in f["laterality"]][:2]
    # the sub-code depends on the exact site (quadrant, lobe...), which the code quotes often leave out
    docs = list({id(d): d for items in f.values() for d, _, _ in items}.values())
    for d in docs:
        for m in _SITE_SENTENCE.finditer(d.text):
            if (q := " ".join(m.group(0).split())) not in quotes and len(quotes) < 12:
                quotes.append(q)
    literal = r.icd10.value if (r.icd10.value and r.icd10.confidence_reasons and any("přímo v textu" in x for x in r.icd10.confidence_reasons)) else None
    try:
        res = choose_icd10(out.primary_tumour, quotes, literal, codes_in_docs=codes_in_docs)
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
    unsupported = f"✗ citované pravidlo kód {res.code} nepodporuje {rule_txt}"
    if r.icd10.value == res.code:
        if res.supports is False:  # the code is right only if the rule says so, not because the rule exists
            cap(r.icd10, 60, unsupported)
        else:
            r.icd10.confidence = min(100, (r.icd10.confidence or 0) + 10)
            r.icd10.confidence_reasons.append(f"✓ kód potvrzen pravidly MKN-10 (+10) {rule_txt}")
    elif (literal and mkn10.is_valid(literal) and len(codes_in_docs) > 1 and res.supports is not False
          and site.check(res.code, docs_all)[0] is True and site.check(literal, docs_all)[0] is not True):
        # the documents disagree among themselves and only the rules' code matches the described site: it leads,
        # the written codes stay as alternatives and the field goes to review (conflict)
        previous = r.icd10.value
        r.icd10.value = res.code
        r.icd10.status = FieldStatus.conflict
        r.icd10.evidence = site.evidence(res.code, docs_all) + r.icd10.evidence
        r.icd10.alternatives = [previous] + [a for a in r.icd10.alternatives if a not in (previous, res.code)]
        r.icd10.confidence = min(r.icd10.confidence or 0, 60)
        r.icd10.confidence_reasons = [
            "✓ citace ověřena",
            f"⚠ dokumenty uvádějí různé kódy: {'; '.join(codes_in_docs)}",
            f"kód zvolen podle pravidel MKN-10 a popisu lokalizace: {res.reasoning} {rule_txt}",
        ]
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
    if res.supports is False and r.icd10.value != res.code:
        r.icd10.confidence_reasons.append(f"(návrh pravidel {res.code} se o citované pravidlo neopírá)")
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
    # a code counts as written in the documents only when the quote contains it; a code the model put in `value` for
    # a diagnosis in words ("Ca prsu vlevo" -> C50.9) is its own guess and goes through the name / rules path instead
    icd_ms = [_M(doc, ev, m, normalize.icd10(m.quote)) for doc, ev, m in f["icd10"]]
    for m in icd_ms:  # a code on a biopsy requisition is the clinician's diagnosis before histology, not the pathologist's
        if _is_requisition(m.doc, m.ev, m.raw.quote):
            m.kind = "requisition"
    literal = [m for m in icd_ms if m.value]
    codes_in_docs = _codes_in_docs(literal)
    if len(codes_in_docs) > 1:
        warnings.append("Rozpor kódů diagnózy v dokumentech: " + "; ".join(codes_in_docs) + ".")
    if literal:
        r.icd10 = _field(literal, code_valid=all(mkn10.is_valid(m.value) is not False for m in literal) or False, code_path="literal")
    elif f["icd10"]:
        from app.retrieval.codes import MKN10, search_codes

        doc, ev, m = f["icd10"][0]
        hits = search_codes(MKN10, m.value, 1)
        if hits:
            r.icd10 = _field([_M(doc, ev, m, hits[0].code)], code_valid=True, code_path="semantic")
    _apply_coder(r, out, f, docs, codes_in_docs)
    if r.icd10.value and mkn10.is_valid(r.icd10.value) is False:
        parent = r.icd10.value[:-1].rstrip(".")
        if mkn10.is_valid(parent):
            r.icd10.alternatives = [parent] + [a for a in r.icd10.alternatives if a != parent]
            r.icd10.confidence_reasons.append(f"návrh: {parent} ({r.icd10.value} v MKN-10-CZ neexistuje)")
    _check_site(r, docs, warnings)
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
    _diagnosis_date_fallback(r, docs)
    r.laterality = _field(_normalised(f["laterality"], normalize.laterality), to_display=lambda v: v.value)

    # --- morphology
    r.morphology_type = _field(_normalised(f["morphology_type"], lambda v: "Cytologie" if "cyto" in v.lower() else ("Histologie" if "histo" in v.lower() else None)))
    morph_items = f["morphology"]
    names = [_M(doc, ev, m, _clean_name(m.value), "code_label" if _CODE_FOOTER.search(m.quote) else None)
             for doc, ev, m in morph_items]
    # the code footer ("M1: M85203 KARCINOM LOBULARNI INFILTRUJICI") is the label of the code, not the pathologist's
    # wording: it names the field only when nothing else does (and then it does not make a conflict with the wording)
    worded = [n for n in names if n.kind != "code_label" and n.value]
    r.morphology_name = _field(worded or names, merge_contained=True)
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
    _clinical_m(r, docs)

    # --- lymph nodes: counted per specimen from the documents (extract/nodes.py); the LLM mentions only as a fallback
    llm_nodes = _normalised(f["lymph_nodes"], normalize.lymph_nodes)
    for n in llm_nodes:
        if _is_fragment(n.doc, n.ev, n.raw.quote):
            n.kind = "fragment"
    node_res = nodes.count(docs)
    r.pn_examined = _node_field(node_res, "examined", warnings) or _field(
        [_M(n.doc, n.ev, n.raw, n.value[0] if n.value else None, n.kind) for n in llm_nodes])
    r.pn_positive = _node_field(node_res, "positive", warnings) or _field(
        [_M(n.doc, n.ev, n.raw, n.value[1] if n.value else None, n.kind) for n in llm_nodes])
    for issue in nodes.check(node_res):
        warnings.append(f"Počet uzlin: {issue}.")
    r.sentinel_node = _field(_normalised(f["sentinel_node"], normalize.sentinel))
    r.clinical_stage = _field(_normalised(f["clinical_stage"], lambda v: (m.group(1).upper() if (m := re.search(r"\b((?:IV|III|II|I)[ABC]?)\b", v)) else None)))
    _derive_stage(r)

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
        # derive from an explicit M0 / M1 (never auto: 60 keeps it below the threshold -> review). MX says nothing about
        # metastases, so it never derives "lokalizované". The NOR rule for this field is an open question (M or stage).
        m_fields = [x for x in (r.tnm_pathological.m, r.tnm_clinical.m) if x.value and str(x.value)[:1] in "01" and x.evidence]
        if m_fields:
            extent = "2" if any(str(x.value).startswith("1") for x in m_fields) or r.metastasis_sites.value else "1"
            r.disease_extent = Extracted[str](
                value=extent,
                status=FieldStatus.found,
                confidence=60,
                confidence_reasons=[f"odvozeno z M{m_fields[0].value}: {'pokročilé' if extent == '2' else 'lokalizované'}",
                                    "není výslovně v textu", "pravidlo NOR pro rozsah neověřeno"],
                evidence=m_fields[0].evidence[:1],
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
