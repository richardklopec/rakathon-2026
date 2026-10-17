"""Reports from the hospital information system (NIS) through InterSystems IRIS.

The NIS (or an IRIS interoperability production translating its HL7v2 MDM / ORU messages) stores each new report as a
FHIR DocumentReference in the IRIS FHIR server, tagged for AI NOR (INBOX_TAG). Here we list those not imported yet,
grouped by patient, and turn the chosen ones into a case. scripts/nis_demo_send.py plays the NIS for the demo.
Which reports were imported is read from the cases in IRIS (Case.nis_ids); the NIS data in IRIS stay untouched.
"""

import base64
from collections import defaultdict

from app import store
from app.fhir import client as fhir

INBOX_SYSTEM, INBOX_CODE = "urn:ai-nor:inbox", "nis"
INBOX_TAG = f"{INBOX_SYSTEM}|{INBOX_CODE}"
PATIENT_SYSTEM = "urn:fno:nis:patient"  # demo identifier system; the real one comes from the FNO NIS
_EXT = {"text/plain": "txt", "application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/tiff": "tif",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx", "message/rfc822": "eml"}


def imported() -> set[str]:
    """NIS reports some case was already made from."""
    return {i for case in store.list_cases() for i in case.nis_ids}


def patient_key(doc: dict) -> str:
    subject = doc.get("subject") or {}
    return (subject.get("identifier") or {}).get("value") or subject.get("reference") or "neznámý pacient"


def _attachment(doc: dict) -> dict:
    return ((doc.get("content") or [{}])[0]).get("attachment") or {}


def filename(doc: dict) -> str:
    """File name for ingest: the extension decides how the content is read (text, PDF with OCR, Word, ...)."""
    att = _attachment(doc)
    ext = _EXT.get((att.get("contentType") or "text/plain").split(";")[0].strip(), "txt")
    title = att.get("title") or doc.get("description") or f"nis-{doc.get('id')}"
    return title if title.lower().endswith(f".{ext}") else f"{title}.{ext}"


def content(doc: dict) -> bytes:
    data = _attachment(doc).get("data")
    if not data:
        raise ValueError(f"DocumentReference/{doc.get('id')} nemá obsah (attachment.data)")
    return base64.b64decode(data)


def _search() -> list[dict]:
    bundle = fhir.search("DocumentReference", _tag=INBOX_TAG, status="current", _count="200")
    return [e["resource"] for e in bundle.get("entry", []) if e.get("resource", {}).get("resourceType") == "DocumentReference"]


def inbox() -> list[dict]:
    """New reports from the NIS grouped by patient: [{patient, documents: [{id, title, kind, date}]}]."""
    done = imported()
    groups: dict[str, list[dict]] = defaultdict(list)
    for doc in _search():
        if doc.get("id") in done:
            continue
        groups[patient_key(doc)].append({
            "id": doc["id"],
            "title": filename(doc),
            "kind": (doc.get("type") or {}).get("text") or doc.get("description"),
            "date": doc.get("date"),
        })
    return [{"patient": p, "documents": sorted(d, key=lambda x: x["date"] or "")} for p, d in sorted(groups.items())]


def fetch(ids: list[str]) -> list[dict]:
    wanted = set(ids)
    docs = [d for d in _search() if d.get("id") in wanted]
    if missing := wanted - {d["id"] for d in docs}:
        raise ValueError("V IRIS nejsou zprávy: " + ", ".join(sorted(missing)))
    return docs
