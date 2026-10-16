"""Anatomic stage from TNM (UICC TNM, 8th edition), table-driven per site; breast (C50) first.

Only explicit categories are used: TX / NX / MX (or a missing M) give no stage, "no metastases" is never assumed.
Add a site by adding its table to TABLES (rules are tried in order, first match wins).
"""

import re
from dataclasses import dataclass


def t_category(v: str | None) -> str | None:
    """'1b' / 'T1mi' -> '1', 'is' -> 'is', 'X' -> None."""
    if not v:
        return None
    v = str(v).strip().lower().removeprefix("t")
    if v.startswith("is"):
        return "is"
    return m.group(1) if (m := re.match(r"([0-4])", v)) else None


def n_category(v: str | None) -> str | None:
    """'0(i+)' -> '0', '1mi' -> '1mi', '1a' -> '1', '3c' -> '3', 'X' -> None."""
    if not v:
        return None
    v = str(v).strip().lower().removeprefix("n")
    if v.startswith("1mi"):
        return "1mi"
    return m.group(1) if (m := re.match(r"([0-3])", v)) else None


def m_category(v: str | None) -> str | None:
    if not v:
        return None
    v = str(v).strip().lower().removeprefix("m")
    return m.group(1) if (m := re.match(r"([01])", v)) else None


@dataclass
class Rule:
    stage: str
    t: set[str]
    n: set[str]


ANY_T = {"is", "0", "1", "2", "3", "4"}
ANY_N = {"0", "1mi", "1", "2", "3"}

# UICC TNM 8, breast (anatomic stage groups). N1mi counts as N1 except with T0/T1 (stage IB).
BREAST = [
    Rule("0", {"is"}, {"0"}),
    Rule("IA", {"1"}, {"0"}),
    Rule("IB", {"0", "1"}, {"1mi"}),
    Rule("IIA", {"0", "1"}, {"1"}),
    Rule("IIA", {"2"}, {"0"}),
    Rule("IIB", {"2"}, {"1", "1mi"}),
    Rule("IIB", {"3"}, {"0"}),
    Rule("IIIA", {"0", "1", "2"}, {"2"}),
    Rule("IIIA", {"3"}, {"1", "1mi", "2"}),
    Rule("IIIB", {"4"}, {"0", "1mi", "1", "2"}),
    Rule("IIIC", ANY_T, {"3"}),
]
TABLES: dict[str, list[Rule]] = {"C50": BREAST}
SITE = {"C50": "prs"}  # the organ each table is for, named in the explanation of a derived stage


def stage(category: str, t: str | None, n: str | None, m: str | None) -> str | None:
    """Stage for the site category (e.g. "C50"), or None (site without a table, a category unknown, no explicit M)."""
    table = TABLES.get(category)
    mc = m_category(m)
    if table is None or mc is None:
        return None
    if mc == "1":
        return "IV"
    tc, nc = t_category(t), n_category(n)
    if tc is None or nc is None:
        return None
    return next((r.stage for r in table if tc in r.t and nc in r.n), None)
