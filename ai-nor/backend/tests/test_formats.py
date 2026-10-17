import io
import zipfile
from email.message import EmailMessage

import pymupdf
import pytest

from app import ingest
from app.ingest import formats

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(body_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W}><w:body>{body_xml}</w:body></w:document>')
    return buf.getvalue()


DOCX = _docx(
    "<w:p><w:r><w:t>Propouštěcí zpráva</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>Dg.: </w:t></w:r><w:r><w:t>C50.4</w:t></w:r></w:p>"
    "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>pT</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1c</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
)


def test_word_paragraphs_and_tables():
    (doc,) = ingest.to_documents("propoustecka.docx", DOCX)
    assert doc.text.splitlines() == ["Propouštěcí zpráva", "Dg.: C50.4", "pT | 1c"]
    assert doc.kind == "PZ"


def test_email_body_and_attachments_become_documents():
    msg = EmailMessage()
    msg["From"], msg["Subject"] = "patologie@fno.example", "Histologie – výsledek"
    msg.set_content("Dobrý den, v příloze výsledek. Dg.: C50.4")
    msg.add_attachment(DOCX, maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename="nalez.docx")
    msg.add_attachment(b"ignored", maintype="application", subtype="octet-stream", filename="program.exe")
    docs = ingest.to_documents("posta.eml", msg.as_bytes())
    assert [d.filename for d in docs] == ["posta.eml", "posta.eml › nalez.docx"]
    assert "Předmět: Histologie – výsledek" in docs[0].text and "Dg.: C50.4" in docs[0].text
    assert docs[0].kind == "histology"
    assert "pT | 1c" in docs[1].text


def test_unsupported_type_says_what_is_supported():
    with pytest.raises(ValueError, match="docx"):
        ingest.to_documents("zprava.odt", b"x")


def _scan(text: str) -> bytes:
    """A page with only an image of the text, like a scanner makes."""
    page_doc = pymupdf.open()
    page = page_doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 300), text, fontsize=12, fontname="helv", fontfile=r"C:\Windows\Fonts\arial.ttf")
    pix = page.get_pixmap(dpi=200)
    scan = pymupdf.open()
    scan.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect, pixmap=pix)
    return scan.tobytes()


needs_ocr = pytest.mark.skipif(not (formats.tessdata_dir() / "ces.traineddata").exists(), reason="python -m scripts.get_tessdata")


@needs_ocr
def test_scanned_pdf_is_read_by_ocr():
    (doc,) = ingest.to_documents("sken.pdf", _scan("Histologie: invazivní karcinom NST, G2. Dg.: C50.4"))
    assert doc.text.startswith(formats.OCR_NOTE)
    assert "karcinom" in doc.text and "C50.4" in doc.text


@needs_ocr
def test_photo_is_read_by_ocr():
    pix = pymupdf.open("pdf", _scan("Ambulantní zpráva Dg.: C20"))[0].get_pixmap(dpi=150)
    (doc,) = ingest.to_documents("foto.png", pix.tobytes("png"))
    assert "C20" in doc.text


def test_pdf_with_text_layer_skips_ocr():
    pdf = pymupdf.open()
    pdf.new_page().insert_text((50, 72), "Ambulantni zprava, Dg.: C50.4, klinicky cT1c cN0 cM0")
    (doc,) = ingest.to_documents("az.pdf", pdf.tobytes())
    assert not doc.text.startswith(formats.OCR_NOTE)


def test_pdf_is_read_in_reading_order_not_storage_order():
    # blocks written bottom first and the value before its label, as report generators often store them
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((300, 200), "Zaver: invazivni karcinom NST")
    page.insert_text((200, 100), "106")
    page.insert_text((50, 100), "Hmotnost [kg]:")
    page.insert_text((50, 150), "Nalez:")
    (doc,) = ingest.to_documents("az.pdf", pdf.tobytes())
    lines = doc.text.splitlines()
    assert lines[0] == "Hmotnost [kg]:  106"  # the label and its value on one line, column padding reduced
    assert doc.text.index("Nalez:") < doc.text.index("Zaver:")  # a heading before what follows it
