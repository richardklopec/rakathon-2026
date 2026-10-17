"""Cases live in IRIS (Nor.CaseRecord) and each has one FHIR record: a draft after the AI extraction, updated in place later."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import audit, ingest, store
from app.config import get_settings
from app.main import app, startup
from app.models import Case

DEMO = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_histologie.txt"


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setattr(get_settings(), "llm_mode", "mock")
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    return TestClient(app)


def _extracted(client) -> dict:
    case = client.post("/api/cases", files=[("files", (DEMO.name, DEMO.read_bytes(), "text/plain"))]).json()
    return client.post(f"/api/cases/{case['id']}/extract").json()


def _resources(bundle: dict) -> dict[str, dict]:
    return {e["request"]["url"]: e.get("resource") for e in bundle["entry"]}


def _resolve_all(report: dict) -> dict:
    for value in report.values():
        fields = [value[p] for p in "tnm"] if isinstance(value, dict) and "y_prefix" in value else [value] if isinstance(value, dict) else []
        for f in fields:
            if f["needs_review"] and f["review"]["state"] == "pending":
                f["review"]["state"] = "confirmed"
    return report


def test_extraction_writes_a_draft_and_confirmation_updates_the_same_record(monkeypatch, tmp_path, fhir):
    client = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(get_settings(), "auto_accept_threshold", 85)  # the demo ICD-10 (70-80) must wait for review
    case = _extracted(client)
    cid = case["id"]

    # right after the AI extraction: a draft in FHIR, only what AI could accept on its own
    assert case["fhir"]["status"] == "preliminary" and case["fhir"]["composition"] == f"Composition/{cid}"
    (draft,) = fhir.bundles
    res = _resources(draft)
    assert all(e["request"]["method"] == "PUT" for e in draft["entry"])  # stable ids, never a second record
    comp = res[f"Composition/{cid}"]
    assert comp["status"] == "preliminary" and comp["title"].endswith("(rozpracované)") and "attester" not in comp
    assert any(s["title"] == "Ke kontrole lékařem" for s in comp["section"])
    cond = res[f"Condition/{cid}-dg"]
    assert cond["verificationStatus"]["coding"][0]["code"] == "provisional"
    assert "code" not in cond  # ICD-10 waits for the clinician, it is not in FHIR yet
    assert all(r["status"] == "preliminary" for u, r in res.items() if u.startswith("Observation/"))
    assert f"DocumentReference/{cid}-d0" in res

    # the clinician resolves the queue and confirms: the same resources, now final
    client.put(f"/api/cases/{cid}/report", json=_resolve_all(case["report"]))
    confirmed = client.post(f"/api/cases/{cid}/confirm", json={"by": "MUDr. Test"}).json()
    assert confirmed["fhir"]["status"] == "final" and confirmed["fhir"]["error"] is None
    final = _resources(fhir.bundles[-1])
    assert f"DocumentReference/{cid}-d0" not in final  # documents do not change, they are not sent again
    comp = final[f"Composition/{cid}"]
    assert comp["status"] == "final" and comp["attester"][0]["party"]["display"] == "MUDr. Test"
    assert not any(s["title"] == "Ke kontrole lékařem" for s in comp["section"])
    cond = final[f"Condition/{cid}-dg"]
    assert cond["verificationStatus"]["coding"][0]["code"] == "confirmed" and cond["code"]["coding"][0]["code"] == "C50.4"
    assert int(confirmed["fhir"]["version"]) == 3  # draft, edit, confirmation: one record, three versions
    log = [e["kind"] for e in client.get(f"/api/cases/{cid}/audit").json()["entries"]]
    assert log.count(audit.FHIR_SUBMITTED) == 2  # draft, final (an edit of the draft is not a new event)


def test_a_field_rejected_later_is_deleted_from_fhir(monkeypatch, tmp_path, fhir):
    client = _client(monkeypatch, tmp_path)
    case = _extracted(client)
    cid = case["id"]
    report = case["report"]
    pt = f"Observation/{cid}-pt"
    assert pt not in _resources(fhir.bundles[0])  # pT waits for the clinician
    report["tnm_pathological"]["t"]["review"]["state"] = "confirmed"
    report = client.put(f"/api/cases/{cid}/report", json=report).json()["report"]
    assert _resources(fhir.bundles[-1])[pt]["valueCodeableConcept"]["text"] == "pT1c"
    report["tnm_pathological"]["t"]["review"]["state"] = "rejected"  # the clinician changes their mind
    client.put(f"/api/cases/{cid}/report", json=report)
    assert {"method": "DELETE", "url": pt} in [e["request"] for e in fhir.bundles[-1]["entry"]]
    assert pt not in store.load(cid).fhir.resources


def test_fhir_down_keeps_the_case_and_a_later_write_catches_up(monkeypatch, tmp_path, fhir):
    client = _client(monkeypatch, tmp_path)
    fhir.down = True
    case = _extracted(client)
    assert case["fhir"]["status"] is None and "nepovedl" in case["fhir"]["error"]
    assert store.load(case["id"]).report.icd10.value == "C50.4"  # saved in IRIS Nor.CaseRecord anyway
    assert client.get(f"/api/cases/{case['id']}/audit").json()["entries"][-1]["kind"] == audit.FHIR_FAILED

    fhir.down = False
    again = client.post(f"/api/cases/{case['id']}/fhir-sync").json()
    assert again["fhir"]["status"] == "preliminary" and again["fhir"]["error"] is None
    assert f"DocumentReference/{case['id']}-d0" in _resources(fhir.bundles[-1])


def test_startup_moves_old_json_cases_into_iris_and_writes_their_drafts(monkeypatch, tmp_path, fhir):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    monkeypatch.setattr(get_settings(), "llm_mode", "mock")
    from app import extract

    docs = ingest.to_documents(DEMO.name, DEMO.read_bytes())
    now = datetime.now(timezone.utc)
    (tmp_path / "cases").mkdir()
    old = Case(id="stary", documents=docs, report=extract.extract(docs)[0], created_at=now, updated_at=now)
    (tmp_path / "cases" / "stary.json").write_text(old.model_dump_json(), encoding="utf-8")
    fresh = Case(id="neprecteny", documents=docs, created_at=now, updated_at=now)  # not extracted: nothing for FHIR
    store.save(fresh)

    startup()
    assert {c.id for c in store.list_cases()} == {"stary", "neprecteny"}
    assert not (tmp_path / "cases").exists() and (tmp_path / "cases-presunuto-do-iris" / "stary.json").exists()
    assert store.load("stary").fhir.status == "preliminary" and store.load("neprecteny").fhir.status is None
    assert [b["entry"][-1]["request"]["url"] for b in fhir.bundles] == ["Composition/stary"]


def test_cases_come_from_iris_and_its_outage_is_a_clear_503(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    class Down:
        def all(self):
            raise store.Unavailable("Connection refused")

    monkeypatch.setattr(store, "backend", Down())
    res = client.get("/api/cases")
    assert res.status_code == 503 and "IRIS" in res.json()["detail"]


def test_stored_json_has_no_computed_fields():
    now = datetime.now(timezone.utc)
    store.save(Case(id="x", created_at=now, updated_at=now))
    assert "ai_confidence" not in json.loads(store.backend["x"])


def test_patient_is_named_by_the_birth_number_most_documents_give():
    from app.models import Document

    docs = [Document(id=f"d{i}", filename=f"z{i}.txt", text=t) for i, t in
            enumerate(["Pacient r. č.: 111111/1111", "RČ 111111/1111, kontrola", "r. č. 222222/2222"])]
    now = datetime.now(timezone.utc)
    case = Case(id="rc", documents=docs, created_at=now, updated_at=now)
    assert case.document_rc == "111111/1111"
    assert Case(id="none", created_at=now, updated_at=now).document_rc is None
    store.save(case)
    assert "document_rc" not in json.loads(store.backend["rc"])  # derived, never stored


def test_form_fields_not_in_the_documents_are_typed_in_the_preview(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    case = _extracted(client)
    cid = case["id"]
    client.put(f"/api/cases/{cid}/report", json=_resolve_all(case["report"]))
    client.post(f"/api/cases/{cid}/confirm", json={"by": "MUDr. Test"})
    form = {"oddeleni": "20 - Chirurgie", "cizinec": True, "zeme_puvodu": "703 - Slovensko", "skupina": "A",
            "pracoviste_hlasici_novotvar": 1}
    saved = client.put(f"/api/cases/{cid}/form", json=form, headers={"X-Actor": "MUDr.%20Test"}).json()
    assert saved["form"]["oddeleni"] == "20 - Chirurgie" and saved["confirmed_at"] is None  # a change needs a new confirmation
    preview = client.get(f"/api/cases/{cid}/uzis-preview").json()
    assert preview["diagnosticka_cast"]["oddeleni"] == "20 - Chirurgie"
    assert preview["diagnosticka_cast"]["zeme_puvodu"] == "703 - Slovensko" and preview["diagnoza"]["cizinec"] is True
    assert preview["tnm"]["skupina"] == "A" and preview["hlaseni"]["pracoviste_hlasici_novotvar"] == 1
    assert preview["diagnosticka_cast"]["zarizeni"] == get_settings().reporting_facility  # untouched -> default
    log = {e["label"]: e for e in client.get(f"/api/cases/{cid}/audit").json()["entries"]}
    assert log["Oddělení"]["new"] == "20 - Chirurgie" and log["Cizinec"]["new"] == "ano"
