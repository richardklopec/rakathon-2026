import base64
import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audit, extract, ingest, nis, store
from app.config import get_settings
from app.main import app
from scripts.nis_demo_send import document_reference

DEMO = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_histologie.txt"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    monkeypatch.setattr(audit, "_iris_up", lambda: False)
    return TestClient(app)


def _nis_docs() -> list[dict]:
    docs = [document_reference("NIS-1", "Histologie", "histologie.txt", DEMO.read_text(encoding="utf-8")),
            document_reference("NIS-1", "Ambulantní zpráva", "az.txt", "Ambulantní zpráva. Dg.: C50.4"),
            document_reference("NIS-2", "MDT", "mdt.txt", "Zápis z MDT. Dg.: C20")]
    for i, d in enumerate(docs):
        d["id"] = f"d{i}"
    return docs


def test_nis_inbox_groups_by_patient_and_import_creates_a_case(env, monkeypatch):
    monkeypatch.setattr(nis, "_search", _nis_docs)
    monkeypatch.setattr(nis.fhir, "is_up", lambda: True)

    inbox = env.get("/api/nis/inbox").json()
    assert inbox["iris"] is True
    assert [(p["patient"], len(p["documents"])) for p in inbox["patients"]] == [("NIS-1", 2), ("NIS-2", 1)]

    case = env.post("/api/nis/import", json={"patient": "NIS-1", "ids": ["d0", "d1"]}).json()
    assert case["patient_ref"] == "NIS-1"
    assert len(case["documents"]) == 2 and "pT1c" in case["documents"][0]["text"]
    # imported reports leave the inbox, the import is in the change log
    assert [p["patient"] for p in env.get("/api/nis/inbox").json()["patients"]] == ["NIS-2"]
    assert env.get(f"/api/cases/{case['id']}/audit").json()["entries"][0]["kind"] == audit.NIS_IMPORTED


def test_nis_content_is_base64_of_the_report():
    doc = document_reference("NIS-1", "Histologie", "h.txt", "Dg.: C50.4")
    assert nis.content(doc) == "Dg.: C50.4".encode() and nis.filename(doc) == "h.txt"
    assert base64.b64decode(doc["content"][0]["attachment"]["data"]).decode() == "Dg.: C50.4"


def _save(case_id: str, confirmed: bool):
    docs = ingest.to_documents(DEMO.name, DEMO.read_bytes())
    now = datetime.now(timezone.utc)
    case = store.Case(id=case_id, patient_ref=case_id.upper(), documents=docs, report=extract.extract_mock(docs), created_at=now, updated_at=now)
    if confirmed:
        case.confirmed_by, case.confirmed_at = "MUDr. Test", now
    store.save(case)


def test_bulk_export_only_confirmed_and_logged(env):
    _save("a", True)
    _save("b", True)
    _save("c", False)

    refused = env.post("/api/export", json={"case_ids": ["a", "c"], "format": "csv"})
    assert refused.status_code == 409 and "C" in refused.json()["detail"]

    r = env.post("/api/export", json={"case_ids": ["a", "b"], "format": "csv"}, headers={"X-Actor": "MUDr.%20Test"})
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    assert [row["pacient"] for row in rows] == ["A", "B"]
    assert rows[0]["diagnoza.dg_mkn"] == "C50.4"

    status = env.get("/api/exports").json()
    assert set(status) == {"a", "b"} and status["a"]["actor"] == "MUDr. Test"

    payload = json.loads(env.post("/api/export", json={"case_ids": ["b"], "format": "json"}).content)
    assert payload["pocet"] == 1 and payload["hlaseni"][0]["id_pripadu"] == "b"
