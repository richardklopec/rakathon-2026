"""Split the organisers' fully synthetic NIS exports (Rakathon_2026_*_10_pacientu.xlsx) into per-patient TXT files
in data/synthetic/<PatientId>/ so they can be uploaded in the UI.

Usage (from backend/): .venv/Scripts/python -m scripts.export_synthetic <folder with the xlsx files>
"""

import re
import sys
from pathlib import Path

from app import ingest

src = Path(sys.argv[1])
out = Path(__file__).resolve().parents[2] / "data" / "synthetic"
for xlsx in sorted(src.glob("Rakathon_2026_*_10_pacientu.xlsx")):
    kind = xlsx.stem.replace("Rakathon_2026_", "").replace("_10_pacientu", "")
    for doc in ingest.to_documents(xlsx.name, xlsx.read_bytes()):
        if m := re.search(r"PatientId: (PAC\d+)", doc.text) or re.search(r"PATIENTID: (PAC\d+)", doc.text):
            target = out / m.group(1) / f"{kind}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(doc.text + "\n", encoding="utf-8")
print("written to", out)
