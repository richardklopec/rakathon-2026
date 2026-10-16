"""Consistency of the report fields with each other (deterministic, no LLM).

Each violation names the fields involved; app/confidence.py caps their confidence (CONSISTENCY_CAP) so they go to review,
and the message is shown as a case warning. Only rules that hold under any NOR convention are here; rules that depend
on open questions (how NOR records "no metastases", disease extent from stage, stage tables per site) come later.
"""

import re
from dataclasses import dataclass
from datetime import date

from app.models import Extracted, FieldStatus, NorReport, PartialDate, ReviewState

PREFIX = "Nesoulad údajů: "  # case warnings from this module (recomputed after every edit)


@dataclass
class Violation:
    rule: str
    fields: list[str]  # report paths, e.g. "tnm_pathological.n"
    message: str  # Czech, for the clinician


def _field(report: NorReport, path: str) -> Extracted | None:
    obj = report
    for part in path.split("."):
        obj = getattr(obj, part, None)
    return obj if isinstance(obj, Extracted) else None


def _v(report: NorReport, path: str):
    f = _field(report, path)
    if f is None or f.value is None or f.status in (FieldStatus.missing, FieldStatus.not_applicable):
        return None
    return None if f.review.state == ReviewState.rejected else f.value


def _m(report: NorReport) -> tuple[str, str] | None:
    """(path, value) of the M category: pathological if stated, else clinical."""
    for path in ("tnm_pathological.m", "tnm_clinical.m"):
        if (v := _v(report, path)) is not None:
            return path, str(v)
    return None


def _date(d: PartialDate) -> tuple[int, int, int]:
    return d.year, d.month or 1, d.day or 1


def check(report: NorReport, today: date | None = None) -> list[Violation]:
    out: list[Violation] = []
    v = lambda path: _v(report, path)  # noqa: E731

    # --- distant metastases
    m = _m(report)
    sites = v("metastasis_sites")
    if m and m[1].startswith("1") and sites == []:
        out.append(Violation("m1_without_sites", [m[0], "metastasis_sites"],
                             f"M{m[1]} (vzdálené metastázy), ale lokalizace metastáz je „žádné“."))
    if m and m[1] == "0" and sites:
        out.append(Violation("m0_with_sites", [m[0], "metastasis_sites"],
                             "M0 (bez vzdálených metastáz), ale je vyplněná lokalizace metastáz."))
    if v("disease_extent") == "1" and ((m and m[1].startswith("1")) or sites):
        out.append(Violation("localized_with_metastases", ["disease_extent", *([m[0]] if m and m[1].startswith("1") else ["metastasis_sites"])],
                             "Onemocnění „lokalizované“, ale jsou uvedené vzdálené metastázy."))

    # --- lymph nodes
    examined, positive = v("pn_examined"), v("pn_positive")
    if examined is not None and positive is not None and positive > examined:
        out.append(Violation("nodes_positive_gt_examined", ["pn_positive", "pn_examined"],
                             f"Pozitivních uzlin ({positive}) je víc než vyšetřených ({examined})."))
    pn = v("tnm_pathological.n")
    if pn is not None and positive is not None:
        pn = str(pn)
        if pn.startswith("0") and positive > 0:  # pN0(i+) = isolated tumour cells, not a positive node
            out.append(Violation("pn0_with_positive_nodes", ["tnm_pathological.n", "pn_positive"],
                                 f"pN{pn}, ale počet pozitivních uzlin je {positive}."))
        if re.match(r"[1-3]", pn) and positive == 0:
            out.append(Violation("pn_positive_without_nodes", ["tnm_pathological.n", "pn_positive"],
                                 f"pN{pn} (postižené uzliny), ale počet pozitivních uzlin je 0."))
    if v("sentinel_node") == "1" and pn is not None and str(pn).startswith("0") and "i+" not in str(pn):
        out.append(Violation("positive_sentinel_pn0", ["sentinel_node", "tnm_pathological.n"],
                             f"Sentinelová uzlina pozitivní, ale pN{pn}."))

    # --- diagnosis basis vs. morphology type (NOR: 16 / 08 = histology, 04 = cytology)
    basis = {int(b) for b in v("diagnosis_basis") or []}
    mtype = v("morphology_type")
    if mtype == "Histologie" and basis and not basis & {8, 16}:
        out.append(Violation("histology_without_basis", ["morphology_type", "diagnosis_basis"],
                             "Typ morfologie „Histologie“, ale K dg. vedla vyšetření neobsahuje histologii (08 ani 16)."))
    if mtype == "Cytologie" and basis and 4 not in basis:
        out.append(Violation("cytology_without_basis", ["morphology_type", "diagnosis_basis"],
                             "Typ morfologie „Cytologie“, ale K dg. vedla vyšetření neobsahuje cytologii (04)."))

    # --- diagnosis vs. topography vs. morphology behaviour
    icd, topo, morph = v("icd10"), v("topography"), v("morphology_code")
    if icd and topo and re.match(r"C[0-7]\d|C80", icd) and topo[:3] != icd[:3]:
        out.append(Violation("icd_vs_topography", ["icd10", "topography"],
                             f"Dg. MKN {icd} a topografie {topo} patří k různým lokalizacím."))
    if icd and morph and "/" in morph:
        behaviour = morph.rsplit("/", 1)[1]
        expected = ("3", "6", "9") if icd.startswith("C") else ("2",) if re.match(r"D0\d", icd) else ("1",) if re.match(r"D3[7-9]|D4[0-8]", icd) else None
        if expected and behaviour not in expected:
            out.append(Violation("icd_vs_behaviour", ["icd10", "morphology_code"],
                                 f"Dg. MKN {icd} neodpovídá chování morfologie {morph} (/{behaviour})."))

    # --- dates
    dg = v("diagnosis_date")
    if isinstance(dg, PartialDate):
        today = today or date.today()
        if _date(dg) > (today.year, today.month, today.day):
            out.append(Violation("diagnosis_in_future", ["diagnosis_date"], "Datum stanovení diagnózy je v budoucnosti."))
        starts = [t.start.value for t in report.treatments if isinstance(t.start.value, PartialDate)]
        if starts and _date(dg) > min(_date(s) for s in starts):
            out.append(Violation("diagnosis_after_treatment", ["diagnosis_date"],
                                 "Datum stanovení diagnózy je po zahájení léčby."))
    return out


def warnings(violations: list[Violation]) -> list[str]:
    return [PREFIX + x.message for x in violations]
