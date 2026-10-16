from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import extract, ingest
from app.fhir.mapping import build_bundle
from app.main import app
from app.models import Case, ReviewState

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


def test_bundle_contains_only_confirmed_fields():
    case = _demo_case()
    bundle = build_bundle(case)
    condition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    assert "code" not in condition  # nothing confirmed yet

    case.report.icd10.review.state = ReviewState.confirmed
    case.report.tnm_pathological.t.review.state = ReviewState.confirmed
    bundle = build_bundle(case)
    types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert bundle["type"] == "transaction"
    assert types.count("Observation") == 1 and "Provenance" in types
    condition = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition")
    assert condition["code"]["coding"][0]["code"] == "C50.4"
    obs = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Observation")
    assert obs["code"]["coding"][0]["code"] == "384625004"  # pT category
    assert obs["valueCodeableConcept"]["text"] == "pT1c"


def test_api_create_and_extract(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    client = TestClient(app)
    res = client.post("/api/cases", files=[("files", (DEMO.name, DEMO.read_bytes(), "text/plain"))])
    assert res.status_code == 200
    case_id = res.json()["id"]
    res = client.post(f"/api/cases/{case_id}/extract")
    assert res.json()["report"]["icd10"]["value"] == "C50.4"
