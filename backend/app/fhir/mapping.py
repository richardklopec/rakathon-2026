"""Build a FHIR R4 transaction Bundle from a confirmed NOR report.

Profiles: mCODE STU4 (structure), HL7 EU Common Cancer Model (concepts), HL7 CZ Core (identifiers, MKN-10).
Only fields the clinician confirmed or edited are written. See contracts/fhir_mapping.md.
"""

import base64
import uuid
from datetime import datetime, timezone

from app.models import Case, Extracted, Laterality, PartialDate, ReviewState, TNM

MCODE = "http://hl7.org/fhir/us/mcode/StructureDefinition/"
SCT = "http://snomed.info/sct"
ICDO3 = "http://terminology.hl7.org/CodeSystem/icd-o-3"
ICD10_CZ = "https://uzis.cz/terminology/CodeSystem/mkn-10"
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
    return field.value is not None and field.review.state in (ReviewState.confirmed, ReviewState.edited)


def _date(d: PartialDate) -> str:
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(x for x in (d.year, d.month, d.day) if x))


def _cc(system: str, code: str, display: str | None = None) -> dict:
    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    return {"coding": [coding]}


def _entry(resource: dict, method: str = "POST", url: str | None = None) -> dict:
    full_url = f"urn:uuid:{uuid.uuid4()}"
    return {
        "fullUrl": full_url,
        "resource": resource,
        "request": {"method": method, "url": url or resource["resourceType"]},
    }


def build_bundle(case: Case) -> dict:
    r = case.report
    entries: list[dict] = []

    patient = _entry(
        {"resourceType": "Patient", "identifier": [{"system": PATIENT_ID_SYSTEM, "value": case.patient_ref or case.id}]},
        method="PUT",
        url=f"Patient?identifier={PATIENT_ID_SYSTEM}|{case.patient_ref or case.id}",
    )
    entries.append(patient)
    subject = {"reference": patient["fullUrl"]}

    doc_refs = {}
    for doc in case.documents:
        e = _entry(
            {
                "resourceType": "DocumentReference",
                "status": "current",
                "subject": subject,
                "description": f"{doc.kind}: {doc.filename}",
                "content": [
                    {
                        "attachment": {
                            "contentType": "text/plain; charset=utf-8",
                            "title": doc.filename,
                            "data": base64.b64encode(doc.text.encode("utf-8")).decode("ascii"),
                        }
                    }
                ],
            }
        )
        doc_refs[doc.id] = e["fullUrl"]
        entries.append(e)

    condition = {
        "resourceType": "Condition",
        "meta": {"profile": [MCODE + "mcode-primary-cancer-condition"]},
        "subject": subject,
        "clinicalStatus": _cc("http://terminology.hl7.org/CodeSystem/condition-clinical", "active"),
        "verificationStatus": _cc("http://terminology.hl7.org/CodeSystem/condition-ver-status", "confirmed"),
        "category": [_cc("http://terminology.hl7.org/CodeSystem/condition-category", "problem-list-item")],
    }
    if _ok(r.icd10):
        condition["code"] = _cc(ICD10_CZ, r.icd10.value, r.icd10.coding.display if r.icd10.coding else None)
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
    condition_entry = _entry(condition)
    entries.append(condition_entry)
    focus = {"reference": condition_entry["fullUrl"]}

    def observation(profile: str, code: dict, value: str, field: Extracted) -> dict:
        return _entry(
            {
                "resourceType": "Observation",
                "meta": {"profile": [MCODE + profile]},
                "status": "final",
                "category": [_cc("http://terminology.hl7.org/CodeSystem/observation-category", "laboratory")],
                "code": code,
                "subject": subject,
                "focus": [focus],
                "valueCodeableConcept": {"text": value},
                "derivedFrom": [{"reference": doc_refs[e.doc_id]} for e in field.evidence if e.doc_id in doc_refs],
            }
        )

    for tnm, idx, prefix in ((r.tnm_clinical, 0, "c"), (r.tnm_pathological, 1, "p")):
        for part in ("t", "n", "m"):
            field = getattr(tnm, part)
            if _ok(field):
                code, display = TNM_CODES[part][idx]
                value = f"{'y' if tnm.y_prefix else ''}{prefix}{part.upper()}{field.value}"
                entries.append(observation(TNM_CODES[part][2], _cc(SCT, code, display), value, field))

    if _ok(r.grade):
        entries.append(
            observation(
                "mcode-histologic-grade",
                _cc("http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl", "C18000", "Histologic Grade"),
                r.grade.value,
                r.grade,
            )
        )

    # Provenance: which documents each written resource was derived from, and who confirmed it
    targets = [{"reference": e["fullUrl"]} for e in entries if e["resource"]["resourceType"] not in ("Patient", "DocumentReference")]
    entries.append(
        _entry(
            {
                "resourceType": "Provenance",
                "target": targets,
                "recorded": datetime.now(timezone.utc).isoformat(),
                "activity": _cc("http://terminology.hl7.org/CodeSystem/v3-DataOperation", "CREATE"),
                "agent": [
                    {"type": _cc("http://terminology.hl7.org/CodeSystem/provenance-participant-type", "assembler"),
                     "who": {"display": "AI NOR extractor"}},
                    {"type": _cc("http://terminology.hl7.org/CodeSystem/provenance-participant-type", "verifier"),
                     "who": {"display": r.icd10.review.by or "clinician"}},
                ],
                "entity": [{"role": "source", "what": {"reference": ref}} for ref in doc_refs.values()],
            }
        )
    )
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}
