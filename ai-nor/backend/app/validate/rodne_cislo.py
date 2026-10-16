"""Czech birth number (rodné číslo, RČ) validation and case-level identity checks.

Rules (zákon č. 133/2000 Sb.):
- born before 1954: 9 digits RRMMDD/XXX, no check digit
- born 1954 and later: 10 digits RRMMDD/XXXX, the whole number is divisible by 11;
  exception until 1985: when the first 9 digits mod 11 = 10, the check digit is 0
- women: month + 50; from 2004 the month may also carry + 20 (men 21-32, women 71-82) when a day runs out of numbers
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.models import Document, FieldStatus, NorReport
from app.validate import mkn10

Sex = Literal["M", "F"]

_SHAPE = re.compile(r"(\d{6})\s?/?\s?(\d{3,4})")
# slash form anywhere ("530101/123", "855201 / 1234"), plain digits only right after a label ("RČ: 8552011234")
_WITH_SLASH = re.compile(r"(?<![\d/])(\d{6})\s?/\s?(\d{3,4})(?![\d/])")
# identifier labels in Czech reports: "r. č.", "RČ", "rodné číslo", and in histology headers "Č. poj." (číslo pojištěnce,
# which for Czech insurees is the birth number)
_LABEL = r"(?:\br\.\s?č\.?|\brč\b|rodné\s+číslo|\bč\.\s?poj\.?|číslo\s+pojištěnce)"
_LABELLED = re.compile(rf"(?i){_LABEL}\s*[:.]?\s*(\d{{6}})\s?/?\s?(\d{{3,4}})(?![\d/])")


@dataclass
class RodneCislo:
    raw: str
    normalized: str | None = None  # RRMMDD/XXXX
    errors: list[str] = field(default_factory=list)
    birth_date: date | None = None
    sex: Sex | None = None
    labelled: bool = False  # written after "r. č." / "Č. poj." etc. (set by find_in_text)

    @property
    def valid(self) -> bool:
        return self.normalized is not None and not self.errors


def looks_like(text: str) -> bool:
    """True when the text is shaped like an RČ (so it must pass check()), False for anonymised ids like 'PAC001'."""
    return bool(re.fullmatch(r"[\d\s/]+", text.strip())) and sum(c.isdigit() for c in text) >= 6


def check(text: str, today: date | None = None) -> RodneCislo:
    today = today or date.today()
    raw = text.strip()
    m = _SHAPE.fullmatch(raw)
    if not m:
        return RodneCislo(raw, errors=["nemá tvar RRMMDD/XXXX (9 nebo 10 číslic)"])
    head, tail = m.groups()
    digits = head + tail
    yy, mm, dd = int(head[:2]), int(head[2:4]), int(head[4:6])
    rc = RodneCislo(raw, normalized=f"{head}/{tail}")

    if len(digits) == 9:
        year = 1900 + yy
        if year >= 1954:
            rc.errors.append("devítimístné rodné číslo se přidělovalo jen narozeným před rokem 1954")
    else:
        year = 1900 + yy if yy >= 54 else 2000 + yy

    sex: Sex = "M"
    month, plus20 = mm, False
    if mm > 70:
        month, sex, plus20 = mm - 70, "F", True
    elif mm > 50:
        month, sex = mm - 50, "F"
    elif mm > 20:
        month, plus20 = mm - 20, True
    if plus20 and year < 2004:
        rc.errors.append("měsíc zvýšený o 20 se používá až od roku 2004")

    try:
        rc.birth_date = date(year, month, dd)
        rc.sex = sex
    except ValueError:
        rc.errors.append(f"neplatné datum narození (den {dd}, měsíc {mm})")
    if rc.birth_date and rc.birth_date > today:
        rc.errors.append("datum narození je v budoucnosti")

    if len(digits) == 10 and int(digits) % 11:
        if int(digits[:9]) % 11 == 10 and digits[9] == "0":
            if year > 1985:
                rc.errors.append("výjimka kontrolní číslice (zbytek 10 → 0) platí jen do roku 1985")
        else:
            rc.errors.append("nesedí kontrolní číslice (číslo není dělitelné 11)")
    return rc


def find_in_text(text: str) -> list[RodneCislo]:
    """Birth numbers written in a document: slash form anywhere, plain 10 digits only after 'RČ' / 'rodné číslo'."""
    seen: dict[int, RodneCislo] = {}
    for pattern in (_WITH_SLASH, _LABELLED):
        for m in pattern.finditer(text):
            rc = seen.setdefault(m.start(1), check(f"{m.group(1)}/{m.group(2)}"))
            rc.labelled = rc.labelled or pattern is _LABELLED
    return [seen[k] for k in sorted(seen)]


def identifiers(docs: list[Document]) -> dict[str, tuple[RodneCislo, list[str]]]:
    """Patient identifiers per document: normalized number -> (check result, files).

    A labelled number counts even when it fails the check (anonymised data, typos: the documents must still agree);
    an unlabelled one only when it is a valid birth number (otherwise it may be any other number of that shape).
    """
    found: dict[str, tuple[RodneCislo, list[str]]] = {}
    for doc in docs:
        for rc in find_in_text(doc.text):
            if rc.valid or rc.labelled:
                files = found.setdefault(rc.normalized, (rc, []))[1]
                if doc.filename not in files:
                    files.append(doc.filename)
    return found


def case_checks(docs: list[Document], report: NorReport, patient_ref: str | None = None, llm_sex: str | None = None) -> list[str]:
    """Case-level warnings: invalid or conflicting birth numbers, sex vs. birth number and vs. diagnosis.

    Lowers the confidence of icd10 when the diagnosis is not allowed for the patient's sex (review policy runs after).
    """
    warnings: list[str] = []
    ids = identifiers(docs)
    valid = {k: v for k, v in ids.items() if v[0].valid}

    if len(ids) > 1:  # most important first: the documents may belong to different patients
        where = "; ".join(f"{k}{'' if rc.valid else ' (neplatné)'} v {', '.join(files)}" for k, (rc, files) in ids.items())
        warnings.append(f"Nesoulad identity: dokumenty uvádějí různá rodná čísla / čísla pojištěnce ({len(ids)}): {where}.")
    for k, (rc, files) in ids.items():  # one warning per number, not per document
        if not rc.valid:
            warnings.append(f"Neplatné rodné číslo {k} ({', '.join(files)}): {'; '.join(rc.errors)}.")

    if patient_ref and looks_like(patient_ref):
        p = check(patient_ref)
        if not p.valid:
            warnings.append(f"Rodné číslo pacienta {patient_ref} je neplatné: {'; '.join(p.errors)}.")
        elif ids and p.normalized not in ids:
            warnings.append(f"Rodné číslo pacienta {p.normalized} se neshoduje s rodným číslem v dokumentech.")

    rc_sex = next(iter(valid.values()))[0].sex if len(valid) == 1 else None
    if rc_sex and llm_sex in ("M", "F") and llm_sex != rc_sex:
        warnings.append(f"Pohlaví podle rodného čísla ({'muž' if rc_sex == 'M' else 'žena'}) nesouhlasí s pohlavím v dokumentaci.")

    sex = rc_sex or (llm_sex if llm_sex in ("M", "F") else None)
    icd = report.icd10.value if report.icd10.status != FieldStatus.missing else None
    if icd and sex:
        rule = mkn10.forbidden_sex(icd)
        if (rule == "1" and sex == "M") or (rule == "2" and sex == "F"):
            warnings.append(f"Diagnóza {icd} není podle MKN-10 přípustná pro pohlaví pacienta.")
            report.icd10.confidence = min(report.icd10.confidence or 0, 40)
            report.icd10.confidence_reasons.append("✗ nepřípustné pohlaví podle MKN-10")

    dg = report.diagnosis_date.value if report.diagnosis_date.status != FieldStatus.missing else None
    birth = next(iter(valid.values()))[0].birth_date if len(valid) == 1 else None
    if dg and birth and (dg.year, dg.month or 12, dg.day or 31) < (birth.year, birth.month, birth.day):
        warnings.append("Datum stanovení diagnózy je před datem narození podle rodného čísla.")
    return warnings
