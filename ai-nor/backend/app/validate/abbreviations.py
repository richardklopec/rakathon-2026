"""Abbreviations whose meaning depends on the context (PLAN step "slovník zkratek").

First entry: a stage group written as a Roman numeral. "IA" is stage IA next to "stadium" or a TNM string, but the
aromatase inhibitor in "hormonoterapie IA"; a Roman numeral opening a line ("I. r. 2004 Ca …") numbers a list.
Breast quadrant abbreviations (HZK, DKK…) and their limb meaning live in validate/site.py.
"""

import re

STAGE_TOKEN = re.compile(r"(?<![A-Za-z0-9])((?:IV|III|II|I)[ABC]?)(?![A-Za-z0-9])")
# the token is about the stage when the text says so: a stage word or a TNM string (pT2 N1 M0, IIB)
STAGE_CONTEXT = re.compile(r"(?i)stádi|stadi|\bst\.\s*(?=[IV])|\bstage\b|\bFIGO\b|(?<![A-Za-z])[cpy]{0,2}T(?:is|[0-4X])")
# right before the token: a therapy or a drug -> IA = inhibitor aromatázy, not a stage
THERAPY_BEFORE = re.compile(r"(?i)(?:hormon\w*|inhibitor\w*|endokrinn\w*|terapi\w*|léčb\w*|\bHT\b|letrozol|anastrozol|"
                            r"exemestan|tamoxifen)\W{0,6}$")


def stage_in(text: str) -> str | None:
    """The stage group written in the text, or None when the Roman numeral means something else."""
    if not text or not STAGE_CONTEXT.search(text):
        return None
    for m in STAGE_TOKEN.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        if THERAPY_BEFORE.search(before):
            continue  # "hormonoterapie IA": aromatase inhibitor
        line_start = text.rfind("\n", 0, m.start()) + 1
        if not text[line_start:m.start()].strip() and text[m.end():m.end() + 1] == ".":
            continue  # "I. r. 2004 …": list numbering
        return m.group(1)
    return None
