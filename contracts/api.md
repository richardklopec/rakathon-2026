# API kontrakt (backend FastAPI, `http://localhost:8000`)

Typy = `nor_record.schema.json` (generuje `backend/scripts/export_schema.py` z `backend/app/models.py`).

| Metoda | Cesta | Vstup | Výstup | Pozn. |
|---|---|---|---|---|
| GET | `/api/health` | — | `{ok, llm_mode, fhir}` | `fhir` = IRIS FHIR `/metadata` odpovídá |
| GET | `/api/cases` | — | `Case[]` | |
| POST | `/api/cases` | multipart `files[]` (PDF/TXT/MD/XLSX), query `patient_ref?` | `Case` | ingest → `Document.text` (offsety citací se vztahují k tomuto textu) |
| GET | `/api/cases/{id}` | — | `Case` | |
| POST | `/api/cases/{id}/extract` | — | `Case` s vyplněným `report` | `LLM_MODE=mock` → regexy, `live` → LLM |
| PUT | `/api/cases/{id}/report` | `NorReport` | `Case` | lékař opravuje / potvrzuje (`field.review.state`) |
| GET | `/api/cases/{id}/fhir-bundle` | — | FHIR `Bundle` (transaction) | náhled; jen potvrzená/editovaná pole |
| POST | `/api/cases/{id}/submit` | — | FHIR `transaction-response` | zápis do IRIS FHIR |

TODO během hackathonu: `GET /api/cases/{id}/nor-export.csv` (přes FHIR SQL Builder nebo přímé mapování), audit log.
