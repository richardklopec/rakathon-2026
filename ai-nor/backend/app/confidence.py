"""Review policy: which fields are accepted automatically and which go to the review queue.

Rule (PLAN.md §4): a field goes to review only when the documents conflict or the confidence is below
AUTO_ACCEPT_THRESHOLD (default 85). Everything else with verified evidence is auto-accepted.
Missing fields are not reviewed; they make the report incomplete instead.
"""

from collections.abc import Iterator

from app.config import get_settings
from app.models import Extracted, FieldStatus, NorReport, ReviewState


def iter_fields(report: NorReport) -> Iterator[tuple[str, Extracted]]:
    """Yield (path, field) for every Extracted in the report, including nested TNM and lists."""
    for name in type(report).model_fields:
        value = getattr(report, name)
        if isinstance(value, Extracted):
            yield name, value
        elif hasattr(value, "t") and hasattr(value, "y_prefix"):  # TNM
            for part in ("t", "n", "m"):
                yield f"{name}.{part}", getattr(value, part)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                for sub in type(item).model_fields:
                    if isinstance(field := getattr(item, sub), Extracted):
                        yield f"{name}[{i}].{sub}", field


def apply_review_policy(report: NorReport) -> NorReport:
    threshold = get_settings().auto_accept_threshold
    for _, field in iter_fields(report):
        if field.status in (FieldStatus.missing, FieldStatus.not_applicable):
            field.needs_review = False
            continue
        if field.review.state in (ReviewState.confirmed, ReviewState.edited, ReviewState.rejected):
            continue  # a human already decided; never override
        verified = any(e.verified for e in field.evidence)
        conflict = field.status == FieldStatus.conflict
        low = field.confidence is None or field.confidence < threshold
        field.needs_review = conflict or low or not verified
        field.review.state = ReviewState.pending if field.needs_review else ReviewState.auto_accepted
    return report


def review_queue(report: NorReport) -> list[tuple[str, Extracted]]:
    """Fields waiting for a human: conflicts first, then lowest confidence."""
    pending = [(p, f) for p, f in iter_fields(report) if f.needs_review and f.review.state == ReviewState.pending]
    return sorted(pending, key=lambda pf: (pf[1].status != FieldStatus.conflict, pf[1].confidence or 0))
