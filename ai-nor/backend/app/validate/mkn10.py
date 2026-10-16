"""MKN-10 (Czech ICD-10) lookup from the ÚZIS CSV (`01_MKN10_5E_2026_*.csv`, ';'-separated, see codefiles.py)."""

from functools import lru_cache

from app.validate import codefiles

ICD10_SYSTEM = "https://uzis.cz/terminology/CodeSystem/mkn-10"


@lru_cache
def _rows() -> dict[str, dict]:
    return {row["KodSTeckou"]: row for row in codefiles.dict_rows(codefiles.MKN10)}


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


def topography_label(code: str) -> str | None:
    """'C34.1' -> 'C34.1 - Horní lalok, průduška nebo plíce' (form style: site name without 'Zhoubný novotvar –')."""
    row = _rows().get(code)
    if not row:
        return None
    name = (row.get("NazevPlny") or row["Nazev"]).split("–", 1)[-1].strip()
    return f"{code} - {name[:1].upper()}{name[1:]}"
