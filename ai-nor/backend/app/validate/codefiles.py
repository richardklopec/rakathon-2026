"""Locate and read the ÚZIS MKN-10 package files (01_MKN10_5E…, 05_…nemoci a poranění, 07_…novotvary).

Files are looked up by their number prefix, first in CODELISTS_DIR (default `ai-nor/uploads`, any subfolder),
then next to MKN10_CSV. ÚZIS ships every file in UTF-8 and in Windows-1250; both are accepted.
"""

import csv
import io
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

MKN10 = "01_MKN10_5E"
INDEX_DISEASES = "05_MKN10"
INDEX_NEOPLASMS = "07_MKN10"
MORPHOLOGY_HEMATO = "morfologie_hematologie"  # scripts/extract_pdf_morphology.py (WHO haematological tumours)


def _dirs() -> list[Path]:
    s = get_settings()
    dirs = [Path(s.codelists_dir)] if s.codelists_dir else []
    if s.mkn10_csv:
        dirs.append(Path(s.mkn10_csv).parent)
    return [d for d in dirs if d.is_dir()]


@lru_cache
def find(prefix: str) -> Path | None:
    """First CSV whose name starts with prefix; UTF-8 copies win over Windows-1250 ones."""
    for d in _dirs():
        hits = sorted(d.rglob(f"{prefix}*.csv"), key=lambda p: ("utf8" not in p.name.lower(), str(p)))
        if hits:
            return hits[0]
    return None


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1250")


@lru_cache
def rows(prefix: str) -> list[list[str]]:
    """Rows of the file (header included); empty when the file is not available."""
    path = find(prefix)
    if path is None:
        return []
    return list(csv.reader(io.StringIO(read_text(path)), delimiter=";"))


def dict_rows(prefix: str) -> list[dict[str, str]]:
    data = rows(prefix)
    if not data:
        return []
    header = data[0]
    return [dict(zip(header, r)) for r in data[1:]]
