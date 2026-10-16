"""Extraction pipeline: documents -> NorReport with evidence.

`mock` mode uses deterministic regexes (enough for UI work and tests).
`live` mode: app/extract/live.py (one LLM call -> verified mentions -> NOR codes -> conflicts -> confidence).
"""

import re

from app.confidence import apply_review_policy
from app.config import get_settings
from app.models import Coding, Document, Evidence, Extracted, FieldStatus, NorReport
from app.validate.mkn10 import ICD10_SYSTEM, is_valid, lookup

_ICD10 = re.compile(r"\bC\d{2}(?:\.?\d{1,2})?\b")
_ICDO_MORPH = re.compile(r"\bM?(8\d{3})(\d)\b")  # histology footer, e.g. "M1: M81403"
_PTNM = re.compile(r"\b(y?p)T(\w{1,3})\s*(?:y?p)?N(\w{1,4})?")


def _first(pattern: re.Pattern, docs: list[Document]) -> tuple[re.Match, Document] | None:
    for doc in docs:
        if m := pattern.search(doc.text):
            return m, doc
    return None


def _evidence(m: re.Match, doc: Document) -> list[Evidence]:
    # regex offsets are exact, so the quote is verified by construction
    return [Evidence(doc_id=doc.id, quote=m.group(0), start=m.start(), end=m.end(), verified=True)]


def _source_score(doc: Document) -> tuple[int, str]:
    """Base score by source reliability (PLAN.md §4)."""
    if doc.kind == "histology":
        return 70, "zdroj: histologie"
    if doc.kind == "MDT":
        return 60, "zdroj: MDT"
    return 50, f"zdroj: {doc.kind}"


def extract_mock(docs: list[Document]) -> NorReport:
    report = NorReport()
    # histology first: it is the most reliable source for diagnosis, morphology and pTNM
    ordered = sorted(docs, key=lambda d: d.kind != "histology")

    if hit := _first(_ICD10, ordered):
        m, doc = hit
        code = m.group(0) if "." in m.group(0) or len(m.group(0)) == 3 else f"{m.group(0)[:3]}.{m.group(0)[3:]}"
        score, reasons = _source_score(doc)[0], ["✓ citace ověřena", _source_score(doc)[1]]
        valid = is_valid(code)
        if valid:
            score, reasons = score + 10, reasons + ["✓ kód platný v MKN-10"]
        elif valid is False:
            score, reasons = min(score, 40), reasons + ["✗ kód není v MKN-10"]
        report.icd10 = Extracted[str](
            value=code,
            coding=Coding(system=ICD10_SYSTEM, code=code, display=lookup(code)),
            status=FieldStatus.found,
            confidence=score,
            confidence_reasons=reasons,
            evidence=_evidence(m, doc),
        )

    if hit := _first(_ICDO_MORPH, ordered):
        m, doc = hit
        code = f"{m.group(1)}/{m.group(2)}"
        # histology footer M-code is a structured anchor: highest base score
        report.morphology_code = Extracted[str](
            value=code,
            status=FieldStatus.found,
            confidence=95,
            confidence_reasons=["✓ citace ověřena", "zdroj: kód M v patičce histologie"],
            evidence=_evidence(m, doc),
        )

    if hit := _first(_PTNM, ordered):
        m, doc = hit
        tnm = report.tnm_pathological
        tnm.y_prefix = m.group(1).startswith("y")
        score, source = _source_score(doc)
        reasons = ["✓ citace ověřena", source, "mock: regex, ne LLM"]
        tnm.t = Extracted[str](value=m.group(2), status=FieldStatus.found, confidence=score, confidence_reasons=reasons, evidence=_evidence(m, doc))
        if m.group(3):
            tnm.n = Extracted[str](value=m.group(3), status=FieldStatus.found, confidence=score, confidence_reasons=reasons, evidence=_evidence(m, doc))
    return report


def extract(docs: list[Document]) -> tuple[NorReport, list[str]]:
    """Return the report (with review policy applied) and case-level warnings."""
    if get_settings().llm_mode == "mock":
        return apply_review_policy(extract_mock(docs)), []
    from app.extract.live import extract_live

    report, warnings, _ = extract_live(docs)
    return apply_review_policy(report), warnings
