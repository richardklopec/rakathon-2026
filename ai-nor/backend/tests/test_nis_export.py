import base64
import csv
import io
import json
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audit, extract, ingest, nis, store
from app.config import get_settings
from app.main import app
from scripts.nis_demo_send import document_reference, mdm, send_mllp

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


def test_imported_reports_are_read_from_the_cases_in_iris(env):
    now = datetime.now(timezone.utc)
    store.save(store.Case(id="x", nis_ids=["d0", "d1"], created_at=now, updated_at=now))
    assert nis.imported() == {"d0", "d1"}


def test_hl7_mdm_message_carries_the_report_for_the_iris_production():
    text = "Dg.: C50.4 | ER 90 % & PR 0\n" + r"Ki-67 ~ 20 % (a^b) C:\x"
    msg = mdm("NIS-DEMO-01", "Histologie", "histologie.txt", text, "DEMO-1", datetime(2026, 3, 5, 10, 15, tzinfo=timezone.utc))
    segments = msg.rstrip("\r").split("\r")
    assert [s[:3] for s in segments] == ["MSH", "EVN", "PID", "PV1", "TXA", "OBX", "OBX"]
    msh, pid, txa = segments[0].split("|"), segments[2].split("|"), segments[4].split("|")
    assert msh[8] == "MDM^T02^MDM_T02" and msh[11] == "2.5" and msh[17] == "UNICODE UTF-8"
    assert pid[3].split("^")[0] == "NIS-DEMO-01"
    assert (txa[2], txa[12], txa[16]) == ("SP", "DEMO-1^NIS", "histologie.txt")  # type, document number, file name
    # delimiters inside the text are escaped, so every OBX keeps its 11 fields
    assert segments[5].split("|")[5] == r"Dg.: C50.4 \F\ ER 90 % \T\ PR 0"
    assert segments[6].split("|")[5] == r"Ki-67 \R\ 20 % (a\S\b) C:\E\x"
    assert all(len(s.split("|")) == 12 for s in segments[5:])


def test_mllp_sends_all_messages_over_one_connection_and_reads_each_ack():
    received: list[bytes] = []

    def server(sock):
        conn, _ = sock.accept()
        with conn:
            buf = b""
            while len(received) < 2:
                buf += conn.recv(4096)
                while b"\x1c\x0d" in buf:
                    frame, buf = buf.split(b"\x1c\x0d", 1)
                    received.append(frame)
                    conn.sendall(b"\x0bMSH|^~\\&|IRIS|ISC|NIS|FNO|||ACK^T02|1|P|2.5\rMSA|CA|1\r\x1c\x0d")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        t = threading.Thread(target=server, args=(sock,), daemon=True)
        t.start()
        codes = send_mllp(["MSH|a\r", "MSH|ž\r"], "127.0.0.1", sock.getsockname()[1])
        t.join(5)
    assert codes == ["CA", "CA"]
    assert received == [b"\x0bMSH|a\r", b"\x0b" + "MSH|ž\r".encode("utf-8")]  # MLLP frame, UTF-8 (MSH-18)
