"""Lymph node counts (NOR "pN vyš." / "pN poz.") from the documents, per specimen, deterministically.

The LLM step returns node mentions as competing values and the most trusted source wins; but node counts from
different specimens (sentinel + non-sentinel, several dissection levels) add up. So:

- specimen: a histology report of a node specimen (topography axilla / SLN / node in the requisition), or a resection
  whose own findings state its node count ("počet a stav mízních uzlin: 18/3", "celkem vyšetřeno 21 uzlin");
  their counts are summed (identical findings, e.g. a repeated report, count once)
- reference: a sentinel result quoted inside another report (the resection conclusion repeating the SLN result) - not
  summed, only checked against the specimens
- summary: "N0 (0/3)", "N0 /3/0/" or "x/y uzlin" in an outpatient / MDT / discharge report - checks the total
- never counted: orphan fragments of the PDF layout (page "1/1", case numbers "1234/2026"), "uzlík" (a nodule)
"""

import hashlib
import re
from dataclasses import dataclass, field

from app.models import Document, Evidence

_NUMBER_WORDS = {"jedna": 1, "jedné": 1, "jeden": 1, "jedno": 1, "jednu": 1, "dvě": 2, "dva": 2, "tři": 3, "čtyři": 4,
                 "pět": 5, "šest": 6, "sedm": 7, "osm": 8, "devět": 9, "deset": 10}
_NUM = r"(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")"
_NODE = r"(?:lymfatick\w*\s+|mízní\w*\s+)?(?:uzlin(?!k)\w*|LU\b)"  # "uzlina/uzliny/uzlin", not "uzlík"
_NODE_WORDS = re.compile(r"(?i)uzlin(?!k)|\bLU\b|\bSLN\b|sentinel")
_SENTINEL = re.compile(r"(?i)sentinel|\bSLN\b")

_TOTAL = re.compile(rf"(?i)celkem\s+(?:vyšetřen\w*\s+)?{_NUM}\s+(?:\w+\s+){{0,2}}{_NODE}")
_EXAMINED = re.compile(rf"(?i)(?:vyšetřen\w*|dodán\w*)\s+(?:celkem\s+)?{_NUM}\s+(?:\w+\s+){{0,2}}{_NODE}")
# "v 1 LU mikrometastáza" counts the positive nodes, not the examined ones
_COUNT = re.compile(rf"(?i)(?<![\d,./])(?<!\bv\s){_NUM}\s+(?:[\w-]+\s+){{0,5}}{_NODE}")
_PAIR = re.compile(r"(?<![\d/])(\d{1,3})\s?/\s?(\d{1,3})(?![\d/])")
_POSITIVE = re.compile(rf"(?i)\bv\s+{_NUM}\s+{_NODE}[^.]{{0,80}}?(?:mikro)?metast")
_NEGATIVE = re.compile(r"(?i)bez\s+(?:známek|přítomnosti|zastižení)?\s*(?:malign|metast|nádor)|METASTAZA\s+NEPRITOMNA"
                       r"|žádná\s+pozitivní|bez\s+nádoru")
_SUMMARY = [
    re.compile(r"\bN\d\w*\s*\(\s*(\d{1,3})\s*/\s*(\d{1,3})\s*\)"),  # N0( 0/3)
    re.compile(r"\bN\d\w*\s*/\s*(\d{1,3})\s*/\s*(\d{1,3})\s*/"),  # N0 /3/0/
]
_FINDINGS = re.compile(r"(?im)^\s*(?:NÁLEZ|Makropopis|Mikropopis|Závěr|ZÁVĚR)\b")
_TOPOGRAPHY = re.compile(r"(?i)TOPOGRAFIE\s+ODBĚRU:\s*([^\n]*)")
_NODE_SITE = re.compile(r"(?i)axil|uzlin|lymf|\bSLN\b|sentinel")


