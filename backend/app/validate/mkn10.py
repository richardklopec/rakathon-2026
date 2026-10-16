"""MKN-10 (Czech ICD-10) lookup from the ÚZIS CSV (`01_MKN10_5E_2026_utf8.csv`, ';'-separated)."""

import csv
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

ICD10_SYSTEM = "https://uzis.cz/terminology/CodeSystem/mkn-10"


@lru_cache
def _table() -> dict[str, str]:
    path = get_settings().mkn10_csv
    if not path or not Path(path).exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["KodSTeckou"]: row["Nazev"] for row in csv.DictReader(f, delimiter=";")}


def lookup(code: str) -> str | None:
    """Return the Czech name for an MKN-10 code like 'C50.4', or None if unknown / table not loaded."""
    return _table().get(code)


def is_valid(code: str) -> bool | None:
    """True/False when the table is loaded, None when it is not configured."""
    table = _table()
    return (code in table) if table else None
