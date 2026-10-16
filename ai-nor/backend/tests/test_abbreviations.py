"""validate/abbreviations.py: Roman numerals read in context (synthetic texts)."""

from app.validate.abbreviations import stage_in


def test_stage_only_in_stage_context():
    assert stage_in("Klinické stádium: IIB") == "IIB"
    assert stage_in("st. IIIA dle TNM") == "IIIA"
    assert stage_in("pT2 N1 M0, IIB") == "IIB"  # next to a TNM string
    assert stage_in("FIGO IC") == "IC"


def test_other_meanings_of_roman_numerals():
    assert stage_in("od 3/2026 hormonoterapie IA") is None  # aromatase inhibitor, no stage context at all
    assert stage_in("pT1c N0 M0, od 3/2026 hormonoterapie IA") is None  # stage context, but IA follows the therapy
    assert stage_in("pT1c N0 M0, léčba: inhibitor IA, stadium IA") == "IA"  # the second IA is the stage
    assert stage_in("I. r. 1998 Ca recta, pT3N0M0") is None  # list numbering at the start of a line
    assert stage_in("bez popisu") is None
