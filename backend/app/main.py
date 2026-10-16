import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app import extract, ingest, store
from app.config import get_settings
from app.fhir import client as fhir
from app.fhir.mapping import build_bundle
from app.models import Case, NorReport

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


@app.post("/api/cases/{case_id}/extract")
def run_extract(case_id: str) -> Case:
    case = _get(case_id)
    case.report = extract.extract(case.documents)
    case.updated_at = datetime.now(timezone.utc)
    return store.save(case)


@app.put("/api/cases/{case_id}/report")
def update_report(case_id: str, report: NorReport) -> Case:
    """Clinician edits / confirms fields (review state lives on each field)."""
    case = _get(case_id)
    case.report = report
    case.updated_at = datetime.now(timezone.utc)
    return store.save(case)


@app.get("/api/cases/{case_id}/fhir-bundle")
def preview_bundle(case_id: str) -> dict:
    return build_bundle(_get(case_id))


@app.post("/api/cases/{case_id}/submit")
def submit(case_id: str) -> dict:
    """Write the confirmed report to the IRIS FHIR server as one transaction."""
    case = _get(case_id)
    response = fhir.post_transaction(build_bundle(case))
    case.fhir_bundle_id = response.get("id")
    store.save(case)
    return response
