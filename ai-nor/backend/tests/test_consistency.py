"""validate/consistency.py and its effect on confidence (synthetic values only)."""

from datetime import date

from app.confidence import CONSISTENCY_CAP, apply_review_policy, apply_violations
from app.models import (
    TNM,
    DiagnosisBasis,
    Evidence,
    Extracted,
    FieldStatus,
    MetastasisSite,
    NorReport,
    PartialDate,
    ReviewState,
    TreatmentEvent,
)
from app.validate import consistency as c

EV = [Evidence(doc_id="d", quote="x", start=0, end=1, verified=True)]


def _f(value, confidence=95):
    return Extracted(value=value, status=FieldStatus.found, confidence=confidence, evidence=EV)


def _rules(report: NorReport) -> set[str]:
    return {v.rule for v in c.check(report, today=date(2026, 10, 16))}


def test_consistent_report_has_no_violations():
    r = NorReport(
        icd10=_f("C34.1"), topography=_f("C34.1"), morphology_code=_f("8140/3"), morphology_type=_f("Histologie"),
        diagnosis_basis=_f([DiagnosisBasis.clinical_exam, DiagnosisBasis.histology_primary]),
        tnm_pathological=TNM(n=_f("1a"), m=_f("1")), pn_examined=_f(12), pn_positive=_f(2), sentinel_node=_f("1"),
        metastasis_sites=_f([MetastasisSite.liver]), disease_extent=_f("2"), diagnosis_date=_f(PartialDate(year=2026, month=3)),
    )
    assert _rules(r) == set()


def test_metastases():
    assert "m1_without_sites" in _rules(NorReport(tnm_clinical=TNM(m=_f("1")), metastasis_sites=_f([])))
    assert "m0_with_sites" in _rules(NorReport(tnm_clinical=TNM(m=_f("0")), metastasis_sites=_f([MetastasisSite.bone])))
    assert "localized_with_metastases" in _rules(NorReport(tnm_clinical=TNM(m=_f("1b")), disease_extent=_f("1")))
    assert _rules(NorReport(tnm_clinical=TNM(m=_f("X")), metastasis_sites=_f([]))) == set()  # MX says nothing


def test_lymph_nodes():
    assert "nodes_positive_gt_examined" in _rules(NorReport(pn_examined=_f(2), pn_positive=_f(3)))
    assert "pn0_with_positive_nodes" in _rules(NorReport(tnm_pathological=TNM(n=_f("0")), pn_positive=_f(1)))
    assert "pn_positive_without_nodes" in _rules(NorReport(tnm_pathological=TNM(n=_f("1mi")), pn_positive=_f(0)))
    assert "positive_sentinel_pn0" in _rules(NorReport(tnm_pathological=TNM(n=_f("0")), sentinel_node=_f("1")))
    assert _rules(NorReport(tnm_pathological=TNM(n=_f("0(i+)")), pn_positive=_f(0), sentinel_node=_f("1"))) == set()


def test_basis_topography_behaviour_dates():
    basis_cyto = _f([DiagnosisBasis.clinical_exam, DiagnosisBasis.cytology])
    assert "histology_without_basis" in _rules(NorReport(morphology_type=_f("Histologie"), diagnosis_basis=basis_cyto))
    assert "cytology_without_basis" in _rules(NorReport(morphology_type=_f("Cytologie"), diagnosis_basis=_f([DiagnosisBasis.histology_primary])))
    assert "icd_vs_topography" in _rules(NorReport(icd10=_f("C34.1"), topography=_f("C18.7")))
    assert "icd_vs_behaviour" in _rules(NorReport(icd10=_f("C34.1"), morphology_code=_f("8140/2")))
    assert "icd_vs_behaviour" in _rules(NorReport(icd10=_f("D05.1"), morphology_code=_f("8500/3")))
    assert "diagnosis_in_future" in _rules(NorReport(diagnosis_date=_f(PartialDate(year=2027))))
    treated = NorReport(diagnosis_date=_f(PartialDate(year=2026, month=5, day=2)))
    treated.treatments = [TreatmentEvent(kind="surgery", start=_f(PartialDate(year=2026, month=4, day=2)))]
    assert "diagnosis_after_treatment" in _rules(treated)


def test_violations_cap_ai_fields_but_not_human_ones():
    r = NorReport(pn_examined=_f(2, 95), pn_positive=_f(3, 95))
    r.pn_examined.review.state = ReviewState.edited  # the clinician typed it
    r = apply_review_policy(apply_violations(r, c.check(r)))
    assert r.pn_positive.confidence == CONSISTENCY_CAP and r.pn_positive.needs_review
    assert any(x.startswith("✗ nesoulad") for x in r.pn_positive.confidence_reasons)
    assert r.pn_examined.confidence == 95
    assert c.warnings(c.check(r))[0].startswith(c.PREFIX)
