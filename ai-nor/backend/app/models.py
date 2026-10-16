"""Data contract for the AI NOR report. Source of truth for contracts/nor_record.schema.json.

Every extracted value is wrapped in `Extracted`, which carries its evidence (quote + offsets in a
source document), a confidence and the clinician's review state.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, computed_field

T = TypeVar("T")


class FieldStatus(str, Enum):
    found = "found"
    missing = "missing"  # not stated in the documents (missing != negative)
    conflict = "conflict"  # documents disagree, see `alternatives`
    not_applicable = "not_applicable"  # e.g. TNM for a glioma


class ReviewState(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    edited = "edited"
    rejected = "rejected"
    auto_accepted = "auto_accepted"  # confidence >= threshold, no conflict: nobody has to review it


class Evidence(BaseModel):
    doc_id: str
    quote: str
    start: int = Field(ge=0, description="Character offset in Document.text")
    end: int = Field(ge=0)
    verified: bool = False  # quote found verbatim at [start:end] of the document


class Coding(BaseModel):
    system: str
    code: str
    display: str | None = None


class Review(BaseModel):
    state: ReviewState = ReviewState.pending
    by: str | None = None
    at: datetime | None = None
    note: str | None = None


class Extracted(BaseModel, Generic[T]):
    value: T | None = None
    coding: Coding | None = None
    status: FieldStatus = FieldStatus.missing
    confidence: int | None = Field(default=None, ge=0, le=100)  # 0-100, see app/confidence.py
    confidence_reasons: list[str] = []  # human-readable signals behind the score
    needs_review: bool = False  # conflict or confidence below AUTO_ACCEPT_THRESHOLD
    evidence: list[Evidence] = []
    alternatives: list[T] = []  # other values seen in the documents (for conflicts)
    review: Review = Review()


class PartialDate(BaseModel):
    """Anonymised documents often keep only the year or month."""

    year: int
    month: int | None = None
    day: int | None = None


class Laterality(str, Enum):
    left = "left"
    right = "right"
    bilateral = "bilateral"
    midline = "midline"
    not_applicable = "not_applicable"  # NOR "4 - odpadá"
    unknown = "unknown"


class DiagnosisBasis(int, Enum):
    """NOR 'K dg. vedla tato vyšetření' (bitmask, form shows the sum)."""

    clinically_obvious = 0
    clinical_exam = 1
    tumour_markers = 2
    cytology = 4
    histology_metastasis = 8
    histology_primary = 16


class MetastasisSite(int, Enum):
    """NOR 'Lokalizace vzdálených metastáz' (bitmask)."""

    unknown = 0
    lung = 1
    bone_marrow = 2
    bone = 4
    pleura = 8
    liver = 16
    peritoneum = 32
    brain = 64
    adrenal = 128
    lymph_nodes = 256
    skin = 512
    other = 1024


class TNM(BaseModel):
    y_prefix: bool = False  # after neoadjuvant therapy (ycTNM / ypTNM)
    t: Extracted[str] = Extracted()
    n: Extracted[str] = Extracted()
    m: Extracted[str] = Extracted()


class Biomarker(BaseModel):
    name: str  # ER, PR, HER2, Ki-67, PD-L1, p16, MSI, ...
    result: Extracted[str] = Extracted()


class TreatmentEvent(BaseModel):
    kind: str  # surgery | radiotherapy | systemic
    description: Extracted[str] = Extracted()
    start: Extracted[PartialDate] = Extracted()
    end: Extracted[PartialDate] = Extracted()
    intent: Extracted[str] = Extracted()  # neoadjuvant | adjuvant | definitive | palliative


class ProgressionEvent(BaseModel):
    status: Extracted[str] = Extracted()  # remission | recurrence | progression | stable
    date: Extracted[PartialDate] = Extracted()
    sites: Extracted[list[MetastasisSite]] = Extracted()


class NorReport(BaseModel):
    """Fields of the NOR form 'Incidence zhoubného novotvaru'."""

    diagnosis_date: Extracted[PartialDate] = Extracted()
    icd10: Extracted[str] = Extracted()  # Dg. MKN, e.g. C50.4
    topography: Extracted[str] = Extracted()  # ICD-O-3 topography
    laterality: Extracted[Laterality] = Extracted()
    diagnosis_basis: Extracted[list[DiagnosisBasis]] = Extracted()
    morphology_type: Extracted[str] = Extracted()  # NOR: "Histologie" | "Cytologie"
    morphology_code: Extracted[str] = Extracted()  # ICD-O-3, e.g. 8140/3
    morphology_name: Extracted[str] = Extracted()
    grade: Extracted[str] = Extracted()  # NOR code 1-9 (1 dobře … 4 nediferencovaný, 9 neurčen)
    tnm_clinical: TNM = TNM()
    tnm_pathological: TNM = TNM()
    pn_examined: Extracted[int] = Extracted()  # NOR "pN vyš." - lymph nodes examined
    pn_positive: Extracted[int] = Extracted()  # NOR "pN poz." - positive lymph nodes
    sentinel_node: Extracted[str] = Extracted()  # NOR 'sn'
    clinical_stage: Extracted[str] = Extracted()  # I-IV / FIGO
    metastasis_sites: Extracted[list[MetastasisSite]] = Extracted()
    disease_extent: Extracted[str] = Extracted()  # NOR 'Onemocnění': 1 lokalizované, 2 pokročilé, 9 neznámo
    biomarkers: list[Biomarker] = []
    treatments: list[TreatmentEvent] = []
    progression: list[ProgressionEvent] = []


class AiConfidence(BaseModel):
    """Overall confidence of the AI in the report (app/confidence.py: overall)."""

    score: int | None = None  # 0-100: weighted mean over fields filled by AI; mandatory NOR fields count double
    level: str | None = None  # vysoká (>= AUTO_ACCEPT_THRESHOLD) | střední (>= 60) | nízká
    fields_ai: int = 0  # fields whose current value comes from AI
    auto_accepted: int = 0
    to_review: int = 0  # still waiting for the clinician
    conflicts: int = 0
    edited_by_human: int = 0  # values replaced by the clinician (not part of the score)
    missing_required: int = 0  # mandatory NOR fields without a value (completeness, not confidence)


class Document(BaseModel):
    id: str
    filename: str
    kind: str | None = None  # AZ | PZ | KZ | MDT | histology | operation | other
    text: str


class Case(BaseModel):
    id: str
    patient_ref: str | None = None  # anonymised id from the source system
    documents: list[Document] = []
    report: NorReport = NorReport()
    warnings: list[str] = []  # case-level validation (identity mismatch, sex vs. diagnosis, ...)
    confirmed_by: str | None = None  # clinician who confirmed the whole report preview
    confirmed_at: datetime | None = None
    fhir_bundle_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def ai_confidence(self) -> AiConfidence:
        from app.confidence import overall  # confidence.py imports this module

        return overall(self.report)
