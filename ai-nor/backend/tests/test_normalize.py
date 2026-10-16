from app.models import Laterality
from app.validate import normalize as n


def test_icd10_and_morphology():
    assert n.icd10("Dg.: C504") == "C50.4"
    assert n.icd10("C16.3  ZN - antrum pyloricum") == "C16.3"
    assert n.icd10("C61") == "C61"
    assert n.morphology("M1:  M81403") == "8140/3"
    assert n.morphology("8090/3") == "8090/3"
    assert n.morphology("pT1") is None


def test_dates():
    assert n.partial_date("02.04.2026").model_dump() == {"year": 2026, "month": 4, "day": 2}
    assert n.partial_date("4/2026").model_dump() == {"year": 2026, "month": 4, "day": None}
    assert n.partial_date("2026-05-12").day == 12
    assert n.partial_date("2026").month is None


def test_laterality_grade_tnm():
    assert n.laterality("Ca prsu l. sin") == Laterality.left
    assert n.laterality("ovarium vpravo") == Laterality.right
    assert n.laterality("obou ovarií") == Laterality.bilateral
    assert n.grade("G2") == "2" and n.grade("grading: Gx") == "9" and n.grade("středně diferencovaný") == "2"
    assert n.grade("Gleason 3+4=7") is None
    assert n.high_grade("serózní high grade adenokarcinom") == "3"
    assert n.tnm("ypT3 ypN3b", "T") == "3" and n.tnm("ypT3 ypN3b", "N") == "3b"
    assert n.tnm("pT1c pN0(sn)", "N") == "0" and n.tnm("pN1mi", "N") == "1mi" and n.tnm("Mx", "M") == "X"
    assert n.y_prefix("ypT2") and not n.y_prefix("pT2")


def test_lymph_nodes():
    assert n.lymph_nodes("24/19") == (24, 19)
    assert n.lymph_nodes("uzliny 2/22 pozitivní") == (22, 2)
    assert n.lymph_nodes("vyšetřeno 14 uzlin, bez maligních struktur") == (14, 0)


def test_sentinel():
    assert n.sentinel("pN0(sn)") == "0"
    assert n.sentinel("bez metastatického postižení") == "0"
    assert n.sentinel("v 1 LU mikrometastáza velikosti 2 mm") == "1"
    assert n.sentinel("X - nestanovena") == "X"