def _int(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS[token.lower()]


@dataclass
class NodeCount:
    kind: str  # specimen | reference | summary
    doc: Document
    start: int
    end: int
    examined: int | None
    positive: int | None
    sentinel: bool = False

    @property
    def evidence(self) -> Evidence:
        return Evidence(doc_id=self.doc.id, quote=" ".join(self.doc.text[self.start:self.end].split()),
                        start=self.start, end=self.end, verified=True)

    def label(self) -> str:
        pos = "?" if self.positive is None else self.positive
        return f"{self.examined}/{pos} ({self.doc.filename})"


@dataclass
class NodeResult:
    specimens: list[NodeCount] = field(default_factory=list)
    references: list[NodeCount] = field(default_factory=list)
    summaries: list[NodeCount] = field(default_factory=list)

    @property
    def examined(self) -> int | None:
        return sum(c.examined for c in self.specimens) if self.specimens else None

    @property
    def positive(self) -> int | None:
        if not self.specimens or any(c.positive is None for c in self.specimens):
            return None
        return sum(c.positive for c in self.specimens)


def _sentence(text: str, start: int, end: int) -> tuple[int, int]:
    """The sentence (or line, for list items) around a match."""
    s = max(text.rfind(". ", 0, start) + 2, text.rfind("\n\n", 0, start) + 2, 0)
    e_dot, e_par = text.find(". ", end), text.find("\n\n", end)
    e = min(x for x in (e_dot + 1 if e_dot >= 0 else len(text), e_par if e_par >= 0 else len(text)))
    return s, e


def _is_node_specimen(doc: Document) -> bool:
    if m := _TOPOGRAPHY.search(doc.text):
        return bool(_NODE_SITE.search(m.group(1)))
    head = doc.text[: (f.start() if (f := _FINDINGS.search(doc.text)) else 0)]
    return bool(re.search(r"(?i)\bSLN\b|sentinel|uzlin(?!k)|lymfadenekt|disekc", head))


def _specimen_count(doc: Document, node_doc: bool) -> tuple[NodeCount | None, list[NodeCount]]:
    """The document's own node count (or None) and sentinel references to other specimens."""
    text = doc.text
    findings = (m.start() if (m := _FINDINGS.search(text)) else 0)
    candidates: list[tuple[int, int, int, int, int | None]] = []  # priority, examined, start, end, positive
    references: list[NodeCount] = []

    def consider(prio: int, examined: int, start: int, end: int, positive: int | None = None):
        s, e = _sentence(text, start, end)
        if not node_doc and _SENTINEL.search(text[s:e]):  # a resection quoting the sentinel result: a reference
            references.append(NodeCount("reference", doc, s, e, examined, positive, sentinel=True))
            return
        candidates.append((prio, examined, s, e, positive))

    for m in _TOTAL.finditer(text, findings):
        consider(3, _int(m.group(1)), m.start(), m.end())
    for m in _PAIR.finditer(text, findings):
        s, e = _sentence(text, m.start(), m.end())
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:line_end if line_end >= 0 else None].strip()
        if not _NODE_WORDS.search(text[s:e]) or re.fullmatch(r"\(?\d+\s?/\s?\d+\)?", line):
            continue  # orphan fragment of the layout ("1/1" page marker, a pair next to an unrelated sentence)
        a, b = int(m.group(1)), int(m.group(2))
        consider(2, max(a, b), m.start(), m.end(), min(a, b))
    for rx in (_EXAMINED, _COUNT):
        for m in rx.finditer(text, findings):
            consider(1, _int(m.group(1)), m.start(), m.end())

    if not candidates:
        return None, references
    prio, examined, s, e, positive = max(candidates, key=lambda c: (c[0], c[1]))
    if positive is None:
        body = text[findings:]
        if m := _POSITIVE.search(body):
            positive = _int(m.group(1))
        elif _NEGATIVE.search(body):
            positive = 0
    return NodeCount("specimen", doc, s, e, examined, positive, sentinel=bool(_SENTINEL.search(text[:findings] or text))), references


def count(docs: list[Document]) -> NodeResult:
    res = NodeResult()
    seen: set[str] = set()
    for doc in docs:
        if doc.kind == "histology":
            node_doc = _is_node_specimen(doc)
            spec, refs = _specimen_count(doc, node_doc)
            res.references += refs
            if spec:
                key = hashlib.sha1(" ".join(doc.text[spec.start:].split()).encode()).hexdigest()
                if key not in seen:  # the same findings in two reports (a repeated report) count once
                    seen.add(key)
                    res.specimens.append(spec)
        else:
            for rx in _SUMMARY:
                for m in rx.finditer(doc.text):
                    a, b = int(m.group(1)), int(m.group(2))
                    res.summaries.append(NodeCount("summary", doc, m.start(), m.end(), max(a, b), min(a, b)))
    return res


def check(res: NodeResult) -> list[str]:
    """Disagreements: summaries vs. the specimen total; sentinel references vs. any specimen (warnings)."""
    out = []
    total = res.examined
    if total is None:
        return out
    for s in res.summaries:
        if s.examined != total or (res.positive is not None and s.positive != res.positive):
            out.append(f"souhrn {s.examined}/{s.positive} v {s.doc.filename} × histologie {total}/"
                       f"{'?' if res.positive is None else res.positive} ({' + '.join(c.label() for c in res.specimens)})")
    counts = {c.examined for c in res.specimens} | {total}
    for r in res.references:
        if r.examined not in counts:
            out.append(f"odkaz {r.examined}/{'?' if r.positive is None else r.positive} v {r.doc.filename} "
                       f"neodpovídá žádnému vzorku ({' + '.join(c.label() for c in res.specimens)})")
    return out
