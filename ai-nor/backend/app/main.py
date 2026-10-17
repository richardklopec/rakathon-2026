import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import audit, extract, ingest, nis, retrieval, store
from app.confidence import apply_review_policy, review_queue
from app.config import get_settings
from app.export import batch, uzis
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
async def create_case(files: list[UploadFile], patient_ref: str | None = None, x_actor: str | None = Header(None)) -> Case:
    now = datetime.now(timezone.utc)
    case = Case(id=str(uuid.uuid4()), patient_ref=patient_ref, created_at=now, updated_at=now)
    for f in files:
        try:
            case.documents += ingest.to_documents(f.filename or "upload", await f.read())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    store.save(case)
    audit.log(case.id, audit.actor_from_header(x_actor), audit.CASE_CREATED, new=", ".join(d.filename for d in case.documents))
    return case


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
def run_extract(case_id: str, x_actor: str | None = Header(None)) -> Case:
    case = _get(case_id)
    case.report, case.warnings = extract.extract(case.documents, case.patient_ref)
    case.confirmed_by = case.confirmed_at = None  # new extraction needs a new confirmation
    case.updated_at = datetime.now(timezone.utc)
    store.save(case)
    audit.log(case.id, audit.actor_from_header(x_actor), audit.EXTRACTED, new=f"{get_settings().llm_mode}, ke kontrole {len(review_queue(case.report))}")
    return case


@app.put("/api/cases/{case_id}/report")
def update_report(case_id: str, report: NorReport, x_actor: str | None = Header(None)) -> Case:
    """Clinician resolves the review queue (review state lives on each field). Invalidates a previous confirmation."""
    case = _get(case_id)
    audit.log_report_changes(case.id, audit.actor_from_header(x_actor), case.report, report)  # who changed what (IRIS)
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
def update_patient(case_id: str, body: Patient, x_actor: str | None = Header(None)) -> Case:
    """'Pacient RČ' from the preview. A value shaped like a birth number must be a valid one (stored as RRMMDD/XXXX)."""
    case = _get(case_id)
    ref = (body.patient_ref or "").strip() or None
    if ref and rodne_cislo.looks_like(ref):
        rc = rodne_cislo.check(ref)
        if not rc.valid:
            raise HTTPException(422, "Neplatné rodné číslo: " + "; ".join(rc.errors))
        ref = rc.normalized
    if ref != case.patient_ref:
        audit.log(case.id, audit.actor_from_header(x_actor), audit.PATIENT, "patient_ref", case.patient_ref, ref)
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
def confirm(case_id: str, body: Confirmation, x_actor: str | None = Header(None)) -> Case:
    """Clinician confirms the whole report preview. Only possible with an empty review queue."""
    case = _get(case_id)
    if pending := review_queue(case.report):
        raise HTTPException(409, f"ke kontrole zbývá {len(pending)} polí: " + ", ".join(p for p, _ in pending))
    case.confirmed_by, case.confirmed_at = body.by, datetime.now(timezone.utc)
    store.save(case)
    audit.log(case.id, audit.actor_from_header(x_actor) if x_actor else body.by, audit.REPORT_CONFIRMED, new=body.by)
    return case


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
def submit(case_id: str, x_actor: str | None = Header(None)) -> dict:
    """Write the confirmed report to the IRIS FHIR server as one transaction."""
    case = _get(case_id)
    _require_confirmed(case)
    response = fhir.post_transaction(build_bundle(case))
    case.fhir_bundle_id = response.get("id")
    store.save(case)
    audit.log(case.id, audit.actor_from_header(x_actor), audit.FHIR_SUBMITTED, new=f"{len(response.get('entry', []))} zdrojů")
    return response


class ExportRequest(BaseModel):
    case_ids: list[str]
    format: str = "csv"  # csv | json


@app.post("/api/export")
def export_reports(body: ExportRequest, x_actor: str | None = Header(None)) -> Response:
    """Bulk export of confirmed reports (CSV or JSON). Every exported report gets an 'exported' entry in the audit log."""
    if body.format not in batch.FORMATS:
        raise HTTPException(422, f"neznámý formát {body.format} (csv | json)")
    if not body.case_ids:
        raise HTTPException(422, "nevybráno žádné hlášení")
    cases = [_get(i) for i in body.case_ids]
    if unconfirmed := [c.patient_ref or c.id for c in cases if not c.confirmed_at]:
        raise HTTPException(409, "exportovat lze jen potvrzená hlášení; nepotvrzená: " + ", ".join(unconfirmed))
    data = batch.build(cases, body.format)
    actor = audit.actor_from_header(x_actor)
    audit.write([audit.entry(c.id, actor, audit.EXPORTED, new=f"{body.format.upper()}, {len(cases)} hlášení v dávce") for c in cases])
    name = f"nor-hlaseni-{datetime.now().strftime('%Y%m%d-%H%M')}.{body.format}"
    return Response(data, media_type=batch.FORMATS[body.format], headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/nis/inbox")
def nis_inbox() -> dict:
    """New reports from the NIS in IRIS FHIR (DocumentReference tagged for AI NOR), grouped by patient."""
    if not fhir.is_up():
        return {"iris": False, "patients": []}
    return {"iris": True, "patients": nis.inbox()}


class NisImport(BaseModel):
    patient: str
    ids: list[str]


@app.post("/api/nis/import")
def nis_import(body: NisImport, x_actor: str | None = Header(None)) -> Case:
    """Turn chosen NIS reports of one patient into a case (then POST /extract as for an upload)."""
    try:
        docs = nis.fetch(body.ids)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    now = datetime.now(timezone.utc)
    case = Case(id=str(uuid.uuid4()), patient_ref=body.patient, created_at=now, updated_at=now)
    for doc in docs:
        try:
            case.documents += ingest.to_documents(nis.filename(doc), nis.content(doc))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    store.save(case)
    nis.mark_imported(body.ids)
    audit.log(case.id, audit.actor_from_header(x_actor), audit.NIS_IMPORTED,
              new=f"{len(docs)} zpráv z NIS (IRIS FHIR DocumentReference): " + ", ".join(d["id"] for d in docs))
    return case


@app.get("/api/exports")
def export_status() -> dict:
    """Last export of every report: {case_id: {at, actor, detail}} (audit log, IRIS Nor.Audit)."""
    return {cid: {"at": e.at, "actor": e.actor, "detail": e.new} for cid, e in audit.latest(audit.EXPORTED).items()}


@app.get("/api/cases/{case_id}/audit")
def get_audit(case_id: str) -> dict:
    """Change log of the case, oldest first (IRIS table Nor.Audit; local file while IRIS is down)."""
    _get(case_id)
    entries, iris_up = audit.read(case_id)
    return {"iris": iris_up, "entries": [vars(e) for e in entries]}
