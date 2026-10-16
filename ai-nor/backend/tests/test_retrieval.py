from app.models import Document
from app.retrieval import chunk_document
from app.retrieval.codes import _clean


def test_chunks_cover_text_with_exact_offsets():
    text = "\n".join(f"Řádek {i}: invazivní karcinom NST, G2, pT1c pN0(sn)." for i in range(60))
    doc = Document(id="d1", filename="x.txt", text=text)
    chunks = chunk_document(doc, size=300, overlap=60)
    assert len(chunks) > 5
    for c in chunks:
        assert text[c.start : c.end] == c.text
        assert len(c.text) <= 300
    assert chunks[0].start == 0 and chunks[-1].end == len(text)
    for a, b in zip(chunks, chunks[1:]):
        assert b.start < a.end  # overlap, nothing lost between chunks


def test_morphology_index_term_cleanup():
    assert _clean("– bazocelulární (M8090/3) – viz Novotvar, kůže, maligní") == "bazocelulární"
    assert _clean("Adenokarcinom (M8140/3) (viz též Novotvar, maligní)") == "Adenokarcinom"
