"""Step 4: explicit clinical M, negative staging, biopsy / treatment dates, derived stage and date (synthetic texts)."""

from app.confidence import apply_review_policy, review_queue
from app.extract import derive, live
from app.extract.coder import CodeChoice
from app.extract.live import FieldMentions, LlmExtraction, Mention
from app.models import Document, FieldStatus, PartialDate
from app.validate import consistency
from app.validate.normalize import partial_date


def _d(name, kind, text):
    return Document(id=name, filename=name, kind=kind, text=text)


AZ = _d("AZ.pdf", "AZ", "Dg.: C504\nCa mammae vlevo pT1c N0( 0/3)M0\nst. localis bpn")
MDT = _d("MDT.pdf", "MDT", "SONO břicha a RTG plic: negativní\n7,5,2026 BCS + SLN l.sin.\nTNM: pT1c N0 /3/0/ Mx")
HIST = _d("H.pdf", "histology", "Závěr:\n9. TNM: pT1c N0 Mx\nM1: M85203 KARCINOM")


def test_explicit_m_only_from_clinical_tnm_strings():
    assert [(h.value, h.doc.filename) for h in derive.explicit_m([AZ, MDT, HIST])] == [("0", "AZ.pdf"), ("X", "MDT.pdf")]
    assert derive.explicit_m([_d("x", "AZ", "pT2 pN1 pM1 bez dalšího")]) == []  # pM is the pathologist's (open question)
    assert derive.explicit_m([_d("x", "AZ", "M1: M85203 KARCINOM")]) == []  # morphology code footer, no TNM around


def test_negative_staging_and_dates():
    assert [h.doc.filename for h in derive.negative_staging([AZ, MDT])] == ["MDT.pdf"]
    assert derive.negative_staging([_d("x", "AZ", "CT hrudníku: bez známek generalizace")])
    t = derive.first_treatment([MDT])
    assert t.kind == "surgery" and t.value == PartialDate(year=2026, month=5, day=7)
    b = derive.first_biopsy([_d("a", "AZ", "19.3.2026 CCB - invazivní karcinom\n7,5,2026 BCS")])
    assert b.value == PartialDate(year=2026, month=3, day=19)
    assert derive.first_treatment([_d("p", "MDT", "11.6.2026 CHT odložena\nplánována operace 5.5.2026")]) is None
    assert partial_date("7,5,2026 BCS") == PartialDate(year=2026, month=5, day=7)
    assert partial_date("tumor 2,5 cm") is None


def _run(monkeypatch, docs, extra_fields=()):
    def llm(system, user, schema):
        if schema is CodeChoice:
            return CodeChoice(code="C50.4", rule_code="C50", rule_quote="C50.4 Horní zevní kvadrant prsu", reasoning="", certain=True)
        m = lambda doc, q, v: Mention(doc=doc, quote=q, value=v, explicit=True, hedged=False)  # noqa: E731
        return LlmExtraction(primary_tumour="karcinom prsu vlevo", other_tumours=[], patient_sex="F", fields=[
            FieldMentions(field="icd10", mentions=[m(1, "Dg.: C504", "C504")]),
            FieldMentions(field="pT", mentions=[m(1, "pT1c N0( 0/3)M0", "pT1c")]),
            FieldMentions(field="pN", mentions=[m(1, "pT1c N0( 0/3)M0", "N0")]),
            FieldMentions(field="pM", mentions=[m(2, "TNM: pT1c N0 /3/0/ Mx", "Mx")]),
            *extra_fields,
        ])

    from app.extract import coder
    from app.retrieval.rules import RuleHit
    rule = RuleHit(kind="category", code="C50", title="Prs", page=108, score=1.0, text="C50.4 Horní zevní kvadrant prsu")
    monkeypatch.setattr(live.llm, "structured", llm)
    monkeypatch.setattr(coder, "_default_candidates", lambda q, lit: ([rule], []))
    return live.extract_live(docs)


