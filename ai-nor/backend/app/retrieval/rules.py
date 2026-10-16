"""MKN-10 coding rules from the ÚZIS PDF 'Tabelární část' (mkn-tabelarni-cast_1-4-2014_2.pdf) in IRIS Vector Search.

The PDF adds what the 2026 CSV does not have: inclusion / exclusion notes ("Patří sem / Nepatří sem"), chapter and group
notes (e.g. chapter II note 5 on overlapping lesions .8) and the general coding rules from the introduction.
Valid codes and names still come from the 2026 CSV; the PDF (2014) is used only as rules the LLM must cite.

Table Nor.Rule: Kind (category | note), Code (C50, or a range like C00–D48 / ÚVOD), Title, Text, Page, Embedding.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app import iris_db
from app.config import get_settings
from app.retrieval.embeddings import embed

SOURCE = "MKN-10, Tabelární část (ÚZIS, 2014)"
TOC_PAGES = range(24, 36)  # 0-based: table of contents, skipped
NOTE_CHUNK = 1500

_CATEGORY = re.compile(r"^([A-Z]\d{2})$")
_RANGE = re.compile(r"\(([A-Z]\d{2}(?:[–-][A-Z]\d{2})?)\)")


@dataclass
class RuleEntry:
    kind: str  # category | note
    code: str
    title: str
    text: str
    page: int  # printed page number (PDF index + 1)


@dataclass
class RuleHit(RuleEntry):
    score: float


def _lines(page) -> list[tuple[float, float, str, list]]:
    """Rebuild text lines from word positions: (y, x0, text, words). The PDF pages are single-column."""
    rows: dict[int, list] = {}
    for w in page.get_text("words"):
        rows.setdefault(round(w[1] / 2.5), []).append(w)
    out = []
    for key in sorted(rows):
        ws = sorted(rows[key], key=lambda w: w[0])
        out.append((ws[0][1], ws[0][0], " ".join(w[4] for w in ws), ws))
    return out


def _is_heading(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.9


def parse_pdf(path: str | Path) -> list[RuleEntry]:
    import pymupdf

    doc = pymupdf.open(str(path))
    entries: list[RuleEntry] = []
    group_title, group_code, group_notes, group_page = "ÚVOD", "ÚVOD", [], 1
    cat: RuleEntry | None = None
    last_heading_y = None

    def flush_cat():
        nonlocal cat
        if cat:
            entries.append(cat)
            cat = None

    def flush_notes(force: bool = False):
        nonlocal group_notes
        text = "\n".join(group_notes).strip()
        if text and (force or len(text) >= NOTE_CHUNK):
            for i in range(0, len(text), NOTE_CHUNK):
                entries.append(RuleEntry("note", group_code, group_title, text[i : i + NOTE_CHUNK], group_page))
            group_notes = []

    for pno in range(doc.page_count):
        if pno in TOC_PAGES:
            continue
        page = doc[pno]
        height = page.rect.height
        for y, x0, text, words in _lines(page):
            if y < 33 or y > height - 25:  # running header / footer ("108 / II. KAPITOLA")
                continue
            first = words[0][4]
            if _CATEGORY.match(first) and x0 < 45:  # "C50 Zhoubný novotvar prsu"
                flush_cat()
                flush_notes(force=True)
                cat = RuleEntry("category", first, text[len(first):].strip(), "", pno + 1)
                context = [group_title] + [n for n in group_notes if n.startswith(("Patří", "Nepatří", "Pozn"))]
                cat.text = "Skupina: " + " | ".join(context)[:400] + "\n" + text
                last_heading_y = None
                continue
            if first == "." and len(words) > 1 and words[1][4].isdigit() and cat:  # ". 4 Horní zevní kvadrant prsu"
                cat.text += f"\n{cat.code}.{words[1][4]} " + " ".join(w[4] for w in words[2:])
                continue
            if _is_heading(text) and x0 < 40:  # group / chapter heading, may span two lines
                flush_cat()
                if last_heading_y is not None and y - last_heading_y < 16:
                    group_title += " " + text
                else:
                    flush_notes(force=True)
                    group_title, group_page = text, pno + 1
                if m := _RANGE.search(group_title):
                    group_code = m.group(1).replace("-", "–")
                last_heading_y = y
                continue
            last_heading_y = None
            if cat:
                cat.text += "\n" + text
            else:
                group_notes.append(text)
                flush_notes()
    flush_cat()
    flush_notes(force=True)
    return entries


def _pdf_path() -> Path:
    path = get_settings().mkn10_rules_pdf
    if not path or not Path(path).exists():
        raise RuntimeError(f"MKN10_RULES_PDF not found: {path}")
    return Path(path)


def index_rules() -> dict[str, int]:
    entries = parse_pdf(_pdf_path())
    # the embedding model reads ~128 tokens: code + title + start of the text carry the meaning
    vectors = embed([f"{e.code} {e.title}. {e.text[:400]}" for e in entries])
    with iris_db.cursor() as cur:
        cur.execute("DELETE FROM Nor.Rule")
        cur.executemany(
            "INSERT INTO Nor.Rule (Kind, Code, Title, Text, Page, Embedding) VALUES (?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE))",
            [[e.kind, e.code, e.title[:500], e.text[:8000], e.page, iris_db.to_vector(v)] for e, v in zip(entries, vectors)],
        )
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.kind] = counts.get(e.kind, 0) + 1
    return counts


_ONCO = "(Code LIKE 'C%' OR Code LIKE 'D0%' OR Code LIKE 'D3%' OR Code LIKE 'D4%')"


def get_category(code: str) -> RuleHit | None:
    with iris_db.cursor() as cur:
        cur.execute("SELECT TOP 1 Kind, Code, Title, Text, Page FROM Nor.Rule WHERE Kind = 'category' AND Code = ?", [code[:3]])
        row = cur.fetchone()
        return RuleHit(*row, score=1.0) if row else None  # IRIS rows are unreadable once the cursor closes


def search_rules(query: str, kind: str = "category", top_k: int = 5, oncology_only: bool = True) -> list[RuleHit]:
    """Most similar rule entries (IRIS VECTOR_COSINE). Notes of chapter II are filtered by their range code."""
    qv = iris_db.to_vector(embed([query])[0])
    where = "Kind = ?"
    if oncology_only:
        where += f" AND {_ONCO}" if kind == "category" else " AND (Code LIKE 'C%' OR Code = 'ÚVOD')"
    with iris_db.cursor() as cur:
        cur.execute(
            f"SELECT TOP {int(top_k)} Kind, Code, Title, Text, Page, VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score"
            f" FROM Nor.Rule WHERE {where} ORDER BY Score DESC",
            [qv, kind],
        )
        return [RuleHit(*r[:5], score=float(r[5])) for r in cur.fetchall()]


def chapter_notes(code: str = "C00–D48") -> list[RuleHit]:
    """All notes of a chapter (chapter II has ~6 600 characters, small enough to send whole)."""
    with iris_db.cursor() as cur:
        cur.execute("SELECT Kind, Code, Title, Text, Page FROM Nor.Rule WHERE Kind = 'note' AND Code = ? ORDER BY ID", [code])
        return [RuleHit(*r, score=1.0) for r in cur.fetchall()]


_MORPH_WORDS = re.compile(
    r"\b(zhoubn\w*|karcinom\w*|adenokarcinom\w*|novotvar\w*|nádor\w*|tumor\w*|ca|invazivn\w*|infiltruj\w*|"
    r"spinocelul\w*|dlaždicob\w*|bazocelul\w*|duktáln\w*|lobulárn\w*|serózn\w*|high|low|grade|nst|g\d|p?[tnm]\d\w*)\b",
    re.IGNORECASE,
)


def candidate_categories(query: str, literal: str | None = None, top_k: int = 8) -> list[RuleHit]:
    """Union of: category of a code written in the documents, categories of the best MKN-10 code-list hits
    (Nor.Code, good at organ names) and vector hits in Nor.Rule. Recall matters more than precision here."""
    from app.retrieval.codes import MKN10, search_codes

    site_query = " ".join(_MORPH_WORDS.sub(" ", query).split()) or query
    order: list[str] = []
    if literal:
        order.append(literal[:3])
    for code in re.findall(r"\b([CD]\d{2})", query.upper()):
        order.append(code)
    order += [h.code[:3] for h in search_codes(MKN10, site_query, 6)]
    order += [h.code for h in search_rules(site_query, top_k=4)]
    seen, out = set(), []
    for code in order:
        if code in seen:
            continue
        seen.add(code)
        if hit := get_category(code):
            out.append(hit)
        if len(out) >= top_k:
            break
    return out
