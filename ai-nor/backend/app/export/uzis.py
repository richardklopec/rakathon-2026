"""Report in the structure and codes of the ÚZIS NOR form 'Incidence zhoubného novotvaru' (contracts/nor_form.md).

The exact ÚZIS import format is not known yet (PLAN.md §10.1); this JSON mirrors the form fields 1:1.
"""

from app.config import get_settings
from app.models import Case, Extracted, FieldStatus, ReviewState
from app.validate import mkn10
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
        "stav": "Úplné" if not missing else "Neúplné",
        "chybi_povinne": missing,
        "potvrzeno": case.confirmed_at is not None,
        "varovani": case.warnings,
        **form,
    }
