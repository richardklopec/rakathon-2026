"""Extract the WHO classification of haematopoietic and lymphoid tumours with ICD-O codes from the MKN-10 tabular
part PDF (appendix "KLASIFIKACE SZO HEMATOPOETICKÝCH A LYMFOIDNÍCH NÁDORŮ S KÓDY MKN-O", pages 867-870 of
mkn-tabelarni-cast_1-4-2014_2.pdf) into a CSV next to the ÚZIS code lists.

The alphabetical index (05_…) carries almost no lymphoma / leukaemia morphology codes (96xx-99xx), this fills them.
The PDF is not in git; the CSV it produces is (uploads/morfologie_hematologie_szo_pdf2014_utf8.csv).

Usage (from backend/): .venv/Scripts/python -m scripts.extract_pdf_morphology [path/to/pdf]
"""

import csv
import re
import sys
from pathlib import Path

import pymupdf

from app.config import REPO_ROOT

PDF = REPO_ROOT / "uploads" / "mkn-tabelarni-cast_1-4-2014_2.pdf"
OUT = REPO_ROOT / "uploads" / "morfologie_hematologie_szo_pdf2014_utf8.csv"
PAGES = range(866, 870)  # 0-based: printed pages 867-870
CODE = re.compile(r"^(9\d{3})/([0-9])$")


def _lines(page) -> list[tuple[float, float, bool, str]]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text:
                bold = "Bold" in line["spans"][0]["font"]
                out.append((line["bbox"][1], line["bbox"][0], bold, text))
    return sorted(out)


def _continues(text: str) -> bool:
    return text[0].islower() or text[0] in "{("


def extract(pdf: Path) -> tuple[list[dict], list[str]]:
    """Rows (Kod, Nazev, Skupina, Strana) and the left-column lines that carry no code of their own.

    The code is printed at the vertical middle of its name, which may wrap over 1-3 lines (continuation lines
    start lowercase or with a bracket). Bold lines are group headings, unless a code is printed next to them.
    Lowercase lines left over are variants sharing the code above (e.g. 's předchozím myelodysplastickým syndromem').
    """
    doc = pymupdf.open(pdf)
    rows: list[dict] = []
    skipped: list[str] = []
    group = ""
    for index in PAGES:
        lines = [l for l in _lines(doc[index]) if "PŘÍLOHA" not in l[3]]
        if index == PAGES[0]:  # the appendix starts mid-page, after the title and the source note
            title = next(i for i, l in enumerate(lines) if "KLASIFIKACE SZO" in l[3])
            first_heading = next(i for i, l in enumerate(lines) if i > title + 1 and l[2])
            lines = lines[first_heading:]
        names = [(y, bold, text) for y, x, bold, text in lines if x < 200]
        codes = [(y, f"{m.group(1)}/{m.group(2)}") for y, x, _, text in lines if x > 200 and (m := CODE.match(text))]

        used: dict[int, str] = {}  # line index -> code
        spans: list[tuple[int, int, str]] = []
        for yc, code in codes:
            for k in (3, 2, 1):  # prefer the longest name centred on the code
                hit = next(
                    (
                        s
                        for s in range(len(names) - k + 1)
                        if abs((names[s][0] + names[s + k - 1][0]) / 2 - yc) <= 2.5
                        and not any(i in used for i in range(s, s + k))
                        and not _continues(names[s][2])
                        and all(not names[i][1] and _continues(names[i][2]) for i in range(s + 1, s + k))
                    ),
                    None,
                )
                if hit is not None:
                    spans.append((hit, hit + k, code))
                    used.update({i: code for i in range(hit, hit + k)})
                    break
            else:
                raise ValueError(f"page {index + 1}: no name for code {code} at y={yc:.1f}")

        starts = {s: (e, code) for s, e, code in spans}
        for i, (y, bold, text) in enumerate(names):
            if i in starts:
                end, code = starts[i]
                name = " ".join(names[j][2] for j in range(i, end))
                rows.append({"Kod": code, "Nazev": name, "Skupina": group, "Strana": index + 1})
            elif i in used:
                continue
            elif bold:
                group = text
            else:
                skipped.append(f"str. {index + 1}: {text}")
    return rows, skipped


if __name__ == "__main__":
    rows, skipped = extract(Path(sys.argv[1]) if len(sys.argv) > 1 else PDF)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["Kod", "Nazev", "Skupina", "Strana"], delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows ({len({r['Kod'] for r in rows})} codes) to {OUT}")
    for line in skipped:
        print("  variant without its own code:", line)
