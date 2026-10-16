from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import extract, ingest
from app.fhir.mapping import build_bundle
from app.main import app
from app.models import Case, FieldStatus, ReviewState

DEMO = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_histologie.txt"


def _demo_case() -> Case:
    docs = ingest.to_documents(DEMO.name, DEMO.read_bytes())
    now = datetime.now(timezone.utc)
    return Case(id="demo", patient_ref="DEMO001", documents=docs, report=extract.extract_mock(docs), created_at=now, updated_at=now)


def test_ingest_guesses_kind_and_keeps_text():
    (doc,) = ingest.to_documents(DEMO.name, DEMO.read_bytes())
    assert doc.kind == "histology"
    assert "pT1c" in doc.text


def test_mock_extraction_has_evidence_pointing_into_the_document():
    case = _demo_case()
    r = case.report
    assert r.icd10.value == "C50.4"
    assert r.morphology_code.value == "8500/3"
    assert r.tnm_pathological.t.value == "1c"
    for field in (r.icd10, r.morphology_code, r.tnm_pathological.t):
        ev = field.evidence[0]
        doc = next(d for d in case.documents if d.id == ev.doc_id)
        assert doc.text[ev.start : ev.end] == ev.quote


def test_review_policy_auto_accepts_only_confident_fields():
    from app.confidence import apply_review_policy, review_queue

    case = _demo_case()
    r = apply_review_policy(case.report)
    assert r.morphology_code.confidence == 95
    assert r.morphology_code.review.state == ReviewState.auto_accepted and not r.morphology_code.needs_review
    # ICD-10 from histology scores 70 (80 with the MKN-10 table loaded) < 85 -> review
    assert r.icd10.needs_review and r.icd10.review.state == ReviewState.pending
    # a missing MANDATORY field is queued (fill it in or confirm it is not in the documentation), an optional one is not
    assert r.grade.needs_review and r.grade.status == FieldStatus.missing
    assert not r.clinical_stage.needs_review
    queue = review_queue(r)
    found = [(p, f) for p, f in queue if f.status != FieldStatus.missing]
    assert {p for p, _ in found} == {"icd10", "tnm_pathological.t", "tnm_pathological.n"}
    assert {p for p, f in queue if f.status == FieldStatus.missing} == {
        "diagnosis_date", "topography", "laterality", "diagnosis_basis", "morphology_type", "grade", "disease_extent"}
    scores = [f.confidence or 0 for _, f in queue]
    assert scores == sorted(scores)  # missing (no score) first, then lowest confidence
    r.grade.review.state = ReviewState.confirmed  # "really not in the documentation"
    assert "grade" not in {p for p, _ in review_queue(apply_review_policy(r))}


def test_conflict_always_goes_to_review():
    from app.confidence import apply_review_policy
    from app.models import FieldStatus

    case = _demo_case()
    case.report.morphology_code.status = FieldStatus.conflict
    r = apply_review_policy(case.report)
    assert r.morphology_code.needs_review  # even with confidence 95


def test_bundle_writes_auto_accepted_and_human_confirmed_fields():
    from app.confidence import apply_review_policy

    case = _demo_case()
    apply_review_policy(case.report)
    bundle = build_bundle(case)
    condition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    assert "code" not in condition  # ICD-10 still waits for review
    assert condition["extension"][0]["valueCodeableConcept"]["coding"][0]["code"] == "8500/3"  # auto-accepted

    case.report.icd10.review.state = ReviewState.confirmed
    case.report.tnm_pathological.t.review.state = ReviewState.confirmed
    case.confirmed_by = "MUDr. Test"
    bundle = build_bundle(case)
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert bundle["type"] == "transaction"
    assert types.count("Observation") == 1 and "Provenance" in types
    condition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    assert condition["code"]["coding"][0]["code"] == "C50.4"
    assert condition["meta"]["tag"][0]["code"] == "confirmed"
    obs = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation")
    assert obs["code"]["coding"][0]["code"] == "384625004"  # pT category
    assert obs["valueCodeableConcept"]["text"] == "pT1c"
    prov = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Provenance")
    assert any(a["type"]["coding"][0]["code"] == "verifier" for a in prov["agent"])


def test_api_create_and_extract(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    client = TestClient(app)
    res = client.post("/api/cases", files=[("files", (DEMO.name, DEMO.read_bytes(), "text/plain"))])
    assert res.status_code == 200
    case_id = res.json()["id"]
    res = client.post(f"/api/cases/{case_id}/extract")
    assert res.json()["report"]["icd10"]["value"] == "C50.4"
