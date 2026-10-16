# Synthetic birth numbers generated to pass / fail the rules, not real people.
from datetime import date

from app.models import Document, Extracted, FieldStatus, NorReport, PartialDate
from app.validate import rodne_cislo as rc

TODAY = date(2026, 10, 16)


def test_valid_numbers():
    man = rc.check("850315/0007", TODAY)
    assert man.valid and man.sex == "M" and man.birth_date == date(1985, 3, 15)
    woman = rc.check("905701/0006", TODAY)
    assert woman.valid and woman.sex == "F" and woman.birth_date == date(1990, 7, 1)
    assert rc.check("8503150007", TODAY).normalized == "850315/0007"  # without slash
    assert rc.check("850315 / 0007", TODAY).valid
    assert rc.check("500101/123", TODAY).valid  # 9 digits before 1954, no check digit
    plus20 = rc.check("052315/0001", TODAY)  # month + 20 from 2004
    assert plus20.valid and plus20.birth_date == date(2005, 3, 15)
    assert rc.check("800101/0040", TODAY).valid  # check-digit exception (mod 10 -> 0) until 1985


def test_invalid_numbers():
    assert "nesedí kontrolní číslice" in rc.check("850315/0008", TODAY).errors[0]
    assert "neplatné datum" in rc.check("850230/0004", TODAY).errors[0]
    assert "devítimístné" in rc.check("600101/123", TODAY).errors[0]
    assert "výjimka" in rc.check("900101/0030", TODAY).errors[0]
    assert any("až od roku 2004" in e for e in rc.check("992315/0000", TODAY).errors)
    assert any("budoucnosti" in e for e in rc.check("261231/0010", TODAY).errors)
    assert not rc.check("PAC001", TODAY).valid
    assert rc.looks_like("850315/0007") and not rc.looks_like("PAC001") and not rc.looks_like("DEMO")


def test_find_in_text():
    text = "Pacientka RČ: 9057010006, kontrola 850315 / 0007. Tel. 603123456, č. vzorku 2026/151516."
    assert [x.normalized for x in rc.find_in_text(text)] == ["905701/0006", "850315/0007"]
    assert rc.find_in_text("8503150007 bez označení") == []  # plain digits only after a label


def _doc(name: str, text: str) -> Document:
    return Document(id=name, filename=name, text=text)


def test_case_checks():
    same = [_doc("az.txt", "RČ: 905701/0006"), _doc("hist.txt", "r.č. 9057010006")]
    assert rc.case_checks(same, NorReport()) == []  # the same number written two ways is not a mismatch

    other = [_doc("az.txt", "RČ: 905701/0006"), _doc("hist.txt", "RČ: 850315/0007")]
    assert any(w.startswith("Nesoulad identity") for w in rc.case_checks(other, NorReport()))

    bad = rc.case_checks([_doc("az.txt", "RČ: 850315/0008")], NorReport())
    assert bad and bad[0].startswith("Neplatné rodné číslo 850315/0008 (az.txt)")

    mismatch = rc.case_checks(same, NorReport(), patient_ref="850315/0007")
    assert any("se neshoduje" in w for w in mismatch)

    sex = rc.case_checks(same, NorReport(), llm_sex="M")
    assert any("Pohlaví podle rodného čísla (žena)" in w for w in sex)

    report = NorReport(diagnosis_date=Extracted[PartialDate](value=PartialDate(year=1989), status=FieldStatus.found))
    assert any("před datem narození" in w for w in rc.case_checks(same, report))


def test_identity_compares_labelled_numbers_even_when_invalid():
    # anonymised data: numbers fail the check, but the documents must still agree with each other
    docs = [_doc("az.txt", "Pacient r.č. 991399/1111"), _doc("hist1.txt", "Bydliště: Č. poj.: 991399/1111"),
            _doc("hist2.txt", "Č. poj.: 991399/2222"), _doc("hist3.txt", "číslo pojištěnce 991399/1111")]
    w = rc.case_checks(docs, NorReport())
    assert w[0].startswith("Nesoulad identity") and "991399/2222 (neplatné) v hist2.txt" in w[0]
    invalid = [x for x in w if x.startswith("Neplatné rodné číslo")]
    assert len(invalid) == 2  # one per number, not one per document
    assert "991399/1111 (az.txt, hist1.txt, hist3.txt)" in invalid[0]


def test_unlabelled_invalid_numbers_are_ignored():
    # e.g. a lab sample number of the same shape: not an identifier unless labelled or a valid birth number
    docs = [_doc("hist.txt", "vzorek 202604/1234, RČ: 905701/0006"), _doc("az.txt", "r. č. 905701/0006")]
    assert rc.case_checks(docs, NorReport()) == []
