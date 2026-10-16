"""validate/staging.py: UICC TNM 8 breast stage groups."""

import pytest

from app.validate.staging import stage


@pytest.mark.parametrize("t,n,m,expected", [
    ("is", "0", "0", "0"),
    ("1b", "0", "0", "IA"), ("1mi", "0(i+)", "0", "IA"),
    ("1c", "1mi", "0", "IB"), ("0", "1mi", "0", "IB"),
    ("1", "1a", "0", "IIA"), ("2", "0", "0", "IIA"),
    ("2", "1mi", "0", "IIB"), ("2", "1", "0", "IIB"), ("3", "0", "0", "IIB"),
    ("1", "2a", "0", "IIIA"), ("3", "1", "0", "IIIA"),
    ("4b", "1", "0", "IIIB"),
    ("2", "3a", "0", "IIIC"),
    ("1", "0", "1", "IV"), ("X", "X", "1", "IV"),
])
def test_breast_stage_groups(t, n, m, expected):
    assert stage("C50", t, n, m) == expected


def test_no_stage_without_explicit_categories():
    assert stage("C50", "1b", "0", "X") is None  # MX: metastases not assessed
    assert stage("C50", "1b", "0", None) is None  # no M: never assume M0
    assert stage("C50", "X", "0", "0") is None
    assert stage("C50", "is", "1", "0") is None  # not a valid combination
    assert stage("C34", "1", "0", "0") is None  # no table for the site yet
