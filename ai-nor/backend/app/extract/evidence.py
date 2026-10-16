"""Locate an LLM quote in the source document and return exact offsets (or None = unverified)."""

import re
import unicodedata

from app.models import Document, Evidence


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase, strip accents, collapse whitespace; keep a map normalized index -> original index."""
    out, idx, prev_space = [], [], False
    for i, ch in enumerate(text):
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c)).lower()
        if not base:
            continue
        if base.isspace():
            if prev_space:
                continue
            base, prev_space = " ", True
        else:
            prev_space = False
        for c in base:
            out.append(c)
            idx.append(i)
    return "".join(out), idx


def locate(doc: Document, quote: str) -> Evidence | None:
    quote = quote.strip().strip("„“\"'…")
    if not quote:
        return None
    if (pos := doc.text.find(quote)) >= 0:
        return Evidence(doc_id=doc.id, quote=quote, start=pos, end=pos + len(quote), verified=True)
    norm_doc, mapping = _norm_with_map(doc.text)
    norm_q, _ = _norm_with_map(quote)
    norm_q = norm_q.strip()
    if len(norm_q) < 3:
        return None
    pos = norm_doc.find(norm_q)
    if pos < 0:
        # last resort: ignore punctuation differences
        strip = lambda s: re.sub(r"[^\w ]", "", s)  # noqa: E731
        if strip(norm_q) and strip(norm_q) in strip(norm_doc):
            return Evidence(doc_id=doc.id, quote=quote, start=0, end=0, verified=False)
        return None
    start = mapping[pos]
    end = mapping[pos + len(norm_q) - 1] + 1
    return Evidence(doc_id=doc.id, quote=doc.text[start:end], start=start, end=end, verified=True)
