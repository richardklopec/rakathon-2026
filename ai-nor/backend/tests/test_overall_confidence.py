from datetime import datetime, timezone

from app.confidence import apply_review_policy, overall
from app.models import Case, Evidence, Extracted, FieldStatus, NorReport, ReviewState

EV = [Evidence(doc_id="d", quote="x", start=0, end=1, verified=True)]


def _f(value, confidence, status=FieldStatus.found):
    return Extracted[str](value=value, status=status, confidence=confidence, evidence=EV)


def test_weighted_score_and_counts():
    r = NorReport(
        icd10=_f("C50.4", 90),  # mandatory: weight 2
        morphology_name=_f("karcinom", 60),  # optional: weight 1
        grade=_f("2", 70, FieldStatus.conflict),  # mandatory, conflict
    )
    r = apply_review_policy(r)
    o = overall(r)
    assert r.grade.confidence == 60  # conflict cap (CONFLICT_CAP)
    assert o.score == round((2 * 90 + 60 + 2 * 60) / 5)  # 72
    assert o.level == "střední"
    assert (o.fields_ai, o.auto_accepted, o.to_review, o.conflicts) == (3, 1, 2, 1)
    assert o.missing_required == 7  # 9 mandatory fields, icd10 + grade filled


def test_human_edits_leave_the_score():
    r = apply_review_policy(NorReport(icd10=_f("C50.4", 95), grade=_f("2", 40)))
    r.grade.value, r.grade.review.state = "3", ReviewState.edited
    o = overall(r)
    assert o.score == 95 and o.edited_by_human == 1 and o.to_review == 0
    assert overall(NorReport()).score is None


def test_case_exposes_score():
    now = datetime.now(timezone.utc)
    case = Case(id="c", report=apply_review_policy(NorReport(icd10=_f("C50.4", 90))), created_at=now, updated_at=now)
    dumped = case.model_dump()
    assert dumped["ai_confidence"]["score"] == 90
    assert Case.model_validate(dumped).ai_confidence.score == 90  # stored JSON with the computed field loads back


def test_conflict_cap_is_applied_once_and_never_raises():
    r = apply_review_policy(NorReport(icd10=_f("C34.9", 100, FieldStatus.conflict), grade=_f("2", 40, FieldStatus.conflict)))
    assert r.icd10.confidence == 60 and r.icd10.needs_review
    assert r.grade.confidence == 40  # already below the cap
    r = apply_review_policy(r)  # PUT /report applies the policy again
    assert sum("odporují" in x for x in r.icd10.confidence_reasons) == 1
