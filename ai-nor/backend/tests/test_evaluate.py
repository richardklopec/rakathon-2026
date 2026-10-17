"""scripts/evaluate.py: comparing fields with gold values and the metrics (synthetic values only)."""

from scripts import evaluate as ev

from app.confidence import apply_review_policy
from app.models import DiagnosisBasis, Evidence, Extracted, FieldStatus, Laterality, NorReport, PartialDate

EV = [Evidence(doc_id="d", quote="x", start=0, end=1, verified=True)]


def _f(value, confidence=90, status=FieldStatus.found):
    return Extracted(value=value, status=status, confidence=confidence, evidence=EV)


def _report() -> NorReport:
    r = NorReport(
        icd10=_f("C34.9", 95),  # wrong, auto-accepted
        laterality=_f(Laterality.left, 90),
        diagnosis_basis=_f([DiagnosisBasis.clinical_exam, DiagnosisBasis.histology_primary], 88),
        diagnosis_date=_f(PartialDate(year=2025, month=11, day=3), 60),
        morphology_name=_f("Adenokarcinom, mucinózní složka;", 70),
        pn_examined=_f(12, 80, FieldStatus.conflict),  # wrong, but goes to review
        clinical_stage=_f("IA", 70),  # gold says missing
    )
    return NorReport.model_validate_json(apply_review_policy(r).model_dump_json())


GOLD = {
    "icd10": {"value": "C34.1", "status": "explicit"},
    "laterality": {"value": "2", "status": "explicit"},
    "diagnosis_basis": {"value": 17, "status": "derived"},
    "diagnosis_date": {"value": "2025-11-03", "status": "derived"},
    "morphology_name": {"value": "Adenokarcinom + mucinózní složka", "status": "explicit"},
    "pn_examined": {"value": 14, "status": "explicit"},
    "clinical_stage": {"value": None, "status": "missing"},
    "grade": {"value": "2", "status": "explicit"},  # app leaves it empty
    "tnm_pathological.m": {"value": "X", "status": "open"},
}


def test_values_in_nor_codes():
    r = _report()
    assert ev.app_value(r.laterality, "laterality") == "2"
    assert ev.app_value(r.diagnosis_basis, "diagnosis_basis") == 17
    assert ev.app_value(r.diagnosis_date, "diagnosis_date") == "2025-11-03"
    assert ev.app_value(_f(PartialDate(year=2026, month=4)), "diagnosis_date") == "2026-04"
    assert ev.app_value(r.grade, "grade") is None  # missing
    assert ev.norm("Adenokarcinom, mucinózní složka;") == ev.norm("adenokarcinom + mucinozni slozka")
    assert ev.norm("8140/3") == "8140/3" and ev.norm("1B") == ev.norm("1b")


def test_outcomes():
    rows = {r["path"]: r for r in ev.rows_for("syn", 1, _report(), GOLD)}
    assert rows["icd10"]["outcome"] == "wrong" and rows["icd10"]["state"] == "auto_accepted" and not rows["icd10"]["flagged"]
    assert rows["laterality"]["outcome"] == "correct"
    assert rows["diagnosis_basis"]["outcome"] == "correct"
    assert rows["morphology_name"]["outcome"] == "correct"
    assert rows["pn_examined"]["outcome"] == "wrong" and rows["pn_examined"]["flagged"] and rows["pn_examined"]["conflict"]
    assert rows["clinical_stage"]["outcome"] == "false_filled"
    assert rows["grade"]["outcome"] == "false_missing" and rows["grade"]["flagged"]  # mandatory: in the review queue
    assert rows["tnm_pathological.m"]["outcome"] == "open"
    assert rows["tumour_order"]["outcome"] == "open"  # no gold entry = todo


def test_metrics():
    m = ev.metrics(ev.rows_for("syn", 1, _report(), GOLD))
    assert m["scored"] == 8 and m["correct"] == 4
    assert (m["wrong"], m["false_missing"], m["false_filled"]) == (2, 1, 1)
    assert m["errors_flagged"] == 3  # pn_examined (conflict), clinical_stage (70 < 80), grade (missing mandatory); icd10 slips through
    assert m["auto"] == 3 and m["auto_correct"] == 2  # icd10 (wrong), laterality, diagnosis_basis
    bands = {b["band"]: b for b in m["bands"]}
    assert bands["80–100"]["n"] == 3 and bands["80–100"]["correct"] == 2


def test_warnings_and_variance():
    r = _report()
    r.icd10.confidence_reasons = ["⚠ pravidla MKN-10 navrhují C34.1"]
    found = ev.match_warnings(
        [{"id": "a", "desc": "identita", "match": "Nesoulad identity"}, {"id": "b", "desc": "kód", "match": r"C34\.1"},
         {"id": "c", "desc": "nádor", "match": "Další \\(starší\\) nádor"}],
        ["Další (starší) nádor v dokumentaci, nehlásí se zde: x"], r)
    assert [f["found"] for f in found] == [None, "jen v důvodech pole", "varování"]
    rows = ev.rows_for("syn", 1, r, GOLD) + ev.rows_for("syn", 2, NorReport(), GOLD)
    assert any(v["path"] == "icd10" and v["kind"] == "value" for v in ev.run_variance(rows))
    r2 = _report()
    r2.laterality.confidence = 60  # same value, lower score
    rows = ev.rows_for("syn", 1, _report(), GOLD) + ev.rows_for("syn", 2, r2, GOLD)
    assert [(v["path"], v["kind"]) for v in ev.run_variance(rows)] == [("laterality", "score")]


def test_template_has_no_values(tmp_path):
    t = ev.template(tmp_path)
    assert all(f["value"] is None and f["status"] == "todo" for f in t["fields"].values())
