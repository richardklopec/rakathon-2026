from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app import audit, extract, ingest, store
from app.config import get_settings
from app.main import app
from app.models import Case, Extracted, FieldStatus, NorReport, PartialDate, ProgressionEvent, Review, ReviewState

DEMO = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_histologie.txt"


def _found(value, state=ReviewState.auto_accepted, status=FieldStatus.found) -> Extracted:
    return Extracted(value=value, status=status, confidence=90, review=Review(state=state))


def _kinds(old: NorReport, new: NorReport) -> dict[str, tuple]:
    return {path: (kind, o, n) for kind, path, o, n in audit.diff(old, new)}


def test_diff_names_what_the_clinician_did():
    old = NorReport(
        icd10=_found("C50.4", ReviewState.pending),
        grade=_found("2", ReviewState.pending),
        laterality=_found("left", ReviewState.pending),
        diagnosis_date=Extracted(),  # missing
        clinical_stage=_found("I", ReviewState.pending, FieldStatus.conflict),
        topography=Extracted(review=Review(state=ReviewState.pending)),  # missing mandatory field
    )
    new = old.model_copy(deep=True)
    new.icd10.review.state = ReviewState.confirmed  # confirmed as is
    new.grade.value, new.grade.review.state = "3", ReviewState.edited  # overwritten
    new.laterality.review.state = ReviewState.rejected
    new.diagnosis_date = _found(PartialDate(year=2026, month=3, day=5), ReviewState.edited)  # filled in
    new.clinical_stage.value, new.clinical_stage.status = "II", FieldStatus.found  # conflict resolved
    new.topography.review.state = ReviewState.confirmed  # "not in the documentation"

    got = _kinds(old, new)
    assert got["icd10"] == (audit.CONFIRMED, None, "C50.4")
    assert got["grade"] == (audit.CHANGED, "2", "3")
    assert got["laterality"][0] == audit.REJECTED
    assert got["diagnosis_date"] == (audit.FILLED, None, "5. 3. 2026")
    assert got["clinical_stage"] == (audit.RESOLVED, "I", "II")
    assert got["topography"][0] == audit.CONFIRMED_MISSING
    assert "morphology_code" not in got  # untouched fields are not logged


def test_diff_ignores_ai_bookkeeping():
    old = NorReport(icd10=_found("C50.4"))
    new = old.model_copy(deep=True)
    new.icd10.confidence, new.icd10.confidence_reasons = 70, ["jiný důvod"]
    assert audit.diff(old, new) == []


def test_diff_logs_relapse_added_and_removed():
    event = ProgressionEvent(status=_found("recurrence", ReviewState.edited), date=_found(PartialDate(year=2026, month=9, day=14), ReviewState.edited))
    with_relapse = NorReport(progression=[event])
    added = _kinds(NorReport(), with_relapse)
    assert added["progression[0].status"] == (audit.FILLED, None, "recidiva")
    assert audit.label("progression[0].date") == "Relaps 1: datum"
    removed = _kinds(with_relapse, NorReport())
    assert removed["progression[0].date"][0] == audit.REMOVED


def test_actor_header_keeps_diacritics():
    assert audit.actor_from_header(quote("MUDr. Jana Nováková")) == "MUDr. Jana Nováková"
    assert audit.actor_from_header(None) == audit.UNKNOWN_ACTOR


@pytest.fixture
def no_iris(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    monkeypatch.setattr(audit, "_iris_up", lambda: False)
    return tmp_path


def test_entries_fall_back_to_a_local_file_when_iris_is_down(no_iris):
    assert audit.log("c1", "MUDr. Test", audit.CHANGED, "grade", "2", "3") == "local"
    entries, iris_up = audit.read("c1")
    assert not iris_up
    assert [(e.kind, e.label, e.old, e.new, e.storage) for e in entries] == [(audit.CHANGED, "Grading", "2", "3", "local")]


def test_report_edit_through_the_api_is_logged_with_the_user(no_iris):
    docs = ingest.to_documents(DEMO.name, DEMO.read_bytes())
    now = datetime.now(timezone.utc)
    store.save(Case(id="audit-demo", documents=docs, report=extract.extract_mock(docs), created_at=now, updated_at=now))
    client = TestClient(app)

    report = client.get("/api/cases/audit-demo").json()["report"]
    report["grade"]["value"], report["grade"]["status"], report["grade"]["review"]["state"] = "3", "found", "edited"
    r = client.put("/api/cases/audit-demo/report", json=report, headers={"X-Actor": quote("MUDr. Nováková")})
    assert r.status_code == 200

    log = client.get("/api/cases/audit-demo/audit").json()
    assert log["iris"] is False
    (e,) = log["entries"]
    assert (e["actor"], e["kind"], e["label"], e["new"]) == ("MUDr. Nováková", audit.FILLED if e["old"] is None else audit.CHANGED, "Grading", "3")
