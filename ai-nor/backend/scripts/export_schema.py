"""Regenerate contracts/nor_record.schema.json from app.models (run after changing the models).

Usage (from backend/): .venv/Scripts/python -m scripts.export_schema
"""

import json
from pathlib import Path

from app.models import Case

out = Path(__file__).resolve().parents[2] / "contracts" / "nor_record.schema.json"
out.write_text(json.dumps(Case.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {out}")
