"""More input formats: scans and photos (OCR), Word (.docx) and e-mail (.eml with attachments).

OCR is the Tesseract engine built into PyMuPDF with Czech language data; it runs locally, nothing leaves the machine.
The language data live in backend/var/tessdata (python -m scripts.get_tessdata).
"""

import email
import html
import io
import re
import uuid
import zipfile
from email import policy
from xml.etree import ElementTree

import pymupdf

from app.config import get_settings
from app.models import Document

# put in front of text that came from OCR, so the reviewer sees it next to the citations (quotes may carry OCR errors)
OCR_NOTE = "[Text získán OCR ze skenu. Citace ověřte proti originálu.]"
IMAGE_TYPES = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "tif": "tiff", "tiff": "tiff", "bmp": "bmp"}
SUPPORTED = ["pdf", "txt", "md", "xlsx", "docx", "eml", *IMAGE_TYPES]
_MIN_TEXT = 20  # a page with less text than this is treated as a scan


def tessdata_dir():
    return get_settings().data_dir / "tessdata"


def page_text(page: pymupdf.Page, textpage=None) -> str:
    """Text of a page in reading order (top to bottom, left to right), not in the order the PDF stores its blocks:
    otherwise a value drifts away from its label ("Hmotnost [kg]:" … "106") and a heading lands after its content.
    Spaces that only aligned the columns are reduced to two, so a label and its value stay on one readable line."""
    text = page.get_text("text", sort=True, textpage=textpage)
    return "\n".join(re.sub(r"[ \t]{2,}", "  ", line.strip()) for line in text.splitlines())


def _ocr(page: pymupdf.Page) -> str:
    folder = tessdata_dir()
    if not (folder / "ces.traineddata").exists():
        raise ValueError("Sken bez textové vrstvy nelze přečíst: chybí data pro OCR (python -m scripts.get_tessdata).")
    textpage = page.get_textpage_ocr(language="ces", dpi=300, full=True, tessdata=str(folder))
    return page_text(page, textpage)


def pdf_or_image_to_text(data: bytes, filetype: str = "pdf") -> str:
    """Text layer of each page; pages without one (scans, photos) go through OCR."""
    doc = pymupdf.open(stream=data, filetype=filetype)
    if filetype != "pdf":  # a photo or a scanned image: make it a PDF page first
        doc = pymupdf.open("pdf", doc.convert_to_pdf())
    pages, ocr = [], False
    with doc:
        for page in doc:
            text = page_text(page)
            if len(text.strip()) < _MIN_TEXT and (filetype != "pdf" or page.get_images()):
                text, ocr = _ocr(page), True
            pages.append(text)
    body = "\n\n".join(pages)
    return f"{OCR_NOTE}\n\n{body}" if ocr else body


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _paragraph(p) -> str:
    out = []
    for el in p.iter():
        if el.tag == f"{_W}t" and el.text:
            out.append(el.text)
        elif el.tag == f"{_W}tab":
            out.append("\t")
        elif el.tag in (f"{_W}br", f"{_W}cr"):
            out.append("\n")
    return "".join(out)


def docx_to_text(data: bytes) -> str:
    """Word document: paragraphs and tables (a row as 'cell | cell'). Plain zip + XML, no extra dependency."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        body = ElementTree.fromstring(z.read("word/document.xml")).find(f"{_W}body")
    lines = []
    for block in body if body is not None else []:
        if block.tag == f"{_W}p":
            lines.append(_paragraph(block))
        elif block.tag == f"{_W}tbl":
            for row in block.iter(f"{_W}tr"):
                lines.append(" | ".join(" ".join(_paragraph(p) for p in cell.iter(f"{_W}p")).strip() for cell in row.iter(f"{_W}tc")))
    return "\n".join(lines)


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", markup)
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def eml_to_documents(data: bytes, filename: str) -> list[Document]:
    """E-mail (.eml): the message is one document, each supported attachment becomes further documents."""
    from app.ingest import _normalise, guess_kind, to_documents  # the package imports this module

    msg = email.message_from_bytes(data, policy=policy.default)
    head = [f"{label}: {msg[key]}" for key, label in (("From", "Od"), ("To", "Komu"), ("Date", "Datum"), ("Subject", "Předmět")) if msg[key]]
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    if body is not None and body.get_content_type() == "text/html":
        text = _html_to_text(text)
    subject = str(msg["Subject"] or "")
    docs = [Document(id=str(uuid.uuid4()), filename=filename, kind=guess_kind(subject or filename),
                     text=_normalise("\n".join(head) + "\n\n" + text))]
    for part in msg.iter_attachments():
        name = part.get_filename() or "priloha"
        if name.lower().rsplit(".", 1)[-1] in SUPPORTED:
            docs += to_documents(f"{filename} › {name}", part.get_payload(decode=True))
    return docs
