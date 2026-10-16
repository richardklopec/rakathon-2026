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


# --- Dg. MKN: requisition codes, differing codes, subsite from the site description (synthetic texts)
REQ = "PRŮVODNÍ LIST K ZÁSILCE BIOPTICKÉHO MATERIÁLU\nKlinická diagnóza:C509\nKLIN. DIAG.:\nca. prsu - DKK vpravo\nDIAGNÓZA: C509\nNÁLEZ:\nMakropopis: tkáň prsu\nZávěr: invazivní karcinom NST"
H1 = Document(id="h1", filename="H1.pdf", kind="histology", text=REQ)
H2 = Document(id="h2", filename="H2.pdf", kind="histology", text=REQ.replace("Makropopis: tkáň prsu", "Makropopis: uzlina"))
AZ = Document(id="a", filename="AZ.pdf", kind="AZ", text="Dg.: C504 ca prsu vpravo\nst. p. resekci")
MD = Document(id="d", filename="MDT.pdf", kind="MDT", text="drobné ložisko na rozhraní DKK vpravo")
C50_FULL = RuleHit(kind="category", code="C50", title="Zhoubný novotvar prsu", page=108, score=1.0,
                   text="C50 Zhoubný novotvar prsu\nC50.4 Horní zevní kvadrant prsu\nC50.8 Léze přesahující prs\nC50.9 Prs NS")
NOTE = RuleHit(kind="note", code="C00–D48", title="NOVOTVARY", page=91, score=1.0,
               text="Novotvar, který přesahuje dvě nebo více souvisejících lokalizací, musí být zařazen do podpoložky .8")


def _coded(monkeypatch, choice: CodeChoice, docs: list[Document], icd_mentions):
    from app.extract import coder

    def llm(system, user, schema):
        if schema is CodeChoice:
            return choice
        return LlmExtraction(primary_tumour="karcinom prsu vpravo", other_tumours=[], patient_sex="F",
                             fields=[FieldMentions(field="icd10", mentions=[Mention(doc=d, quote=q, value=v, explicit=True, hedged=False)
                                                                           for d, q, v in icd_mentions])])

    monkeypatch.setattr(live.llm, "structured", llm)
    monkeypatch.setattr(coder, "_default_candidates", lambda q, lit: ([C50_FULL], [NOTE]))
    report, warnings, _ = live.extract_live(docs)
    return report, warnings


def test_requisition_codes_differing_codes_and_described_site(monkeypatch):
    choice = CodeChoice(code="C50.8", rule_code="C00–D48", rule_quote="musí být zařazen do podpoložky .8", reasoning="Rozhraní dolních kvadrantů.", certain=True)
    r, warnings = _coded(monkeypatch, choice, [H1, H2, AZ, MD],
                         [(1, "Klinická diagnóza:C509", "C509"), (2, "DIAGNÓZA: C509", "C509"), (3, "Dg.: C504", "C504")])
    assert any(w.startswith("Rozpor kódů diagnózy v dokumentech: C50.9 (H1.pdf – žádanka, H2.pdf – žádanka); C50.4 (AZ.pdf)") for w in warnings)
    assert r.icd10.value == "C50.8" and r.icd10.status == FieldStatus.conflict and r.icd10.confidence <= 60
    assert r.icd10.alternatives[0] == "C50.4"  # the requisitions (45, one source) lost to the AZ (50) before the rules step
    assert any("popis lokalizace odpovídá" in x for x in r.icd10.confidence_reasons)
    assert any(e.doc_id == "d" for e in r.icd10.evidence)  # the site description is cited
    assert r.topography.value == "C50.8"


def test_quoted_rule_must_support_the_code(monkeypatch):
    # the coder confirms the written code but quotes a rule for another sub-code
    choice = CodeChoice(code="C50.4", rule_code="C50", rule_quote="C50.8 Léze přesahující prs", reasoning="", certain=True)
    r, _ = _coded(monkeypatch, choice, [HIST, MDT], [(1, "Diagnóza: C504", "C504"), (2, "Dg.: C50.4", "C50.4")])
    assert r.icd10.value == "C50.4" and r.icd10.confidence <= 60
    assert any("nepodporuje" in x for x in r.icd10.confidence_reasons)
    assert not any("potvrzen pravidly" in x for x in r.icd10.confidence_reasons)


def test_not_specified_code_against_a_described_site(monkeypatch):
    choice = CodeChoice(code="C50.9", rule_code="C50", rule_quote="C50.9 Prs NS", reasoning="", certain=True)
    r, warnings = _coded(monkeypatch, choice, [AZ.model_copy(update={"text": "Dg.: C509"}), MD], [(1, "Dg.: C509", "C509")])
    assert r.icd10.value == "C50.9" and r.icd10.confidence <= 60  # NS although the documents describe the site
    assert r.icd10.alternatives[:1] == ["C50.8"]
    assert any("neodpovídá kódu C50.9" in x for x in r.icd10.confidence_reasons)


def test_code_guessed_by_the_model_is_not_a_written_code(monkeypatch):
    choice = CodeChoice(code="C50.4", rule_code="C50", rule_quote="C50.4 Horní zevní kvadrant prsu", reasoning="", certain=True)
    mdt = Document(id="d", filename="MDT.pdf", kind="MDT", text="Ca prsu vpravo, HZK")
    r, warnings = _coded(monkeypatch, choice, [AZ, mdt], [(1, "Dg.: C504", "C504"), (2, "Ca prsu vpravo", "C50.9")])
    assert not any(w.startswith("Rozpor kódů") for w in warnings)  # MDT has no code, only words
    assert r.icd10.value == "C50.4"
