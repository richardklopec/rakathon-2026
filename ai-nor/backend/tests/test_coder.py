"""MKN-10 coder (variant B): the code must exist and come from the candidates, the rule quote must be in the rules."""

from app.extract import coder
from app.extract.coder import CodeChoice, choose_icd10
from app.retrieval.rules import RuleHit

C50 = RuleHit(
    kind="category", code="C50", title="Zhoubný novotvar prsu", page=108, score=1.0,
    text="C50 Zhoubný novotvar prsu\nNepatří sem: kůže prsu (C43.5‚ C44.5)\nC50.4 Horní zevní kvadrant prsu\nC50.8 Léze přesahující prs",
)
NOTE = RuleHit(
    kind="note", code="C00–D48", title="NOVOTVARY (C00–D48)", page=91, score=1.0,
    text="Novotvar‚ který přesahuje dvě nebo více souvisejících lokalizací uvnitř třímístné položky a jehož místo vzniku nelze určit‚ musí být zařazen do podpoložky .8",
)


def fake_candidates(query, literal):
    return [C50], [NOTE]


def run(monkeypatch, choice: CodeChoice):
    monkeypatch.setattr(coder.llm, "structured", lambda system, user, schema: choice)
    monkeypatch.setattr(coder.mkn10, "is_valid", lambda code: code in {"C50.4", "C50.8", "C44.5"})
    return choose_icd10("karcinom prsu vlevo", ["Dg.: C50.4"], "C50.4", candidates=fake_candidates)


def test_valid_code_with_verified_rule(monkeypatch):
    res = run(monkeypatch, CodeChoice(code="C50.4", rule_code="C50", rule_quote="C50.4 Horní zevní kvadrant prsu", reasoning="Horní zevní kvadrant.", certain=True))
    assert res.valid and res.code == "C50.4"
    assert res.rule.verified and res.rule.page == 108


def test_note_quote_is_located(monkeypatch):
    res = run(monkeypatch, CodeChoice(code="C50.8", rule_code="C00–D48", rule_quote="musí být zařazen do podpoložky .8", reasoning="Přesahuje dva kvadranty.", certain=True))
    assert res.valid and res.rule.verified and res.rule.code == "C00–D48" and res.rule.page == 91


def test_code_outside_candidates_or_invented_quote_is_not_trusted(monkeypatch):
    res = run(monkeypatch, CodeChoice(code="C44.5", rule_code="C44", rule_quote="Kůže trupu", reasoning="", certain=True))
    assert not res.valid  # C44 was not among the candidate categories
    assert res.rule is not None and not res.rule.verified  # quote not in the rules we sent


def test_undecided(monkeypatch):
    res = run(monkeypatch, CodeChoice(code="", rule_code="", rule_quote="", reasoning="Nelze určit.", certain=False))
    assert res.code == "" and not res.valid
