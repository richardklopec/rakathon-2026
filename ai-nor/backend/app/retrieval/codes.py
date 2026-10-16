"""Code lists (číselníky) in IRIS Vector Search (table Nor.Code) for step 3 of code selection (PLAN.md §3.1).

Sources: ÚZIS MKN-10-CZ 2026 package (folder of MKN10_CSV):
- 01_MKN10_5E_2026_utf8.csv: MKN-10 codes C00-C97, D00-D48 with full names
- 05_MKN10_2026_Abecední seznam - nemoci a poranění_utf8.csv: index terms with ICD-O morphology codes "(M8140/3)"
"""

import re
from dataclasses import dataclass

from app import iris_db
from app.retrieval.embeddings import embed
from app.validate import codefiles

MKN10 = "mkn10"
MORPHOLOGY = "icdo3-morph"

_MORPH = re.compile(r"\(M(\d{4})/(\d)\)")
_ONCO_ICD10 = re.compile(r"^(C\d|D0\d|D3[7-9]|D4[0-8])")


@dataclass
class CodeHit:
    system: str
    code: str
    name: str
    score: float
    exact: bool = False  # the term equals a code-list name (step 2), not just semantically close (step 3)


def _require(prefix: str) -> None:
    if codefiles.find(prefix) is None:
        raise RuntimeError(f"{prefix}*.csv not found in CODELISTS_DIR (ai-nor/uploads) nor next to MKN10_CSV")


def load_mkn10() -> list[tuple[str, str]]:
    _require(codefiles.MKN10)
    return [
        (row["KodSTeckou"], row["NazevPlny"] or row["Nazev"])
        for row in codefiles.dict_rows(codefiles.MKN10)
        if _ONCO_ICD10.match(row["KodSTeckou"])
    ]


def _clean(term: str) -> str:
    term = _MORPH.sub("", term)
    term = re.split(r"\s+–\s+viz\b|\(viz\b", term)[0]
    return term.strip(" –-*;").strip()


def load_morphology() -> list[tuple[str, str]]:
    """Morphology terms from the hierarchical index: child names are prefixed by their parents."""
    _require(codefiles.INDEX_DISEASES)
    stack: list[str] = []
    out: dict[tuple[str, str], None] = {}
    for row in codefiles.rows(codefiles.INDEX_DISEASES):
        if not row or not row[0].isdigit():
            continue
        level, name = int(row[0]), row[1]
        stack = stack[: level - 1] + [_clean(name)]
        if m := _MORPH.search(name):
            full = " ".join(p for p in stack if p)
            out[(f"{m.group(1)}/{m.group(2)}", full)] = None
    return list(out)


def index_codes() -> dict[str, int]:
    """Rebuild Nor.Code from the ÚZIS files. Returns row counts per system."""
    rows = [(MKN10, c, n) for c, n in load_mkn10()] + [(MORPHOLOGY, c, n) for c, n in load_morphology()]
    vectors = embed([name for _, _, name in rows])  # names only: the code prefix only adds noise
    with iris_db.cursor() as cur:
        cur.execute("DELETE FROM Nor.Code")
        cur.executemany(
            "INSERT INTO Nor.Code (System, Code, Name, Embedding) VALUES (?, ?, ?, TO_VECTOR(?, DOUBLE))",
            [[s, c, n[:500], iris_db.to_vector(v)] for (s, c, n), v in zip(rows, vectors)],
        )
    counts: dict[str, int] = {}
    for s, _, _ in rows:
        counts[s] = counts.get(s, 0) + 1
    return counts


# Clinical abbreviations / variants not present in the ÚZIS index (extend as needed)
SYNONYMS = {
    "nst": "duktální",
    "invazivní": "infiltrující",  # ICD-O Czech names use "infiltrující"
    "světlobuněčný": "klarocelulární",  # clear cell (8310/3)
    "světlobuněčná": "klarocelulární",
    "spinoca": "spinocelulární karcinom",
    "spinocelulární": "spinocelulární",
    "dlaždicobuněčný": "spinocelulární",
    "adenoca": "adenokarcinom",
    "ca": "karcinom",
    "hgsc": "serózní high grade karcinom",
    "acinární": "acinózní",
    "bcc": "bazocelulární karcinom",
    "dcis": "duktální karcinom in situ",
    "lcis": "lobulární karcinom in situ",
}
_STOP = {"zhoubný", "novotvar", "levého", "pravého", "vlevo", "vpravo", "typu"}
# organ words describe the site (topography), not the morphology -> dropped from morphology queries
_ORGANS = re.compile(
    r"\b(prs[uůy]?|mamm\w*|plic\w*|žalud\w*|prostat\w*|ledvin\w*|hrtan\w*|ovari\w*|vaječník\w*|děloh\w*|"
    r"endometri(?:um|a|u)\b|renáln\w*|tračník\w*|střev\w*|sigm\w*|rekt\w*|pankreat\w*|slinivk\w*|jater|játr\w*|kůž\w*|močov\w*|měchýř\w*)\b",
    re.IGNORECASE,
)
LEXICAL_WEIGHT = 0.35


def expand_query(query: str) -> str:
    words = re.findall(r"[\wáčďéěíňóřšťúůýž]+", query.lower())
    return " ".join(SYNONYMS.get(w, w) for w in words)


def _stems(query: str) -> list[str]:
    words = {w for w in re.findall(r"[\wáčďéěíňóřšťúůýž]+", query.lower()) if len(w) >= 4 and w not in _STOP}
    return sorted({w[:4] for w in words})


def search_codes(system: str, query: str, top_k: int = 5) -> list[CodeHit]:
    """Hybrid search in IRIS: vector similarity + word-stem overlap, one hit per code.

    Vector-only search misses clinical shorthand (NST, antrum); the lexical part catches it.
    """
    q = expand_query(query)
    if system == MORPHOLOGY:
        q = " ".join(_ORGANS.sub(" ", q).split()) or q
    stems = _stems(q)
    qv = iris_db.to_vector(embed([q])[0])
    with iris_db.cursor() as cur:  # step 2: exact name (IRIS default collation is case-insensitive)
        cur.execute("SELECT TOP 5 Code, Name FROM Nor.Code WHERE System = ? AND Name = ?", [system, q])
        exact = [CodeHit(system, code, name, 1.0, exact=True) for code, name in cur.fetchall()]
    if exact:
        return exact[:top_k]
    sql_vec = (
        "SELECT TOP 40 Code, Name, VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score"
        " FROM Nor.Code WHERE System = ? ORDER BY Score DESC"
    )
    rows = []
    with iris_db.cursor() as cur:
        cur.execute(sql_vec, [qv, system])
        rows += cur.fetchall()
        if stems:
            like = " OR ".join(["Name LIKE ?"] * len(stems))
            cur.execute(
                "SELECT TOP 200 Code, Name, VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score"
                f" FROM Nor.Code WHERE System = ? AND ({like})",
                [qv, system, *[f"%{st}%" for st in stems]],
            )
            rows += cur.fetchall()

    best: dict[str, CodeHit] = {}
    for code, name, cos in rows:
        low = name.lower()
        lex = sum(st in low for st in stems) / len(stems) if stems else 0.0
        score = (1 - LEXICAL_WEIGHT) * float(cos) + LEXICAL_WEIGHT * lex
        if code not in best or score > best[code].score:
            best[code] = CodeHit(system, code, name, round(score, 3))
    return sorted(best.values(), key=lambda h: -h.score)[:top_k]
