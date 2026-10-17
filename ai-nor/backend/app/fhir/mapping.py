"""Build the FHIR R4 record of a case: one transaction Bundle, written again whenever the case changes (app/fhir/sync.py).

Profiles: mCODE STU4 (structure), HL7 EU Common Cancer Model (concepts), HL7 CZ Core (identifiers, MKN-10).
Written: fields auto-accepted (confidence >= threshold, no conflict) or confirmed / edited by a human. See contracts/fhir_mapping.md.

Every resource except the Patient has a stable id derived from the case id and is written with PUT, so a later write
updates the same record (new version in FHIR _history) instead of creating a second one. A Composition holds the report
as a whole: preliminary until a clinician confirms it (Condition provisional, Observations preliminary), then final.
"""

import base64
import html
import uuid
from datetime import datetime, timezone

from app.audit import label
from app.confidence import review_queue
from app.config import get_settings
from app.models import Case, Extracted, Laterality, PartialDate, ReviewState
from app.validate import mkn10

MCODE = "http://hl7.org/fhir/us/mcode/StructureDefinition/"
SCT = "http://snomed.info/sct"
LOINC = "http://loinc.org"
ICDO3 = "http://terminology.hl7.org/CodeSystem/icd-o-3"
ICD10_CZ = "https://uzis.cz/terminology/CodeSystem/mkn-10"
REVIEW_TAG_SYSTEM = "urn:ai-nor:review"  # meta.tag: auto_accepted | confirmed | edited (+ score in display)
REPORT_TAG_SYSTEM = "urn:ai-nor:report"  # meta.tag on every resource of the record: preliminary | final
CASE_ID_SYSTEM = "urn:ai-nor:case"  # Composition.identifier = the AI NOR case id
PATIENT_ID_SYSTEM = "urn:ai-nor:source-patient-id"  # TODO real FNO system; RČ would be https://ncez.mzcr.cz/fhir/sid/rcis

LATERALITY_SCT = {
    Laterality.left: ("7771000", "Left"),
    Laterality.right: ("24028007", "Right"),
    Laterality.bilateral: ("51440002", "Right and left"),
    Laterality.midline: ("399488007", "Midline"),
}

# (clinical, pathological) SNOMED observable entities from mCODE TNM staging-type value sets
TNM_CODES = {
    "t": (("399504009", "cT category"), ("384625004", "pT category"), "mcode-tnm-primary-tumor-category"),
    "n": (("399534004", "cN category"), ("371494008", "pN category"), "mcode-tnm-regional-nodes-category"),
    "m": (("399387003", "cM category"), ("371497001", "pM category"), "mcode-tnm-distant-metastases-category"),
}


def _ok(field: Extracted) -> bool:
    return field.value is not None and field.review.state in (
        ReviewState.confirmed,
        ReviewState.edited,
        ReviewState.auto_accepted,
    )


def _review_tag(field: Extracted) -> dict:
    return {"system": REVIEW_TAG_SYSTEM, "code": field.review.state.value, "display": f"jistota {field.confidence}"}


def _date(d: PartialDate) -> str:
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(x for x in (d.year, d.month, d.day) if x))


def _cc(system: str, code: str, display: str | None = None) -> dict:
    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    return {"coding": [coding]}


def _put(resource: dict, rid: str) -> dict:
    """Entry that creates or updates the resource with this id (FHIR update-as-create)."""
    url = f"{resource['resourceType']}/{rid}"
    resource["id"] = rid
    return {"fullUrl": get_settings().fhir_base_url.rstrip("/") + "/" + url, "resource": resource,
            "request": {"method": "PUT", "url": url}}


def _ref(entry: dict) -> dict:
    return {"reference": entry["request"]["url"]}


def document_ids(case: Case) -> list[str]:
    return [f"DocumentReference/{case.id}-d{i}" for i in range(len(case.documents))]


