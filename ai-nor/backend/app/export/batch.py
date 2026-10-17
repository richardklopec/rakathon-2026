"""Bulk export of confirmed reports (Seznam hlášení): CSV (1 row = 1 report, opens in Excel) or JSON.

Fields and codes are those of the ÚZIS form (export/uzis.build); the exact ÚZIS import format is not known yet,
so this is the batch counterpart of the single-report JSON export.
"""

import csv
import io
import json
from datetime import datetime, timezone

from app.export import uzis
from app.models import Case

FORMATS = {"csv": "text/csv; charset=utf-8", "json": "application/json"}
_SECTIONS = ["diagnosticka_cast", "diagnoza", "morfologie", "tnm", "ostatni", "hlaseni"]


def _flat(case: Case) -> dict:
    form = uzis.build(case)
    row = {"id_pripadu": case.id, "pacient": form["pacient"], "stav": form["stav"]}
    for section in _SECTIONS:
        for key, value in form[section].items():
            row[f"{section}.{key}"] = "" if value is None else value
    return row


def to_csv(cases: list[Case]) -> bytes:
    rows = [_flat(c) for c in cases]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter=";")  # ';' = Excel with Czech locale
    writer.writeheader()
    writer.writerows(rows)
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM: Excel reads the diacritics right


def to_json(cases: list[Case]) -> bytes:
    payload = {
        "formular": "NOR - Incidence zhoubného novotvaru",
        "exportovano": datetime.now(timezone.utc).isoformat(),
        "pocet": len(cases),
        "hlaseni": [uzis.build(c) | {"id_pripadu": c.id} for c in cases],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1).encode("utf-8")


def build(cases: list[Case], fmt: str) -> bytes:
    return to_csv(cases) if fmt == "csv" else to_json(cases)
