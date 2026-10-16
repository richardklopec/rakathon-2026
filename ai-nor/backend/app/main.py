import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import extract, ingest, retrieval, store
from app.confidence import apply_review_policy, review_queue
from app.config import get_settings
from app.export import uzis
from app.fhir import client as fhir
from app.fhir.mapping import build_bundle
from app.models import Case, NorReport
from app.retrieval import codes
from app.validate import consistency, rodne_cislo

app = FastAPI(title="AI NOR")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


def _get(case_id: str) -> Case:
    case = store.load(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


@app.get("/api/health")
def health():
    return {"ok": True, "llm_mode": get_settings().llm_mode, "fhir": fhir.is_up()}


@app.get("/api/cases")
def list_cases() -> list[Case]:
    return store.list_cases()


@app.post("/api/cases")
async def create_case(files: list[UploadFile], patient_ref: str | None = None) -> Case:
    now = datetime.now(timezone.utc)
    case = Case(id=str(uuid.uuid4()), patient_ref=patient_ref, created_at=now, updated_at=now)
    for f in files:
        try:
            case.documents += ingest.to_documents(f.filename or "upload", await f.read())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    return store.save(case)


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> Case:
    return _get(case_id)


@app.post("/api/cases/{case_id}/index")
def index_case(case_id: str) -> dict:
    """Chunk + embed (locally) the case documents into IRIS Vector Search (Nor.Chunk)."""
    return {"chunks": retrieval.index_case(_get(case_id))}


@app.get("/api/cases/{case_id}/search")
def search_case(case_id: str, q: str, k: int = 5) -> list[dict]:
    """Passages of the case most similar to q, with offsets usable as Evidence."""
    _get(case_id)
    return [vars(h) for h in retrieval.search(case_id, q, k)]


@app.get("/api/codes/search")
def search_codes(q: str, system: str = codes.MORPHOLOGY, k: int = 5) -> list[dict]:
    """Candidate codes for a free-text term (system: mkn10 | icdo3-morph)."""
    return [vars(h) for h in codes.search_codes(system, q, k)]


@app.post("/api/cases/{case_id}/extract")
def run_extract(case_id: str) -> Case:
    case = _get(case_id)
    case.report, case.warnings = extract.extract(case.documents, case.patient_ref)
    case.confirmed_by = case.confirmed_at = None  # new extraction needs a new confirmation
    case.updated_at = datetime.now(timezone.utc)
    return store.save(case)


@app.put("/api/cases/{case_id}/report")
def update_report(case_id: str, report: NorReport) -> Case:
    """Clinician resolves the review queue (review state lives on each field). Invalidates a previous confirmation."""
    case = _get(case_id)
    case.report = apply_review_policy(report)
    # consistency warnings follow the clinician's edits (confidences of edited fields are the clinician's, left alone)
    case.warnings = [w for w in case.warnings if not w.startswith(consistency.PREFIX)]
    case.warnings += consistency.warnings(consistency.check(case.report))
    case.confirmed_by = case.confirmed_at = None
    case.updated_at = datetime.now(timezone.utc)
    return store.save(case)


class Patient(BaseModel):
    patient_ref: str | None


@app.put("/api/cases/{case_id}/patient")
def update_patient(case_id: str, body: Patient) -> Case:
    """'Pacient RČ' from the preview. A value shaped like a birth number must be a valid one (stored as RRMMDD/XXXX)."""
    case = _get(case_id)
    ref = (body.patient_ref or "").strip() or None
    if ref and rodne_cislo.looks_like(ref):
        rc = rodne_cislo.check(ref)
        if not rc.valid:
            raise HTTPException(422, "Neplatné rodné číslo: " + "; ".join(rc.errors))
        ref = rc.normalized
    case.patient_ref = ref
    case.confirmed_by = case.confirmed_at = None
    case.updated_at = datetime.now(timezone.utc)
    return store.save(case)


@app.get("/api/codelists")
def get_codelists() -> dict:
    """Options for the select boxes of the NOR form preview ({value, label}; value = what NorReport stores)."""
    return uzis.codelists()


@app.get("/api/cases/{case_id}/review-queue")
def get_review_queue(case_id: str) -> list[dict]:
    """Fields waiting for the clinician: conflicts first, then lowest confidence."""
    return [{"path": p, "field": f} for p, f in review_queue(_get(case_id).report)]


class Confirmation(BaseModel):
    by: str


@app.post("/api/cases/{case_id}/confirm")
def confirm(case_id: str, body: Confirmation) -> Case:
    """Clinician confirms the whole report preview. Only possible with an empty review queue."""
    case = _get(case_id)
    if pending := review_queue(case.report):
        raise HTTPException(409, f"ke kontrole zbývá {len(pending)} polí: " + ", ".join(p for p, _ in pending))
    case.confirmed_by, case.confirmed_at = body.by, datetime.now(timezone.utc)
    return store.save(case)


def _require_confirmed(case: Case) -> None:
    if not case.confirmed_at:
        raise HTTPException(409, "hlášení není potvrzené lékařem (POST /confirm)")


@app.get("/api/cases/{case_id}/uzis-preview")
def uzis_preview(case_id: str) -> dict:
    """Report in the ÚZIS form structure, for the preview the clinician confirms."""
    return uzis.build(_get(case_id))


@app.get("/api/cases/{case_id}/uzis-export")
def uzis_export(case_id: str) -> dict:
    """Confirmed report for ÚZIS / NOR (JSON in the form structure)."""
    case = _get(case_id)
    _require_confirmed(case)
    return uzis.build(case)


@app.get("/api/cases/{case_id}/fhir-bundle")
def preview_bundle(case_id: str) -> dict:
    return build_bundle(_get(case_id))


@app.post("/api/cases/{case_id}/submit")
def submit(case_id: str) -> dict:
    """Write the confirmed report to the IRIS FHIR server as one transaction."""
    case = _get(case_id)
    _require_confirmed(case)
    response = fhir.post_transaction(build_bundle(case))
    case.fhir_bundle_id = response.get("id")
    store.save(case)
    return response
