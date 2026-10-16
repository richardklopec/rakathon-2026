"""Report in the structure and codes of the ÚZIS NOR form 'Incidence zhoubného novotvaru' (contracts/nor_form.md).

The exact ÚZIS import format is not known yet (PLAN.md §10.1); this JSON mirrors the form fields 1:1.
"""

import re
from functools import lru_cache

from app.config import get_settings
from app.models import Case, DiagnosisBasis, Extracted, FieldStatus, Laterality, MetastasisSite, ReviewState
from app.validate import codefiles, mkn10, rodne_cislo
from app.validate.normalize import DISEASE_EXTENT_NOR, GRADE_NOR, LATERALITY_LABEL, LATERALITY_NOR, SENTINEL_LABEL

# Fields we treat as mandatory for "Úplné" (assumption, verify with FNO - PLAN.md §10.2)
REQUIRED = ["diagnosis_date", "icd10", "topography", "laterality", "diagnosis_basis", "morphology_type", "morphology_code", "grade", "disease_extent"]

STAGE_NOR = {"I": "1 - Stadium I", "II": "2 - Stadium II", "III": "3 - Stadium III", "IV": "4 - Stadium IV"}


def _v(f: Extracted):
    return None if f.review.state == ReviewState.rejected or f.status == FieldStatus.missing else f.value


def _date(f: Extracted) -> str | None:
    d = _v(f)
    if not d:
        return None
    return ".".join(str(x) for x in (d.day, d.month, d.year) if x)


def _bits(values) -> int | None:
    return None if values is None else sum(int(v) for v in values)


def build(case: Case) -> dict:
    r, s = case.report, get_settings()
    icd = _v(r.icd10)
    lat = _v(r.laterality)
    grade = _v(r.grade)
    stage = _v(r.clinical_stage)
    extent = _v(r.disease_extent)
    y = r.tnm_pathological.y_prefix

    form = {
        "diagnosticka_cast": {
            "zarizeni": s.reporting_facility,
            "oddeleni": s.reporting_department or None,
            "zeme_puvodu": "203 - Česko",
        },
        "diagnoza": {
            "datum_stanoveni_diagnozy": _date(r.diagnosis_date),
            "k_dg_vedla_vysetreni": _bits(_v(r.diagnosis_basis)),
            "lateralita": LATERALITY_LABEL[LATERALITY_NOR[lat]] if lat else None,
            "dg_mkn": icd,
            "dg_slovne": mkn10.lookup(icd) if icd else None,
            "topografie": (mkn10.topography_label(_v(r.topography)) or _v(r.topography)) if _v(r.topography) else None,
        },
        "morfologie": {
            "typ_morfologie": _v(r.morphology_type),
            "kod_morfologie": _v(r.morphology_code),
            "grading": GRADE_NOR.get(grade, grade) if grade else None,
            "nazev_morfologie": _v(r.morphology_name),
        },
        "tnm": {
            "T": _v(r.tnm_clinical.t), "N": _v(r.tnm_clinical.n), "M": _v(r.tnm_clinical.m),
            "y": y,
            "pT": _v(r.tnm_pathological.t), "pN": _v(r.tnm_pathological.n),
            "pN_vys": _v(r.pn_examined), "pN_poz": _v(r.pn_positive),
            "sn": SENTINEL_LABEL.get(_v(r.sentinel_node)) if _v(r.sentinel_node) else None, "pM": _v(r.tnm_pathological.m),
            "lokalizace_vzdalenych_metastaz": _bits(_v(r.metastasis_sites)),
            "klinicke_stadium": STAGE_NOR.get(stage, stage) if stage else None,
        },
        "ostatni": {"onemocneni": DISEASE_EXTENT_NOR.get(extent, extent) if extent else None},
        "hlaseni": {
            "datum_hlaseni": case.confirmed_at.date().isoformat() if case.confirmed_at else None,
            "jmeno_hlasiciho_lekare": case.confirmed_by,
            "pracoviste_hlasici_novotvar": 3,  # 1 stanovilo dg. + 2 léčí (default for FNO oncology)
        },
    }
    missing = [name for name in REQUIRED if _v(getattr(case.report, name)) in (None, [], "")]
    return {
        "formular": "NOR - Incidence zhoubného novotvaru",
        "pacient": case.patient_ref,
        "pacient_rc": patient_check(case.patient_ref),
        "stav": "Úplné" if not missing else "Neúplné",
        "chybi_povinne": missing,
        "potvrzeno": case.confirmed_at is not None,
        "varovani": case.warnings,
        **form,
    }


