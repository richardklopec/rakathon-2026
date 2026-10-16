"""Code lists from the ÚZIS package tracked in ai-nor/uploads (Windows-1250 CSV) and the PDF-derived haematology CSV."""

import re

import pytest

from app.retrieval.codes import load_morphology
from app.validate import codefiles

pytestmark = pytest.mark.skipif(codefiles.find(codefiles.INDEX_DISEASES) is None, reason="ÚZIS code lists not available")


def test_morphology_typos_fixed_and_cleaned():
    terms = load_morphology()
    codes = {c for c, _ in terms}
    assert {"9013/0", "9120/3", "8381/0"} <= codes  # 'M90013/0' and 'M91200/3' in the ÚZIS index
    assert all(len(c) == 6 for c in codes)  # NNNN/N only, no 5-digit typos
    assert not [n for _, n in terms if re.search(r"\(M\d", n)]  # no code fragments left in names ('(MALT …)' is fine)


def test_haematology_codes_from_pdf():
    codes = {c for c, _ in load_morphology()}
    assert {"9875/3", "9650/3", "9680/3", "9732/3", "9823/3"} <= codes  # CML, Hodgkin, DLBCL, myeloma, CLL
    assert sum(c >= "96" for c in codes) >= 90
