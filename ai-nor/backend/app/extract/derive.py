"""Deterministic findings for derived NOR fields: explicit clinical M, negative staging, biopsy and treatment dates.

Nothing here is inferred from silence: an M category or a date is only taken where the text states it.
"""

import re
from dataclasses import dataclass

from app.models import Document, Evidence, PartialDate


@dataclass
class Hit:
    value: object
    doc: Document
    start: int
    end: int
    kind: str = ""

    @property
    def evidence(self) -> Evidence:
        return Evidence(doc_id=self.doc.id, quote=" ".join(self.doc.text[self.start:self.end].split()),
                        start=self.start, end=self.end, verified=True)


# --- clinical M ---------------------------------------------------------------------------------------------------
# an M token inside a TNM string ("pT1c N0( 0/3)M0", "cT1c cN0 M0"); pM is the pathologist's (open question, left out),
# "M1: M85203" (morphology code footer) is not an M category
_M_TOKEN = re.compile(r"(?<![A-Za-z])c?M([01Xx])(?:[a-d])?(?![\w:])")  # "Mx" is usually written lowercase
_TNM_CONTEXT = re.compile(r"\b[cpy]{0,2}T(?:is|[0-4X])|\b[cpy]{0,2}N[0-3X]")
_NEGATIVE_STAGING = re.compile(
    r"(?i)bez\s+(?:známek\s+)?(?:generalizace|vzdálen\w*\s+meta\w*|meta\w*)"
    r"|staging\w*[^.\n]{0,60}negat"
    r"|\b(?:SONO|USG|CT|PET(?:/CT)?|RTG|scint\w*)\b[^.\n]{0,60}?(?:negat|bez\s+(?:patolog|meta|ložisk))"
)


def explicit_m(docs: list[Document]) -> list[Hit]:
    """Clinical M categories written in TNM strings (outside histology reports, where Mx is the pathologist's)."""
    hits = []
    for doc in docs:
        for line_m in re.finditer(r"[^\n]+", doc.text):
            line = line_m.group(0)
            if not _TNM_CONTEXT.search(line) or doc.kind == "histology":
                continue
            for m in _M_TOKEN.finditer(line):
                if line[max(0, m.start() - 1)] == "p":  # pM
                    continue
                hits.append(Hit(m.group(1).upper(), doc, line_m.start() + m.start(), line_m.start() + m.end(), "tnm"))
    return hits


def negative_staging(docs: list[Document]) -> list[Hit]:
    """Statements that the staging found no distant disease ("bez známek generalizace", "SONO břicha … negat.")."""
    return [Hit("0", doc, m.start(), m.end(), "staging") for doc in docs for m in _NEGATIVE_STAGING.finditer(doc.text)]


# --- dates --------------------------------------------------------------------------------------------------------
_DATE = re.compile(r"(?<!\d)(\d{1,2})\s?[.,]\s?(\d{1,2})\s?[.,]\s?((?:19|20)\d{2})(?!\d)")
_BIOPSY = re.compile(r"(?i)\bCCB\b|core\s*cut|biops|punkc|\bFNAB?\b|tru-?cut|vakuov\w*\s+biops")
TREATMENTS = [
    ("surgery", re.compile(r"(?i)\bBCS\b|mastektom|resekc|reexciz|exstirp|operac|lumpe[ck]tom|\bSLNB?\b|ablac|\w+ektomi")),
    ("systemic", re.compile(r"(?i)\bCHT\b|chemoter|\bHT\b|hormonál\w*\s+léč|imunoter")),
    ("radiotherapy", re.compile(r"(?i)\bRT\b|radioter|ozař")),
]


# "CHT odložena", "plánována operace", "indikována RT": not (yet) done, so not a start of treatment
_NOT_DONE = re.compile(r"(?i)odlož|plánov|indikov|doporuč|zvážit|zvažov|nebud|neprovede|objedn")


def _dated(docs: list[Document], keyword: re.Pattern, kind: str) -> list[Hit]:
    """Dates written next to a keyword on the same line (within 40 characters): "7,5,2026 BCS + SLN", "19.3.2026 CCB"."""
    out = []
    for doc in docs:
        for line_m in re.finditer(r"[^\n]+", doc.text):
            line = line_m.group(0)
            for d in _DATE.finditer(line):
                k = keyword.search(line)
                if not k or min(abs(k.start() - d.end()), abs(d.start() - k.end())) > 40:
                    continue
                if _NOT_DONE.search(line[max(0, k.start() - 25):k.end() + 25]):
                    continue
                day, month, year = int(d.group(1)), int(d.group(2)), int(d.group(3))
                if 1 <= day <= 31 and 1 <= month <= 12:
                    out.append(Hit(PartialDate(year=year, month=month, day=day), doc,
                                   line_m.start() + min(d.start(), k.start()), line_m.start() + max(d.end(), k.end()), kind))
    return out


def _key(d: PartialDate) -> tuple[int, int, int]:
    return d.year, d.month or 1, d.day or 1


def first_biopsy(docs: list[Document]) -> Hit | None:
    hits = _dated(docs, _BIOPSY, "biopsy")
    return min(hits, key=lambda h: _key(h.value)) if hits else None


def first_treatment(docs: list[Document]) -> Hit | None:
    hits = [h for kind, rx in TREATMENTS for h in _dated(docs, rx, kind)]
    return min(hits, key=lambda h: _key(h.value)) if hits else None
