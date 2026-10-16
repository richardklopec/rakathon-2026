"""MKN-10 (Czech ICD-10) lookup from the ÚZIS CSV (`01_MKN10_5E_2026_utf8.csv`, ';'-separated)."""

import csv
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

ICD10_SYSTEM = "https://uzis.cz/terminology/CodeSystem/mkn-10"


@lru_cache
def _rows() -> dict[str, dict]:
    path = get_settings().mkn10_csv
    if not path or not Path(path).exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["KodSTeckou"]: row for row in csv.DictReader(f, delimiter=";")}


def _table() -> dict[str, str]:
    return {code: row["Nazev"] for code, row in _rows().items()}


def forbidden_sex(code: str) -> str | None:
    """ÚZIS column NepripustnePohlavi: '1' = not allowed for men (e.g. C53), '2' = not allowed for women (e.g. C61)."""
    row = _rows().get(code)
    return (row.get("NepripustnePohlavi") or None) if row else None


def lookup(code: str) -> str | None:
    """Return the Czech name for an MKN-10 code like 'C50.4', or None if unknown / table not loaded."""
    row = _rows().get(code)
    return row["Nazev"] if row else None


def is_valid(code: str) -> bool | None:
    """True/False when the table is loaded, None when it is not configured."""
    rows = _rows()
    return (code in rows) if rows else None