def build_bundle(case: Case, documents: bool = True, update: bool = False) -> dict:
    """The whole record of the case. documents=False leaves out the source documents (they never change after upload)."""
    r = case.report
    final = case.confirmed_at is not None
    status = "final" if final else "preliminary"
    report_tag = {"system": REPORT_TAG_SYSTEM, "code": status,
                  "display": "hlášení potvrzené lékařem" if final else "rozpracované hlášení, čeká na lékaře"}
    entries: list[dict] = []

    patient_url = f"urn:uuid:{uuid.uuid4()}"
    entries.append({
        "fullUrl": patient_url,
        "resource": {"resourceType": "Patient", "identifier": [{"system": PATIENT_ID_SYSTEM, "value": case.patient_ref or case.id}]},
        "request": {"method": "PUT", "url": f"Patient?identifier={PATIENT_ID_SYSTEM}|{case.patient_ref or case.id}"},
    })
    subject = {"reference": patient_url}

    doc_refs = [{"reference": u} for u in document_ids(case)]
    if documents:
        for i, doc in enumerate(case.documents):
            entries.append(_put({
                "resourceType": "DocumentReference",
                "status": "current",
                "subject": subject,
                "description": f"{doc.kind}: {doc.filename}",
                "content": [{"attachment": {
                    "contentType": "text/plain; charset=utf-8",
                    "title": doc.filename,
                    "data": base64.b64encode(doc.text.encode("utf-8")).decode("ascii"),
                }}],
            }, f"{case.id}-d{i}"))
    doc_ref_of = {doc.id: ref for doc, ref in zip(case.documents, doc_refs)}

    condition = {
        "resourceType": "Condition",
        "meta": {"profile": [MCODE + "mcode-primary-cancer-condition"], "tag": [_review_tag(r.icd10), report_tag]},
        "subject": subject,
        "clinicalStatus": _cc("http://terminology.hl7.org/CodeSystem/condition-clinical", "active"),
        # an AI draft is not a confirmed diagnosis for anyone reading the FHIR server
        "verificationStatus": _cc("http://terminology.hl7.org/CodeSystem/condition-ver-status", "confirmed" if final else "provisional"),
        "category": [_cc("http://terminology.hl7.org/CodeSystem/condition-category", "problem-list-item")],
    }
    if _ok(r.icd10):
        condition["code"] = _cc(ICD10_CZ, r.icd10.value, mkn10.lookup(r.icd10.value))  # value may be edited by the clinician
    if _ok(r.diagnosis_date):
        condition["onsetDateTime"] = _date(r.diagnosis_date.value)
    if _ok(r.topography):
        site = _cc(ICDO3, r.topography.value)
        if _ok(r.laterality) and r.laterality.value in LATERALITY_SCT:
            code, display = LATERALITY_SCT[r.laterality.value]
            site["extension"] = [
                {"url": MCODE + "mcode-laterality-qualifier", "valueCodeableConcept": _cc(SCT, code, display)}
            ]
        condition["bodySite"] = [site]
    if _ok(r.morphology_code):
        condition["extension"] = [
            {
                "url": MCODE + "mcode-histology-morphology-behavior",
                "valueCodeableConcept": _cc(ICDO3, r.morphology_code.value, r.morphology_name.value),
            }
        ]
    condition_entry = _put(condition, f"{case.id}-dg")
    entries.append(condition_entry)
    human_reviewed = {condition_entry["request"]["url"]} if r.icd10.review.state != ReviewState.auto_accepted else set()
    focus = _ref(condition_entry)

    observations: list[dict] = []

    def observation(profile: str, code: dict, value: str, field: Extracted, suffix: str) -> dict:
        entry = _put({
            "resourceType": "Observation",
            "meta": {"profile": [MCODE + profile], "tag": [_review_tag(field), report_tag]},
            "status": status,
            "category": [_cc("http://terminology.hl7.org/CodeSystem/observation-category", "laboratory")],
            "code": code,
            "subject": subject,
            "focus": [focus],
            "valueCodeableConcept": {"text": value},
            "derivedFrom": [doc_ref_of[e.doc_id] for e in field.evidence if e.doc_id in doc_ref_of],
        }, f"{case.id}-{suffix}")
        if field.review.state != ReviewState.auto_accepted:
            human_reviewed.add(entry["request"]["url"])
        observations.append(entry)
        return entry

    for tnm, idx, prefix in ((r.tnm_clinical, 0, "c"), (r.tnm_pathological, 1, "p")):
        for part in ("t", "n", "m"):
            field = getattr(tnm, part)
            if _ok(field):
                code, display = TNM_CODES[part][idx]
                value = f"{'y' if tnm.y_prefix else ''}{prefix}{part.upper()}{field.value}"
                observation(TNM_CODES[part][2], _cc(SCT, code, display), value, field, f"{prefix}{part}")

    if _ok(r.grade):
        observation("mcode-histologic-grade", _cc("http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl", "C18000", "Histologic Grade"),
                    r.grade.value, r.grade, "g")
    entries += observations

    # Provenance: which documents the written resources came from, whether the clinician resolved the field
    # by hand or took over the AI prefill, and who confirmed the whole report (one Provenance per group).
    written = [condition_entry["request"]["url"]] + [o["request"]["url"] for o in observations]
    groups = [
        ([u for u in written if u not in human_reviewed], False, "ai"),
        ([u for u in written if u in human_reviewed], True, "lekar"),
    ]
    now = datetime.now(timezone.utc).isoformat()
    for targets, by_human, suffix in groups:
        if not targets:
            continue
        agents = [
            {"type": _cc("http://terminology.hl7.org/CodeSystem/provenance-participant-type", "assembler"),
             "who": {"display": "AI NOR extractor"}},
        ]
        if case.confirmed_by:
            agents.append(
                {"type": _cc("http://terminology.hl7.org/CodeSystem/provenance-participant-type", "verifier"),
                 "who": {"display": case.confirmed_by}}
            )
        ai_reason = "předvyplněno AI (jistota nad prahem, bez rozporu), " + (
            "potvrzeno v náhledu hlášení" if final else "čeká na potvrzení celého hlášení lékařem")
        entries.append(_put({
            "resourceType": "Provenance",
            "meta": {"tag": [report_tag]},
            "target": [{"reference": u} for u in targets],
            "recorded": now,
            "activity": _cc("http://terminology.hl7.org/CodeSystem/v3-DataOperation", "UPDATE" if update else "CREATE"),
            "reason": [{"text": "pole řešil lékař ručně" if by_human else ai_reason}],
            "agent": agents,
            "entity": [{"role": "source", "what": ref} for ref in doc_refs],
        }, f"{case.id}-prov-{suffix}"))

    entries.append(_put(_composition(case, status, report_tag, subject, condition_entry, observations, doc_refs), case.id))
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def _composition(case: Case, status: str, tag: dict, subject: dict, condition: dict, observations: list[dict], docs: list[dict]) -> dict:
    """The report as a whole: what it consists of, whether a clinician confirmed it and what still waits for review."""
    final = status == "final"
    sections = [{"title": "Diagnóza", "entry": [_ref(condition)]}]
    if observations:
        sections.append({"title": "TNM a grading", "entry": [_ref(o) for o in observations]})
    if docs:
        sections.append({"title": "Zdrojové zprávy", "entry": docs})
    pending = [label(path) for path, _ in review_queue(case.report)]
    if pending and not final:
        items = "".join(f"<li>{html.escape(p)}</li>" for p in pending)
        sections.append({"title": "Ke kontrole lékařem", "text": {
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><p>Pole, která ještě nejsou ve FHIR (čekají na lékaře):</p><ul>{items}</ul></div>',
        }})
    comp = {
        "resourceType": "Composition",
        "meta": {"tag": [tag]},
        "identifier": {"system": CASE_ID_SYSTEM, "value": case.id},
        "status": status,
        "type": _cc(LOINC, "72134-0", "Cancer event report"),
        "subject": subject,
        "date": case.updated_at.isoformat(),
        "author": [{"display": "AI NOR (vytěžení z dokumentace)"}] + ([{"display": case.confirmed_by}] if case.confirmed_by else []),
        "title": "Hlášení novotvaru do NOR" + ("" if final else " (rozpracované)"),
        "custodian": {"display": get_settings().reporting_facility},
        "section": sections,
    }
    if final and case.confirmed_at:
        comp["attester"] = [{"mode": "legal", "time": case.confirmed_at.isoformat(), "party": {"display": case.confirmed_by}}]
    return comp
