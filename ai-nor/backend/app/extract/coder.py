"""Second LLM step: choose the MKN-10 code with the coding rules of the MKN-10 Tabelární část (PLAN.md §3.1, variant B).

Candidates come from IRIS (literal code from the documents, MKN-10 code-list search in Nor.Code, rule search in Nor.Rule);
the LLM picks one sub-code and must quote the rule it used. The code is then validated against the 2026 CSV and the
quote against the rule texts, so neither a non-existent code nor an invented rule can get through.
"""

import re
import unicodedata
from collections.abc import Callable

from pydantic import BaseModel

from app import llm
from app.models import RuleRef
from app.validate import mkn10


class CodeChoice(BaseModel):
    # field order matters: the model writes the reasoning first and the code last (otherwise code and reasoning can disagree)
    reasoning: str  # one or two sentences in Czech
    rule_code: str  # category or note the decision relies on, e.g. "C50" or "C00–D48"
    rule_quote: str  # verbatim quote from the provided rules (sub-code line, Patří sem / Nepatří sem, note)
    code: str  # chosen MKN-10 code with dot, e.g. C50.4 (or "" when it cannot be decided)
    certain: bool  # False when the documents do not allow a clear choice


class CoderResult(BaseModel):
    code: str
    valid: bool
    rule: RuleRef | None
    reasoning: str
    certain: bool


SYSTEM = """Jsi zkušený kódovač Národního onkologického registru. Podle pravidel MKN-10 (Tabelární část) přiřadíš
hlášenému nádoru JEDEN kód MKN-10 s podpoložkou (např. C50.4).

Pravidla:
1. Vybírej jen z podpoložek kandidátních kategorií, které dostaneš. Když nelze rozhodnout, vrať code "" a certain=false.
2. Respektuj „Patří sem / Nepatří sem“ a poznámky kapitoly II (např. poznámka 5: léze přesahující více podpoložek → .8).
3. Kód uvedený v dokumentaci ber jako silné vodítko. Oprav ho jen tehdy, když odporuje pravidlům nebo citacím, nebo v MKN-10
   neexistuje. Chybějící detail v citacích není důvod ke změně.
4. Kategorie bez podpoložek (např. C61, C64) se kóduje třímístně.
   Zkratky kvadrantů prsu: HZK/ZHK = horní zevní (.4), HVK/VHK = horní vnitřní (.2), DZK/ZDK = dolní zevní (.5),
   DVK/VDK = dolní vnitřní (.3); HKK / DKK / ZKK / VKK = oblast dvou kvadrantů (horních / dolních / zevních / vnitřních).
   Výslovné „rozhraní“ dvou kvadrantů bez kódu v dokumentaci → léze přesahující → .8. Pozor: DKK / HKK mimo popis prsu
   znamená dolní / horní končetiny.
5. reasoning napiš nejdřív, code musí odpovídat závěru reasoning.
6. rule_quote = DOSLOVNÁ krátká citace z dodaných pravidel (řádek podpoložky, Patří sem / Nepatří sem nebo věta z poznámky).
7. reasoning: jedna až dvě věty česky, proč tento kód."""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^\w]+", " ", s).strip()


def _default_candidates(query: str, literal: str | None):
    from app.retrieval.rules import candidate_categories, chapter_notes

    return candidate_categories(query, literal), chapter_notes()


def choose_icd10(
    primary_tumour: str,
    quotes: list[str],
    literal: str | None,
    candidates: Callable | None = None,  # (query, literal) -> (categories, notes); default: IRIS
) -> CoderResult | None:
    query = " ".join([primary_tumour, *quotes])[:600]
    cats, notes = (candidates or _default_candidates)(query, literal)
    if not cats:
        return None
    rules_text = "\n\n".join(f"### {c.code} (str. {c.page})\n{c.text}" for c in cats)
    notes_text = "\n".join(n.text for n in notes)
    user = (
        f"Hlášený nádor: {primary_tumour}\n"
        f"Kód MKN-10 uvedený v dokumentaci: {literal or 'není'}\n"
        "Citace z dokumentace:\n" + "\n".join(f"- {q}" for q in quotes[:12]) +
        f"\n\n## Kandidátní kategorie MKN-10\n{rules_text}\n\n## Poznámky kapitoly II (Novotvary)\n{notes_text}"
    )
    choice = llm.structured(SYSTEM, user, CodeChoice)
    code = mkn10_code(choice.code)
    if code and not mkn10.is_valid(code) and mkn10.is_valid(code[:3]):
        code = code[:3]  # category without sub-codes (C64.9 -> C64)
    if not code:
        return CoderResult(code="", valid=False, rule=None, reasoning=choice.reasoning, certain=False)

    # verify the quote against the rule texts we actually sent
    rule = None
    nq = _norm(choice.rule_quote)
    if len(nq) >= 4:
        for entry in [*cats, *notes]:
            if nq in _norm(entry.text):
                rule = RuleRef(code=entry.code, page=entry.page, quote=choice.rule_quote.strip(), verified=True)
                break
    if rule is None and choice.rule_quote:
        rule = RuleRef(code=choice.rule_code, page=None, quote=choice.rule_quote.strip(), verified=False)
    in_candidates = code[:3] in {c.code for c in cats}
    return CoderResult(
        code=code,
        valid=bool(mkn10.is_valid(code)) and in_candidates,
        rule=rule,
        reasoning=choice.reasoning,
        certain=choice.certain,
    )


def mkn10_code(text: str) -> str | None:
    from app.validate.normalize import icd10

    return icd10(text) if text else None
