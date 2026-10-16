"""Live extraction with a fake LLM answer (no network): verification, normalisation, conflicts, confirm gating."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.extract import live
from app.extract.coder import CodeChoice
from app.extract.live import FieldMentions, LlmExtraction, Mention
from app.retrieval.rules import RuleHit
from app.models import Case, Document, FieldStatus

HIST = Document(
    id="h", filename="Histologie.pdf", kind="histology",
    text="Závěr:\n1. typ nádoru - invazivní karcinom NST\n2. grading nádoru - G2\n4. pTNM - pT1c pN0(sn)\nM1: M85003 KARCINOM\nDiagnóza: C504",
)
MDT = Document(id="m", filename="MDT.pdf", kind="MDT", text="Ca mammae l.sin., cT1c cN0 Mx. Grading G3 dle biopsie. Dg.: C50.4")


def fake_llm(system, user, schema):
    if schema is CodeChoice:  # second step: MKN-10 coder
        return CodeChoice(code="C50.4", rule_code="C50", rule_quote="C50.4 Horní zevní kvadrant prsu", reasoning="Horní zevní kvadrant.", certain=True)

    def m(doc, quote, value, explicit=True, hedged=False):
        return Mention(doc=doc, quote=quote, value=value, explicit=explicit, hedged=hedged)

    return LlmExtraction(
        primary_tumour="karcinom prsu vlevo",
        other_tumours=[],
        patient_sex="F",
        fields=[
            FieldMentions(field="icd10", mentions=[m(1, "Diagnóza: C504", "C504"), m(2, "Dg.: C50.4", "C50.4")]),
            FieldMentions(field="laterality", mentions=[m(2, "Ca mammae l.sin.", "l.sin.")]),
            FieldMentions(field="morphology", mentions=[m(1, "M1: M85003 KARCINOM", "M85003"), m(1, "invazivní karcinom NST", "invazivní karcinom NST")]),
            FieldMentions(field="grade", mentions=[m(1, "grading nádoru - G2", "G2"), m(2, "Grading G3 dle biopsie", "G3")]),
            FieldMentions(field="pT", mentions=[m(1, "pTNM - pT1c pN0(sn)", "pT1c")]),
            FieldMentions(field="pN", mentions=[m(1, "pTNM - pT1c pN0(sn)", "pN0(sn)")]),
            FieldMentions(field="cT", mentions=[m(2, "cT1c cN0 Mx", "cT1c")]),
            FieldMentions(field="cM", mentions=[m(2, "this quote does not exist", "Mx")]),
        ],
    )


C50_RULE = RuleHit(kind="category", code="C50", title="Zhoubný novotvar prsu", page=108, score=1.0,
                   text="C50 Zhoubný novotvar prsu\nC50.4 Horní zevní kvadrant prsu")


def _report(monkeypatch):
    from app.extract import coder

    monkeypatch.setattr(live.llm, "structured", fake_llm)
    monkeypatch.setattr(coder, "_default_candidates", lambda q, lit: ([C50_RULE], []))  # no IRIS in tests
    report, warnings, _ = live.extract_live([HIST, MDT])
    return report, warnings


def test_live_extraction_verifies_normalises_and_flags_conflicts(monkeypatch):
    r, warnings = _report(monkeypatch)
    assert r.icd10.value == "C50.4" and r.icd10.status == FieldStatus.found
    assert len({e.doc_id for e in r.icd10.evidence}) == 2  # both documents agree
    assert r.icd10.confidence >= 85
    assert r.laterality.value.value == "left"
    assert r.morphology_code.value == "8500/3"
    assert r.grade.status == FieldStatus.conflict and r.grade.value == "2" and r.grade.alternatives == ["3"]
    assert r.tnm_pathological.t.value == "1c" and r.tnm_pathological.n.value == "0"
    assert r.tnm_clinical.m.confidence <= 30  # quote not found in the document
    assert r.topography.value == "C50.4"
    assert warnings == []
    assert r.icd10.rules and r.icd10.rules[0].verified and r.icd10.rules[0].page == 108  # confirmed by MKN-10 rules
    assert any("potvrzen pravidly" in x for x in r.icd10.confidence_reasons)


def test_confirm_requires_empty_review_queue(monkeypatch, tmp_path):
    from app import store
    from app.config import get_settings
    from app.confidence import apply_review_policy
    from app.main import app

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    r, _ = _report(monkeypatch)
    now = datetime.now(timezone.utc)
    case = Case(id="c1", documents=[HIST, MDT], report=apply_review_policy(r), created_at=now, updated_at=now)
    store.save(case)
    client = TestClient(app)

    assert client.get("/api/cases/c1/uzis-export").status_code == 409  # not confirmed
    assert client.post("/api/cases/c1/confirm", json={"by": "MUDr. X"}).status_code == 409  # queue not empty

    queue = client.get("/api/cases/c1/review-queue").json()
    assert queue[0]["path"] == "grade"  # conflicts first
    report = client.get("/api/cases/c1").json()["report"]
    for item in queue:
        node = report
        for part in item["path"].split("."):
            node = node[part]
        node["review"]["state"] = "confirmed"
    assert client.put("/api/cases/c1/report", json=report).status_code == 200
    res = client.post("/api/cases/c1/confirm", json={"by": "MUDr. X"})
    assert res.status_code == 200 and res.json()["confirmed_by"] == "MUDr. X"
    export = client.get("/api/cases/c1/uzis-export").json()
    assert export["diagnoza"]["dg_mkn"] == "C50.4"
    assert export["diagnoza"]["lateralita"] == "2 - vlevo"
    assert export["morfologie"]["kod_morfologie"] == "8500/3"
