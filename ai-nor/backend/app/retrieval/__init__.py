"""Document chunks in IRIS Vector Search (table Nor.Chunk): index a case, find passages for a field group.

Offsets (StartPos/EndPos) point into Document.text, so a hit can be turned straight into Evidence.
"""

from dataclasses import dataclass

from app import iris_db
from app.models import Case, Document
from app.retrieval.embeddings import embed

CHUNK_SIZE = 600
CHUNK_OVERLAP = 120


@dataclass
class Chunk:
    doc_id: str
    start: int
    end: int
    text: str


@dataclass
class Hit(Chunk):
    score: float


def chunk_document(doc: Document, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[Chunk]:
    """Split on line boundaries into ~size-char chunks with overlap; offsets are exact."""
    text, chunks, start = doc.text, [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + size // 2, end)  # prefer a line break in the second half
            if cut == -1:
                cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut > start else end
        piece = text[start:end]
        if piece.strip():
            chunks.append(Chunk(doc.id, start, end, piece))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def index_case(case: Case) -> int:
    """(Re)index all documents of a case. Returns the number of chunks stored."""
    chunks = [c for d in case.documents for c in chunk_document(d)]
    if not chunks:
        return 0
    vectors = embed([c.text for c in chunks])
    with iris_db.cursor() as cur:
        cur.execute("DELETE FROM Nor.Chunk WHERE CaseId = ?", [case.id])
        cur.executemany(
            "INSERT INTO Nor.Chunk (CaseId, DocId, StartPos, EndPos, Text, Embedding)"
            " VALUES (?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE))",
            [[case.id, c.doc_id, c.start, c.end, c.text, iris_db.to_vector(v)] for c, v in zip(chunks, vectors)],
        )
    return len(chunks)


def search(case_id: str, query: str, top_k: int = 5) -> list[Hit]:
    """Most similar chunks of one case (cosine similarity, higher = closer)."""
    qv = iris_db.to_vector(embed([query])[0])
    with iris_db.cursor() as cur:
        cur.execute(
            f"SELECT TOP {int(top_k)} DocId, StartPos, EndPos, Text,"
            " VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score"
            " FROM Nor.Chunk WHERE CaseId = ? ORDER BY Score DESC",
            [qv, case_id],
        )
        return [Hit(r[0], r[1], r[2], r[3], float(r[4])) for r in cur.fetchall()]
