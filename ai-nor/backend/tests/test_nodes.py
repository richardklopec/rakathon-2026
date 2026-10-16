"""extract/nodes.py: lymph node counts per specimen (synthetic reports with the structure of real histology reports)."""

from app.extract import live, nodes
from app.extract.live import FieldMentions, LlmExtraction, Mention
from app.models import Document, FieldStatus


def _h(name: str, topo: str, findings: str) -> Document:
    text = (f"PRŮVODNÍ LIST K ZÁSILCE BIOPTICKÉHO MATERIÁLU\nTOPOGRAFIE ODBĚRU: {topo}\nNÁLEZ:\n1/1\n1234/2026\n"
            f"Makropopis: zaslána částice s 1 uzlíkem velikosti 5 mm.\nMikropopis: {findings}")
    return Document(id=name, filename=name, kind="histology", text=text)


SLN = _h("H_sln.pdf", "axila vpravo", "zastižena tuková tkáň a 1 částečně lipomatózně změněná sentinelová lymfatická uzlina, bez známek malignity.")
NON_SLN = _h("H_non.pdf", "axila vpravo", "zastižena tuková tkáň a 2 lymfatické uzliny se sinusovou histiocytózou, bez přítomnosti maligních struktur.")
RESECTION = _h("H_res.pdf", "prs vpravo", "invazivní karcinom.\nZávěr:\n8. Sentinelová lymfatická uzlina: Sentinelové lymfatické uzliny bez známek malignity (2/0)")
AZ = Document(id="az", filename="AZ.pdf", kind="AZ", text="Histologie: pT1c N0( 0/3)M0")
MDT = Document(id="mdt", filename="MDT.pdf", kind="MDT", text="TNM: pT1c N0 /3/0/ Mx")


def test_specimens_are_summed_references_and_summaries_only_checked():
    res = nodes.count([SLN, NON_SLN, RESECTION, AZ, MDT])
    assert (res.examined, res.positive) == (3, 0)
    assert [c.doc.filename for c in res.specimens] == ["H_sln.pdf", "H_non.pdf"]
    assert [(c.doc.filename, c.examined) for c in res.references] == [("H_res.pdf", 2)]  # quoted, not summed
    assert [(c.doc.filename, c.examined, c.positive) for c in res.summaries] == [("AZ.pdf", 3, 0), ("MDT.pdf", 3, 0)]
    assert nodes.check(res) == []  # the reference matches the non-SLN specimen, the summaries the total


def test_resection_with_own_dissection_uses_its_total():
    gastric = _h("H.pdf", "žaludek", "počet a stav mízních uzlin: vyšetření uzlin - 47/0 (46/0 + 1/0 v rámci hlavního resekátu).")
    pelvis = _h("H2.pdf", "děloha", "pánev vpravo 7 uzlin vyšetřených, žádná pozitivní; pánev vlevo 9 uzlin vyšetřených; "
                                    "celkem vyšetřeno 23 lymfatických uzlin bez nádoru.")
    assert (nodes.count([gastric]).examined, nodes.count([gastric]).positive) == (47, 0)
    assert (nodes.count([pelvis]).examined, nodes.count([pelvis]).positive) == (23, 0)


def test_micrometastasis_counts_as_positive_and_repeated_reports_once():
    sln = _h("S.pdf", "axila vlevo", "vyšetřeny celkem 2 lymfatické uzliny (LU), v 1 LU zastižena mikrometastáza 2 mm.")
    res = nodes.count([sln, sln.model_copy(update={"id": "S2", "filename": "S_kopie.pdf"})])
    assert (res.examined, res.positive) == (2, 1) and len(res.specimens) == 1


def test_layout_fragments_and_nodules_never_count():
    # "1/1" page marker, "1234/2026" case number, "1 uzlíkem" (a nodule in the gross description)
    assert nodes.count([_h("X.pdf", "axila vlevo", "tuková tkáň bez lymfatické tkáně.")]).examined is None


def test_summary_disagreeing_with_specimens_is_a_conflict():
    az = Document(id="az", filename="AZ.pdf", kind="AZ", text="pT1c N0( 0/5)M0")
    res = nodes.count([SLN, NON_SLN, az])
    assert nodes.check(res) and "souhrn 5/0 v AZ.pdf" in nodes.check(res)[0]
    f = live._node_field(res, "examined", [])
    assert f.value == 3 and f.status == FieldStatus.conflict and f.alternatives == [5]


def test_live_uses_specimens_and_demotes_fragments(monkeypatch):
    def llm(system, user, schema):
        m = Mention(doc=3, quote="Sentinelové lymfatické uzliny bez známek malignity (2/0)", value="2/0", explicit=True, hedged=False)
        return LlmExtraction(primary_tumour="karcinom prsu", other_tumours=[], patient_sex="F",
                             fields=[FieldMentions(field="lymph_nodes", mentions=[m])])

    monkeypatch.setattr(live.llm, "structured", llm)
    r, warnings, _ = live.extract_live([SLN, NON_SLN, RESECTION, AZ, MDT])
    assert r.pn_examined.value == 3 and r.pn_positive.value == 0
    assert r.pn_examined.confidence == 85  # 70 − 5 (sum of 2 specimens) + 20 (AZ and MDT agree)
    assert {e.doc_id for e in r.pn_examined.evidence} >= {"H_sln.pdf", "H_non.pdf"}
    assert not any(w.startswith("Počet uzlin") for w in warnings)
    page = Document(id="p", filename="P.pdf", kind="histology", text="NÁLEZ:\n(2/0)\nbez známek malignity")
    assert live._is_fragment(page, None, "(2/0)")
    assert not live._is_fragment(AZ, None, "pT1c N0( 0/3)M0")
