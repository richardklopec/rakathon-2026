"""validate/site.py: subsite of the breast from the site descriptions (synthetic texts)."""

from app.models import Document
from app.validate import site


def _d(name: str, text: str) -> Document:
    return Document(id=name, filename=name, kind="AZ", text=text)


def test_quadrants_from_tumour_lines():
    docs = [_d("a", "Ca prsu vlevo v HZK, ložisko 12 mm"), _d("b", "ložisko na rozhraní DKK vlevo")]
    assert site.subsites("C50", docs) == {".4": ["a"], ".8": ["b"]}
    assert site.subsites("C50", [_d("c", "karcinom prsu retroareolárně vpravo")]) == {".1": ["c"]}
    assert site.subsites("C50", [_d("d", "tumor v horním zevním kvadrantu")]) == {".4": ["d"]}


def test_examination_and_other_meanings_do_not_count():
    exam = _d("e", "st. localis: prs vlevo po resekci, bradavka bpn, HZK bez rezistence\nDKK bez otoků")
    assert site.subsites("C50", [exam]) == {}  # no tumour word, normal findings, lower limbs
    assert site.subsites("C50", [_d("f", "ložisko 3 cm od bradavky, bradavka bpn")]) == {}  # a distance, not the site
    assert site.subsites("C50", [_d("g", "karcinom bradavky vlevo")]) == {".0": ["g"]}


def test_check_and_evidence():
    docs = [_d("b", "ložisko na rozhraní DKK vlevo")]
    assert site.check("C50.8", docs)[0] is True
    assert site.check("C50.4", docs)[0] is False
    assert site.check("C50.9", docs)[0] is False  # NS although the site is described
    assert site.check("C34.1", docs)[0] is None  # category without rules
    assert site.check("C50.4", [_d("x", "bez popisu")])[0] is None
    ev = site.evidence("C50.8", docs)
    assert len(ev) == 1 and ev[0].verified and "rozhraní DKK" in ev[0].quote and docs[0].text[ev[0].start:ev[0].end] == docs[0].text


def test_descriptions_list_every_described_site():
    docs = [_d("a", "Ca prsu vlevo v HZK\nkontrola za 3 měsíce"), _d("b", "ložisko na rozhraní DKK")]
    assert [e.quote for e in site.descriptions("C50", docs)] == ["Ca prsu vlevo v HZK", "ložisko na rozhraní DKK"]
