import logging
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import audit, extract, ingest, nis, retrieval, store
from app.confidence import apply_review_policy, review_queue
from app.config import get_settings
from app.export import batch, uzis
from app.fhir import client as fhir
from app.fhir import sync as fhir_sync
from app.fhir.mapping import build_bundle
from app.models import Case, FormFields, NorReport
from app.retrieval import codes
from app.validate import consistency, rodne_cislo

log = logging.getLogger("uvicorn.error")


def startup() -> None:
    """Cases live in IRIS (Nor.CaseRecord): move in old JSON case files, then bring FHIR records that fell behind up to date."""
    try:
        moved = store.migrate_files()
        cases = store.list_cases()
    except store.Unavailable as e:
        log.warning("AI NOR: hlášení z IRIS nenačtena, IRIS neběží (%s)", e)
        return
    log.info("AI NOR: z IRIS načteno %d hlášení%s", len(cases), f", {moved} přesunuto ze starých JSON souborů" if moved else "")
    behind = [c for c in cases if fhir_sync.extracted(c)
              and (c.fhir.error or c.fhir.status != ("final" if c.confirmed_at else "preliminary"))]
    for case in behind:
        _save(case, audit.SYSTEM_ACTOR, documents=True)
    if behind:
        ok = sum(not c.fhir.error for c in behind)
        log.info("AI NOR: do IRIS FHIR dopsáno %d z %d hlášení", ok, len(behind))


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=startup, name="ai-nor-startup", daemon=True).start()  # the API answers meanwhile
    yield


app = FastAPI(title="AI NOR", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(store.Unavailable)
def iris_unavailable(_: Request, e: store.Unavailable) -> JSONResponse:
    return JSONResponse({"detail": f"Hlášení jsou uložená v IRIS a to teď neodpovídá. Spusťte IRIS (docker compose up -d). {e}"}, 503)


def _get(case_id: str) -> Case:
    case = store.load(case_id)
    if case is None:
        raise HTTPException(404, "case not found")
    return case


def _save(case: Case, actor: str, documents: bool = False) -> Case:
    """Save the case in IRIS (Nor.CaseRecord) and bring its FHIR record up to date (draft until confirmed, then final)."""
    before = case.fhir.status, case.fhir.error
    fhir_sync.sync(case, documents)
    store.save(case)
    if case.fhir.error and case.fhir.error != before[1]:
        audit.log(case.id, actor, audit.FHIR_FAILED, new=case.fhir.error)
    elif case.fhir.status and case.fhir.status != before[0]:
        what = "konečné hlášení (final)" if case.fhir.status == "final" else "rozpracované hlášení (preliminary)"
        audit.log(case.id, actor, audit.FHIR_SUBMITTED, new=f"{what}, {case.fhir.composition}, verze {case.fhir.version}")
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
    actor = audit.actor_from_header(x_actor)
    audit.log(case.id, actor, audit.EXTRACTED, new=f"{get_settings().llm_mode}, ke kontrole {len(review_queue(case.report))}")
    return _save(case, actor, documents=True)  # the draft goes to IRIS FHIR right away


@app.put("/api/cases/{case_id}/report")
def update_report(case_id: str, report: NorReport, x_actor: str | None = Header(None)) -> Case:
    """Clinician resolves the review queue (review state lives on each field). Invalidates a previous confirmation."""
    case = _get(case_id)
    actor = audit.actor_from_header(x_actor)
    audit.log_report_changes(case.id, actor, case.report, report)  # who changed what (IRIS)
    case.report = apply_review_policy(report)
    # consistency warnings follow the clinician's edits (confidences of edited fields are the clinician's, left alone)
    case.warnings = [w for w in case.warnings if not w.startswith(consistency.PREFIX)]
    case.warnings += consistency.warnings(consistency.check(case.report))
    case.confirmed_by = case.confirmed_at = None
    case.updated_at = datetime.now(timezone.utc)
    return _save(case, actor)  # the FHIR record follows (resolved fields join it)


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
    actor = audit.actor_from_header(x_actor)
    changed = ref != case.patient_ref
    if changed:
        audit.log(case.id, actor, audit.PATIENT, "patient_ref", case.patient_ref, ref)
    case.patient_ref = ref
    case.confirmed_by = case.confirmed_at = None
    case.updated_at = datetime.now(timezone.utc)
    return _save(case, actor, documents=changed)  # the documents point to the patient too


@app.put("/api/cases/{case_id}/form")
def update_form(case_id: str, body: FormFields, x_actor: str | None = Header(None)) -> Case:
    """NOR form fields typed in the preview that are not in the documents (facility, country, TNM group, ...).
    Invalidates a previous confirmation."""
    case = _get(case_id)
    actor = audit.actor_from_header(x_actor)
    before = case.form.model_dump()
    for name, value in body.model_dump().items():
        if value != before[name]:
            show = lambda v: None if v in (None, False, "") else ("ano" if v is True else str(v))  # noqa: E731
            audit.log(case.id, actor, audit.CHANGED if show(before[name]) else audit.FILLED, f"form.{name}", show(before[name]), show(value))
    case.form = body
    case.confirmed_by = case.confirmed_at = None
    case.updated_at = datetime.now(timezone.utc)
    return _save(case, actor)


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
    actor = audit.actor_from_header(x_actor) if x_actor else body.by
    audit.log(case.id, actor, audit.REPORT_CONFIRMED, new=body.by)
    return _save(case, actor)  # the same FHIR record becomes final


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
    """The transaction that keeps the case's FHIR record up to date (what the next write sends)."""
    return build_bundle(_get(case_id))


@app.post("/api/cases/{case_id}/fhir-sync")
def resync(case_id: str, x_actor: str | None = Header(None)) -> Case:
    """Write the FHIR record again, documents included (after IRIS was down). Normally every change does it by itself."""
    case = _get(case_id)
    if not fhir_sync.extracted(case):
        raise HTTPException(409, "hlášení ještě není vytěžené, ve FHIR zatím nic není")
    return _save(case, audit.actor_from_header(x_actor), documents=True)


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
    case = Case(id=str(uuid.uuid4()), patient_ref=body.patient, nis_ids=[d["id"] for d in docs], created_at=now, updated_at=now)
    for doc in docs:
        try:
            case.documents += ingest.to_documents(nis.filename(doc), nis.content(doc))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    store.save(case)  # the reports leave the inbox: nis.imported() looks at the cases
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
