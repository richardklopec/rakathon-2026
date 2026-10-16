"""Turn values as written in Czech clinical text into NOR form values (contracts/nor_form.md).

Every function returns None when the text cannot be normalised, so the field ends up for review
instead of carrying a guessed value.
"""

import re

from app.models import Laterality, PartialDate

_ICD10 = re.compile(r"\b([CD])\s?(\d{2})(?:\.?(\d{1,2}))?\b")
_MORPH = re.compile(r"\bM?-?(\d{4})\s?/?\s?(\d)\b")


def icd10(text: str) -> str | None:
    """'C504' / 'C50.4' / 'dg. C 50.4' -> 'C50.4'."""
    if m := _ICD10.search(text.upper()):
        letter, num, sub = m.groups()
        return f"{letter}{num}.{sub}" if sub else f"{letter}{num}"
    return None


def morphology(text: str) -> str | None:
    """'M81403' / '8140/3' / 'M-8140/3' -> '8140/3' (only plausible ICD-O neoplasm codes 8000-9999)."""
    if (m := _MORPH.search(text.upper())) and int(m.group(1)) >= 8000:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def partial_date(text: str) -> PartialDate | None:
    t = text.strip()
    if m := re.search(r"\b(\d{4})-(\d{1,2})(?:-(\d{1,2}))?\b", t):  # ISO
        y, mo, d = m.groups()
        return PartialDate(year=int(y), month=int(mo), day=int(d) if d else None)
    if m := re.search(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{2,4})\b", t):  # 2.4.2026 / 2,4,2026 handled below
        d, mo, y = m.groups()
        y = int(y) + 2000 if len(y) == 2 else int(y)
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            return PartialDate(year=y, month=int(mo), day=int(d))
    if m := re.search(r"\b(\d{1,2})\s?/\s?(\d{2,4})\b", t):  # 4/2026, 02/26
        mo, y = m.groups()
        y = int(y) + 2000 if len(y) == 2 else int(y)
        if 1 <= int(mo) <= 12:
            return PartialDate(year=y, month=int(mo))
    if m := re.search(r"\b(19\d{2}|20\d{2})\b", t):
        return PartialDate(year=int(m.group(1)))
    return None


_LATERALITY = [
    (r"oboustran|bilat|obou|l\.\s?dx\.?\s?(a|i|\+)\s?l\.\s?sin", Laterality.bilateral),
    (r"vlevo|lev[éýá]|l\.\s?sin|\bsin\b|sinistr", Laterality.left),
    (r"vpravo|prav[éýá]|l\.\s?dx|\bdx\b|dext", Laterality.right),
    (r"odpad|nepárov|neaplik|střed", Laterality.not_applicable),
    (r"nezn", Laterality.unknown),
]

LATERALITY_NOR = {
    Laterality.right: "1",
    Laterality.left: "2",
    Laterality.bilateral: "3",
    Laterality.not_applicable: "4",
    Laterality.midline: "4",
    Laterality.unknown: "9",
}


LATERALITY_LABEL = {"1": "1 - vpravo", "2": "2 - vlevo", "3": "3 - oboustranně", "4": "4 - odpadá", "9": "9 - neznámo"}


def laterality(text: str) -> Laterality | None:
    t = text.lower()
    for pattern, value in _LATERALITY:
        if re.search(pattern, t):
            return value
    return None


GRADE_NOR = {
    "1": "1 - dobře diferencovaný",
    "2": "2 - středně diferencovaný",
    "3": "3 - špatně diferencovaný",
    "4": "4 - nediferencovaný, anaplastický",
    "5": "5 - T-buňka",
    "6": "6 - B-buňka",
    "7": "7 - Null buňka",
    "8": "8 - NK buňka",
    "9": "9 - neurčen, neuveden, nepoužitelný",
}


def grade(text: str) -> str | None:
    """'G2' / 'grade 2' / 'středně diferencovaný' / 'Gx' -> NOR code. Gleason is not mapped (stays for review)."""
    t = text.lower()
    if "gleason" in t:
        return None
    if re.search(r"\bg\s?x\b|neurč|neuved|nelze", t):
        return "9"
    if m := re.search(r"\b(?:g|grade|grading)\s*([1-4])\b", t):
        return m.group(1)
    for word, code in (("nediferenc", "4"), ("anaplast", "4"), ("špatně", "3"), ("málo", "3"), ("středně", "2"), ("dobře", "1")):
        if word in t:
            return code
    if re.fullmatch(r"\s*[1-4]\s*", t):
        return t.strip()
    return None


def high_grade(text: str) -> str | None:
    """'high grade' carcinoma (e.g. HGSC) -> 3, 'low grade' -> 1."""
    t = text.lower()
    if "high grade" in t or "high-grade" in t:
        return "3"
    if "low grade" in t or "low-grade" in t:
        return "1"
    return None


def tnm(text: str, part: str) -> str | None:
    """Value of one TNM category without prefixes: 'ypT3' -> '3', 'pN1mi' -> '1mi', 'Mx' -> 'X'."""
    t = text.replace(" ", "")
    m = re.search(rf"(?:y?[cp])?{part.upper()}([0-4][a-d]?(?:mi|\(sn\)|\(i[+-]\))?|is|x|X)", t)
    if not m:
        return None
    v = m.group(1)
    return v.upper() if v.lower() == "x" else v.replace("(sn)", "")


def y_prefix(text: str) -> bool:
    return bool(re.search(r"\by[cp]?[TNM]", text))


def lymph_nodes(text: str) -> tuple[int, int] | None:
    """'24/19' (examined/positive), '2/22 pozitivní', 'vyšetřeno 14 uzlin, bez maligních' -> (examined, positive)."""
    t = text.lower()
    if m := re.search(r"(\d{1,3})\s?/\s?(\d{1,3})\s*(?:poz|uzlin|\+)", t):
        a, b = int(m.group(1)), int(m.group(2))
        return (b, a) if a < b else (a, b)  # "2/22 pozitivní" = positive/examined
    if m := re.search(r"(\d{1,3})\s?/\s?(\d{1,3})", t):
        a, b = int(m.group(1)), int(m.group(2))
        return (a, b) if a >= b else (b, a)
    if m := re.search(r"vyšetřeno\s+(\d{1,3})\s+uzlin.*?(bez|žádná|negat)", t):
        return (int(m.group(1)), 0)
    return None


DISEASE_EXTENT_NOR = {"1": "1 - lokalizované", "2": "2 - pokročilé", "9": "9 - neznámo"}


def disease_extent(text: str) -> str | None:
    t = text.lower()
    if re.search(r"lokaliz|localiz|omezen", t):
        return "1"
    if re.search(r"pokroč|generaliz|metast|advanced", t):
        return "2"
    if "nezn" in t:
        return "9"
    return None


SENTINEL_LABEL = {"0": "0 - negativní", "1": "1 - pozitivní", "X": "X - nestanovena"}  # only "X" seen in the form; verify codes


def sentinel(text: str) -> str | None:
    """Sentinel node result -> '0' negative, '1' positive, 'X' not done."""
    t = text.lower()
    if re.search(r"nestanov|neproveden|neprov", t):
        return "X"
    if re.search(r"\bbez\b|negat|pn0|\b0\s?/\s?\d|\(\d+/0\)|nepostiž|benign", t):
        return "0"
    if re.search(r"pozit|mikrometast|metast|pn[1-3]|\b[1-9]\d*\s?/\s?\d|\d+/[1-9]\)", t):
        return "1"
    return None
