"""validate/references.py: histology report numbers vs. "viz biopsie č. …" references (synthetic reports)."""

from app.models import Document
from app.validate import references as ref


def _h(name, number, text=""):
    return Document(id=name, filename=name, kind="histology", text=f"PRŮVODNÍ LIST\nNÁLEZ:\n1/1\n{number}\nMakropopis: …\n{text}")


def test_reference_to_a_biopsy_that_is_not_the_one_in_the_documents():
    biopsy = _h("Bx.pdf", "1111/2026")
    resection = _h("Res.pdf", "2222/2026", "Typ nádoru: karcinom (viz biopsie č. 3333/2026).")
    mdt = Document(id="m", filename="MDT.pdf", kind="MDT", text="karcinom (viz biopsie č. 3333/2026)")
    assert ref.report_numbers([biopsy, resection]) == {"1111/2026": "Bx.pdf", "2222/2026": "Res.pdf"}
    w = ref.check([biopsy, resection, mdt])
    assert len(w) == 1 and w[0].startswith(ref.PREFIX + "Res.pdf, MDT.pdf odkazují na biopsii č. 3333/2026")
    assert "č. 1111/2026 (Bx.pdf)" in w[0]


def test_matching_reference_ranges_and_missing_reports_are_fine():
    biopsy = _h("Bx.pdf", "4102/2026")
    resection = _h("Res.pdf", "4110/2026", "vizte také biopsie č. 4101-4103/2026")
    assert ref.check([biopsy, resection]) == []  # 4102 lies in the range
    assert ref.check([resection]) == []  # the referenced biopsy was not uploaded: nothing to compare with
    assert ref.check([_h("Bx.pdf", "1111/2026"), _h("Res.pdf", "2222/2026", "viz biopsie č. 1111/2026")]) == []
