"""Extraction pipeline: documents -> NorReport with evidence.

`mock` mode uses deterministic regexes (enough for UI work and tests).
`live` mode is where the LLM extraction per field group goes (TODO during the hackathon):
retrieve passages (IRIS vector search) -> llm.structured(...) -> attach evidence offsets -> validate.
"""

import re

from app.config import get_settings
from app.models import Coding, Document, Evidence, Extracted, FieldStatus, NorReport
from app.validate.mkn10 import ICD10_SYSTEM, lookup

_ICD10 = re.compile(r"\bC\d{2}(?:\.?\d{1,2})?\b")
_ICDO_MORPH = re.compile(r"\bM?(8\d{3})(\d)\b")  # histology footer, e.g. "M1: M81403"
_PTNM = re.compile(r"\b(y?p)T(\w{1,3})\s*(?:y?p)?N(\w{1,4})?")


def _first(pattern: re.Pattern, docs: list[Document]) -> tuple[re.Match, Document] | None:
    for doc in docs:
        if m := pattern.search(doc.text):
            return m, doc
    return None


def _evidence(m: re.Match, doc: Document) -> list[Evidence]:
    return [Evidence(doc_id=doc.id, quote=m.group(0), start=m.start(), end=m.end())]


def extract_mock(docs: list[Document]) -> NorReport:
    report = NorReport()
    # histology first: it is the most reliable source for diagnosis, morphology and pTNM
    ordered = sorted(docs, key=lambda d: d.kind != "histology")

    if hit := _first(_ICD10, ordered):
        m, doc = hit
        code = m.group(0) if "." in m.group(0) or len(m.group(0)) == 3 else f"{m.group(0)[:3]}.{m.group(0)[3:]}"
        report.icd10 = Extracted[str](
            value=code,
            coding=Coding(system=ICD10_SYSTEM, code=code, display=lookup(code)),
            status=FieldStatus.found,
            confidence=0.6,
            evidence=_evidence(m, doc),
        )

    if hit := _first(_ICDO_MORPH, ordered):
        m, doc = hit
        code = f"{m.group(1)}/{m.group(2)}"
        report.morphology_code = Extracted[str](
            value=code, status=FieldStatus.found, confidence=0.6, evidence=_evidence(m, doc)
        )

    if hit := _first(_PTNM, ordered):
        m, doc = hit
        tnm = report.tnm_pathological
        tnm.y_prefix = m.group(1).startswith("y")
        tnm.t = Extracted[str](value=m.group(2), status=FieldStatus.found, confidence=0.5, evidence=_evidence(m, doc))
        if m.group(3):
            tnm.n = Extracted[str](value=m.group(3), status=FieldStatus.found, confidence=0.5, evidence=_evidence(m, doc))
    return report


def extract(docs: list[Document]) -> NorReport:
    if get_settings().llm_mode == "mock":
        return extract_mock(docs)
    raise NotImplementedError("live LLM extraction: implement per field group (see module docstring)")
