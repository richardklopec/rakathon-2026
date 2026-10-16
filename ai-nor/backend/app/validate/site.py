"""Deterministic subsite (4th character of the MKN-10 code) from the site descriptions in the documents.

A second, independent opinion next to the LLM coder: it never picks the code itself, it says which subsites the
documents describe, so the chosen code can be checked against them. Table-driven by category; breast (C50) first.
"""

import re
from dataclasses import dataclass

from app.models import Document, Evidence


@dataclass
class SiteRule:
    subsite: str  # ".4"
    label: str  # Czech, for the warning
    pattern: re.Pattern


def _rx(words: str, abbr: str = "") -> re.Pattern:
    # words: case-insensitive; abbreviations (HZK, DKK…): case-sensitive, so "dkk" in other contexts does not match
    parts = [rf"(?i:{words})"] + ([rf"\b(?:{abbr})\b"] if abbr else [])
    return re.compile("|".join(parts))


RULES: dict[str, list[SiteRule]] = {
    "C50": [
        SiteRule(".0", "bradavka / dvorec", _rx(r"(?<!od )(?:bradav|(?<!retro)(?<!sub)areol|mamil)")),
        SiteRule(".1", "centrální část", _rx(r"centráln\w* část|retroareol|subareol")),
        SiteRule(".2", "horní vnitřní kvadrant", _rx(r"horní\w* vnitřní\w* kvadrant", "HVK|VHK")),
        SiteRule(".3", "dolní vnitřní kvadrant", _rx(r"doln\w* vnitřní\w* kvadrant", "DVK|VDK")),
        SiteRule(".4", "horní zevní kvadrant", _rx(r"horní\w* zevní\w* kvadrant", "HZK|ZHK")),
        SiteRule(".5", "dolní zevní kvadrant", _rx(r"doln\w* zevní\w* kvadrant", "DZK|ZDK")),
        SiteRule(".6", "axilární výběžek", _rx(r"axilární\w* výběž|Spence")),
        # two quadrants named together (HKK = both upper ones…) or an explicit border: overlapping lesion
        # ("přesahující" alone is left out: it often means size or growth into the skin, not two subsites)
        SiteRule(".8", "rozhraní / přesah kvadrantů", _rx(r"rozhraní|na hranici kvadrant|(?:více|dvou|obou)\s+\w*\s*kvadrant", "HKK|DKK|ZKK|VKK")),
    ],
}
# the line must be about the tumour itself, not just the breast: "DKK bez otoků" (lower limbs) or the physical exam
# "bradavka bpn" must not count as the tumour site
CONTEXT = {"C50": re.compile(r"(?i)ložisk|tumor|\bTU\b|\bca\b|karcinom|nádor|léz[ei]|útvar|infiltr|\bklip")}
# a site followed by a normal finding is an examination, not the site of the tumour ("bradavka bpn", "HZK bez rezistence")
_NORMAL_AFTER = re.compile(r"(?i)\W{0,3}(bpn|b\.\s?p\.\s?n|bez\b|klidn|norm|nepostiž)")


def _word_end(line: str, pos: int) -> int:
    """Patterns match word stems ("bradav"): check what follows the whole word ("bradavka bpn")."""
    while pos < len(line) and line[pos].isalnum():
        pos += 1
    return pos


def _matches(category: str, docs: list[Document]):
    """(subsite, document, line start, line end) for every tumour-site description."""
    rules, context = RULES.get(category), CONTEXT.get(category)
    if not rules:
        return
    for doc in docs:
        pos = 0
        for line in doc.text.split("\n"):
            start, pos = pos, pos + len(line) + 1
            if not context.search(line):
                continue
            for rule in rules:
                if any(not _NORMAL_AFTER.match(line, _word_end(line, m.end())) for m in rule.pattern.finditer(line)):
                    yield rule.subsite, doc, start, start + len(line)


def subsites(category: str, docs: list[Document]) -> dict[str, list[str]]:
    """Subsite -> files whose site descriptions point to it ({".8": ["MDT.pdf"], ".4": ["AZ.pdf"]})."""
    found: dict[str, list[str]] = {}
    for subsite, doc, _, _ in _matches(category, docs):
        if doc.filename not in found.setdefault(subsite, []):
            found[subsite].append(doc.filename)
    return found


def evidence(code: str, docs: list[Document]) -> list[Evidence]:
    """The description lines that support the code's subsite (first one per document), as verified citations."""
    category, _, sub = code.partition(".")
    out, seen = [], set()
    for subsite, doc, start, end in _matches(category, docs):
        if subsite == f".{sub}" and doc.id not in seen:
            seen.add(doc.id)
            out.append(Evidence(doc_id=doc.id, quote=doc.text[start:end].strip(), start=start, end=end, verified=True))
    return out


def label(category: str, subsite: str) -> str:
    return next((r.label for r in RULES.get(category, []) if r.subsite == subsite), subsite)


def check(code: str, docs: list[Document]) -> tuple[bool | None, dict[str, list[str]]]:
    """(supported, subsites): True = the code's subsite is described, False = the documents describe other subsites
    (or the code says NS while they are specific), None = no description to compare with / category not covered."""
    category, _, sub = code.partition(".")
    found = subsites(category, docs)
    if not found:
        return None, found
    return (f".{sub}" in found if sub and sub != "9" else False), found