def test_derived_m_stage_extent_and_date(monkeypatch):
    r, _, _ = _run(monkeypatch, [AZ, MDT])
    cm = r.tnm_clinical.m
    assert cm.value == "0" and cm.confidence == live.CLINICAL_M_CAP  # explicit M0 65 + staging 10 = 75, still for review
    assert any("M0 výslovně v TNM (AZ.pdf, 65)" in x for x in cm.confidence_reasons)
    assert any("staging bez vzdálených metastáz" in x for x in cm.confidence_reasons)
    assert r.clinical_stage.value == "IA"
    how = next(x for x in r.clinical_stage.confidence_reasons if x.startswith("odvozeno"))
    # the explanation says which organ table was used and what every input rests on
    assert how.startswith("odvozeno pro prs (C50.4, tabulka UICC TNM 8): pT1c (2 zprávy) + pN0 (2 zprávy) + cM0 (AZ.pdf: „pT1c N0( 0/3)M0“")
    assert "MDT.pdf: „SONO břicha a RTG plic: negativní“" in how and how.endswith("→ IA")
    assert any("výsledek je výpočet" in x for x in r.clinical_stage.confidence_reasons)
    assert not any(x == "✓ citace ověřena" for x in r.clinical_stage.confidence_reasons)
    # the stage cites every place its inputs were read from, not just the first of each
    inputs = {(e.doc_id, e.start, e.end) for f in (r.tnm_pathological.t, r.tnm_pathological.n, cm) for e in f.evidence}
    assert {(e.doc_id, e.start, e.end) for e in r.clinical_stage.evidence} == inputs and len(inputs) > 3
    assert len(r.clinical_stage.evidence) == len(inputs)  # one TNM string read for pT, pN and M is one source
    assert r.disease_extent.value == "1"  # from cM0, not from the MX in the MDT
    assert r.diagnosis_date.value == PartialDate(year=2026, month=5, day=7)
    assert r.diagnosis_date.confidence == 60 and any("zahájení léčby" in x for x in r.diagnosis_date.confidence_reasons)
    assert r.treatments[0].kind == "surgery"
    r = apply_review_policy(r)
    assert not any(path.startswith("treatments") for path, _ in review_queue(r))  # never blocks the confirmation
    assert r.tnm_clinical.m.needs_review and r.diagnosis_date.needs_review


def test_mx_alone_derives_nothing(monkeypatch):
    r, _, _ = _run(monkeypatch, [_d("AZ.pdf", "AZ", "Dg.: C504\npT1c N0 Mx"), _d("MDT.pdf", "MDT", "TNM: pT1c N0 /3/0/ Mx")])
    assert r.tnm_clinical.m.status == FieldStatus.missing
    assert r.disease_extent.status == FieldStatus.missing  # MX never means "lokalizované"
    assert r.clinical_stage.status == FieldStatus.missing  # no stage without an explicit M


def test_stated_stage_checked_against_tnm(monkeypatch):
    az = AZ.model_copy(update={"text": AZ.text + "\nKlinické stádium IIA"})
    stated = FieldMentions(field="clinical_stage", mentions=[Mention(doc=1, quote="Klinické stádium IIA", value="IIA", explicit=True, hedged=False)])
    r, _, _ = _run(monkeypatch, [az, MDT], [stated])
    assert r.clinical_stage.value == "IIA" and r.clinical_stage.status == FieldStatus.conflict
    assert r.clinical_stage.alternatives == ["IA"]


def test_later_stated_date_gets_the_treatment_date_as_alternative(monkeypatch):
    late = FieldMentions(field="diagnosis_date", mentions=[Mention(doc=2, quote="7,5,2026 BCS", value="30.9.2026", explicit=True, hedged=False)])
    r, _, _ = _run(monkeypatch, [AZ, MDT], [late])
    assert r.diagnosis_date.value == PartialDate(year=2026, month=9, day=30)
    assert r.diagnosis_date.alternatives[0] == PartialDate(year=2026, month=5, day=7)
    assert "diagnosis_after_treatment" in {v.rule for v in consistency.check(r)}


def test_aromatase_inhibitor_is_not_a_stage(monkeypatch):
    az = AZ.model_copy(update={"text": AZ.text + "\nod 3/2026 hormonoterapie IA"})
    misread = FieldMentions(field="clinical_stage", mentions=[Mention(doc=1, quote="od 3/2026 hormonoterapie IA", value="IA", explicit=True, hedged=False)])
    r, _, _ = _run(monkeypatch, [az, MDT], [misread])
    cs = r.clinical_stage
    assert cs.value == "IA"  # still IA, but computed from TNM, not read from the therapy line
    assert not any("hormonoterapie" in e.quote for e in cs.evidence)
    assert any(x.startswith("odvozeno pro prs (C50.4") and x.endswith("→ IA") for x in cs.confidence_reasons)


def test_tnm_of_an_earlier_tumour_is_not_the_m_of_this_one(monkeypatch):
    az = AZ.model_copy(update={"text": "I. r. 2004 Ca recta, pT3N0M1\n" + AZ.text})
    r, _, _ = _run(monkeypatch, [az, MDT])
    cm = r.tnm_clinical.m
    assert cm.value == "0" and cm.status == FieldStatus.found  # the M1 of the earlier pT3 tumour is not a conflict
    assert all("pT3" not in e.quote for e in cm.evidence)
