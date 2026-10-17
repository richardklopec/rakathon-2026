"""Keep each case in the IRIS FHIR server as one record that is updated in place.

The record is written right after the AI extraction as a draft (Composition preliminary, only fields AI could accept on
its own) and rewritten after every change of the case: a field resolved by the clinician joins it, confirmation turns
it final. Same resource ids every time (app/fhir/mapping.py), so FHIR keeps one record with its version history.
Resources that dropped out since the last write (a field rejected later) are deleted in the same transaction.
"""

from datetime import datetime, timezone

from app.confidence import iter_fields
from app.fhir import client
from app.fhir.mapping import build_bundle, document_ids
from app.models import Case, FhirRecord, FieldStatus, ReviewState


def extracted(case: Case) -> bool:
    """AI has processed the case (or a person filled something in): there is a record to write."""
    return any(f.status != FieldStatus.missing or f.review.state != ReviewState.pending for _, f in iter_fields(case.report))


def sync(case: Case, documents: bool = False) -> Case:
    """Write the current state of the case to FHIR. Never raises: on failure case.fhir.error says why.

    documents=True sends the source documents again (after a new extraction or a change of patient); they are
    sent anyway until a write of them succeeded.
    """
    if not extracted(case):
        return case
    before = set(case.fhir.resources)
    docs = document_ids(case)
    send_docs = documents or not before.issuperset(docs)
    bundle = build_bundle(case, documents=send_docs, update=bool(before))
    written = [e["request"]["url"] for e in bundle["entry"] if "?" not in e["request"]["url"]]
    current = written + [d for d in docs if d not in written]
    bundle["entry"] += [{"request": {"method": "DELETE", "url": url}} for url in sorted(before - set(current))]
    try:
        response = client.post_transaction(bundle)
    except Exception as e:  # noqa: BLE001 - FHIR down, timeout, rejected bundle: the case itself stays saved
        case.fhir.error = f"Zápis do IRIS FHIR se nepovedl: {str(e)[:300]}"
        return case
    composition = f"Composition/{case.id}"
    version = next((_version(e["response"]) for e in response.get("entry", []) if composition in (e.get("response") or {}).get("location", "")), None)
    case.fhir = FhirRecord(status="final" if case.confirmed_at else "preliminary", composition=composition, version=version,
                           resources=current, synced_at=datetime.now(timezone.utc))
    return case


def _version(response: dict) -> str | None:
    """versionId from the etag (W/"3", what IRIS sends) or from a location ending in /_history/3."""
    if etag := response.get("etag"):
        return etag.removeprefix("W/").strip('"')
    location = response.get("location", "")
    return location.rsplit("/", 1)[-1] if "/_history/" in location else None