def patient_check(patient_ref: str | None) -> dict:
    """Birth-number check of the patient header ('Pacient RČ'); anonymised ids (e.g. 'PAC001') are not birth numbers."""
    if not patient_ref or not rodne_cislo.looks_like(patient_ref):
        return {"je_rc": False, "platne": None, "chyby": []}
    rc = rodne_cislo.check(patient_ref)
    return {
        "je_rc": True,
        "platne": rc.valid,
        "chyby": rc.errors,
        "datum_narozeni": rc.birth_date.isoformat() if rc.birth_date else None,
        "pohlavi": rc.sex,
    }


def _options(labels: dict[str, str]) -> list[dict]:
    return [{"value": code, "label": label} for code, label in labels.items()]


def _site_terms() -> dict[str, list[str]]:
    """Organ / site names per code from the neoplasm index (07_…novotvary): lets 'jícen' or 'prs' find the code."""
    terms: dict[str, list[str]] = {}
    stack: list[str] = []
    for row in codefiles.rows(codefiles.INDEX_NEOPLASMS)[1:]:
        if len(row) < 3 or not row[0].isdigit():
            continue
        level = int(row[0])
        name = re.split(r"\s+–\s+viz\b|\(viz\b", row[1])[0].strip(" –-*").strip()
        stack = (stack + [""] * level)[: level - 1] + [name]  # the index starts at level 2 (level 1 = "Novotvar")
        # primary malignant, in situ and uncertain behaviour are reportable to NOR (secondary / benign are not)
        for col in (2, 4, 6):
            code = row[col].strip() if len(row) > col else ""
            if re.fullmatch(r"[CD]\d{2}(\.\d)?", code):
                term = " ".join(p for p in stack if p)
                if term not in terms.setdefault(code, []):
                    terms[code].append(term)
    return terms


def _with_search(options: list[dict], terms: dict[str, list[str]]) -> list[dict]:
    for o in options:
        if found := terms.get(o["value"]):
            o["search"] = " · ".join(found)[:600]
    return options


@lru_cache
def codelists() -> dict:
    """Options of the form's select boxes: `value` is what the report stores (models.py), `label` is what the form shows,
    optional `search` holds extra words to find the option by (site names from the neoplasm index)."""
    onco = re.compile(r"^(C\d|D0\d|D3[7-9]|D4[0-8])")
    rows = mkn10._rows()
    sites = _site_terms()
    mkn = _with_search([{"value": c, "label": f"{c} - {r['Nazev']}"} for c, r in rows.items() if onco.match(c)], sites)
    topo = _with_search([{"value": c, "label": mkn10.topography_label(c)} for c in rows if re.match(r"^C[0-7]\d\.\d$|^C80\.\d$", c)], sites)
    morph: dict[str, str] = {}
    try:
        from app.retrieval.codes import load_morphology

        for code, name in load_morphology():
            if code not in morph or len(name) < len(morph[code]):  # shortest term = the base name of the code
                morph[code] = name
    except (RuntimeError, OSError):
        pass  # code files not available: the form falls back to free text
    lat = {v.value: LATERALITY_LABEL[LATERALITY_NOR[v]] for v in Laterality if v != Laterality.midline}
    return {
        "laterality": sorted(_options(lat), key=lambda o: o["label"]),
        "morphology_type": _options({"Histologie": "Histologie", "Cytologie": "Cytologie"}),
        "grade": _options(GRADE_NOR),
        "sentinel_node": _options(SENTINEL_LABEL),
        "clinical_stage": _options(STAGE_NOR),
        "disease_extent": _options(DISEASE_EXTENT_NOR),
        "diagnosis_basis": [{"value": b.value, "label": f"{b.value:02d} {lbl}"} for b, lbl in zip(DiagnosisBasis, BASIS_LABELS)],
        "metastasis_sites": [{"value": s.value, "label": f"{s.value} {lbl}"} for s, lbl in zip(MetastasisSite, METASTASIS_LABELS)],
        "icd10": mkn,
        "topography": topo,
        "morphology_code": [{"value": c, "label": f"{c} - {n}"} for c, n in sorted(morph.items())],
    }


BASIS_LABELS = ["klinicky jasné", "klinické vyšetření", "laboratorní vyš. markery", "cytologie", "histologie metastázy", "histologie primárního nádoru"]
METASTASIS_LABELS = ["neznámo", "plíce", "kostní dřeň", "kost", "pleura", "játra", "peritoneum", "mozek", "nadledvinky", "uzliny", "kůže", "jiný orgán"]
