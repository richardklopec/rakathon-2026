"""Review policy: which fields are accepted automatically and which go to the review queue.

Rule (PLAN.md §4): a field goes to review only when the documents conflict or the confidence is below
AUTO_ACCEPT_THRESHOLD (default 85). Everything else with verified evidence is auto-accepted.
Missing fields are not reviewed; they make the report incomplete instead.

Caps: when the documents disagree, the field's confidence is at most CONFLICT_CAP, whatever the winning value scored
(several sources agreeing on one value does not make it certain while another source says something else).
"""

from collections.abc import Iterator

from app.config import get_settings
from app.models import AiConfidence, Extracted, FieldStatus, NorReport, ReviewState

CONFLICT_CAP = 60
_CONFLICT_REASON = f"⚠ dokumenty si odporují: jistota max. {CONFLICT_CAP}"
CONSISTENCY_CAP = 50  # fields that contradict another field (app/validate/consistency.py)


def cap(field: Extracted, limit: int, reason: str) -> None:
    """Lower the field's confidence to `limit` (never raise it) and say why, once."""
    if field.confidence is None or field.confidence > limit:
        field.confidence = limit
    if reason not in field.confidence_reasons:
        field.confidence_reasons.append(reason)


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


def apply_violations(report: NorReport, violations) -> NorReport:
    """Cap the AI fields involved in a consistency violation (validate/consistency.py); review policy decides after."""
    fields = dict(iter_fields(report))
    for v in violations:
        for path in v.fields:
            f = fields.get(path)
            if f is None or f.status == FieldStatus.missing:
                continue
            if f.review.state in (ReviewState.confirmed, ReviewState.edited, ReviewState.rejected):
                continue  # a human already decided
            cap(f, CONSISTENCY_CAP, f"✗ nesoulad: {v.message}")
    return report


def apply_review_policy(report: NorReport) -> NorReport:
    threshold = get_settings().auto_accept_threshold
    for path, field in iter_fields(report):
        if "[" in path:  # treatments / biomarkers / progression: context for checks, not on the NOR form, never reviewed
            field.needs_review = False
            continue
        if field.status in (FieldStatus.missing, FieldStatus.not_applicable):
            field.needs_review = False
            continue
        if field.review.state in (ReviewState.confirmed, ReviewState.edited, ReviewState.rejected):
            continue  # a human already decided; never override
        verified = any(e.verified for e in field.evidence)
        conflict = field.status == FieldStatus.conflict
        if conflict:
            cap(field, CONFLICT_CAP, _CONFLICT_REASON)
        low = field.confidence is None or field.confidence < threshold
        field.needs_review = conflict or low or not verified
        field.review.state = ReviewState.pending if field.needs_review else ReviewState.auto_accepted
    return report


def overall(report: NorReport) -> AiConfidence:
    """Overall AI confidence: weighted mean of the confidences of the NOR form fields whose value comes from AI.

    Mandatory fields (export/uzis.REQUIRED) count double. Values edited or rejected by the clinician are not the AI's
    and are left out; missing fields are completeness, reported separately (missing != uncertain).
    """
    from app.export.uzis import REQUIRED  # uzis imports models; keep this module light

    out = AiConfidence()
    total = weights = 0
    for path, f in iter_fields(report):
        if "[" in path:  # biomarkers / treatments are not on the NOR form
            continue
        required = path.split(".")[0] in REQUIRED
        if f.status in (FieldStatus.missing, FieldStatus.not_applicable) or f.review.state == ReviewState.rejected:
            out.missing_required += required
            continue
        if f.review.state == ReviewState.edited:
            out.edited_by_human += 1
            continue
        if f.confidence is None:
            continue
        w = 2 if required else 1
        total, weights = total + w * f.confidence, weights + w
        out.fields_ai += 1
        out.conflicts += f.status == FieldStatus.conflict
        out.auto_accepted += f.review.state == ReviewState.auto_accepted
        out.to_review += f.needs_review and f.review.state == ReviewState.pending
    if weights:
        out.score = round(total / weights)
        out.level = "vysoká" if out.score >= get_settings().auto_accept_threshold else "střední" if out.score >= 60 else "nízká"
    return out


def review_queue(report: NorReport) -> list[tuple[str, Extracted]]:
    """Fields waiting for a human: conflicts first, then lowest confidence."""
    pending = [(p, f) for p, f in iter_fields(report) if f.needs_review and f.review.state == ReviewState.pending]
    return sorted(pending, key=lambda pf: (pf[1].status != FieldStatus.conflict, pf[1].confidence or 0))
