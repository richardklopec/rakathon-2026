"""Histology report numbers vs. references to them ("viz biopsie č. 5678/2026") across the documents of a case.

A histology report carries its own number right after "NÁLEZ:" (and the page marker "1/1"). Other reports refer to a
biopsy by number. When the case contains histology reports with known numbers and a referenced number matches none of
them, the documents may not belong together (or the reference is wrong): a warning for the clinician. When there is no
other histology to compare with, the referenced report was simply not uploaded: no warning.
"""

import re

from app.models import Document

PREFIX = "Číslo biopsie nesedí: "
_OWN = re.compile(r"NÁLEZ:\s*(?:\d{1,2}\s?/\s?\d{1,2}\s+)?(\d{3,6})\s?/\s?(20\d{2})(?!\d)")
_REF = re.compile(r"(?i)\b(?:biops\w*|bioptick\w*\s+vyšetřen\w*)\s+(?:č\.|číslo)\s*(\d{3,6})(?:\s?[-–]\s?(\d{3,6}))?\s?/\s?(20\d{2})")


def report_numbers(docs: list[Document]) -> dict[str, str]:
    """"1234/2026" -> "Histologie.pdf" for every histology report whose own number is written."""
    out: dict[str, str] = {}
    for doc in docs:
        if doc.kind == "histology" and (m := _OWN.search(doc.text)):
            out.setdefault(f"{int(m.group(1))}/{m.group(2)}", doc.filename)
    return out


def references(docs: list[Document]) -> dict[str, tuple[set[str], list[str]]]:
    """"5678/2026" (as written, ranges kept) -> (numbers it covers, files referring to it)."""
    out: dict[str, tuple[set[str], list[str]]] = {}
    for doc in docs:
        for m in _REF.finditer(doc.text):
            lo, hi, year = int(m.group(1)), int(m.group(2) or m.group(1)), m.group(3)
            label = f"{lo}{'' if hi == lo else f'–{hi}'}/{year}"
            numbers = {f"{n}/{year}" for n in range(lo, min(hi, lo + 50) + 1)}  # "4101-4103/2026"
            files = out.setdefault(label, (numbers, []))[1]
            if doc.filename not in files:
                files.append(doc.filename)
    return out


def check(docs: list[Document]) -> list[str]:
    own = report_numbers(docs)
    out = []
    for label, (numbers, files) in references(docs).items():
        others = {n: f for n, f in own.items() if f not in files}  # a report does not confirm its own reference
        if others and not numbers & set(others):
            have = ", ".join(f"č. {n} ({f})" for n, f in others.items())
            verb = "odkazuje" if len(files) == 1 else "odkazují"
            out.append(f"{PREFIX}{', '.join(files)} {verb} na biopsii č. {label}, histologie v dokumentech ale mají {have}"
                       " – ověřte, že dokumenty patří k sobě a jde o stejnou biopsii.")
    return out
