# API kontrakt (backend FastAPI, `http://localhost:8001`)

Typy = `nor_record.schema.json` (generuje `backend/scripts/export_schema.py` z `backend/app/models.py`).
Pole hlášení: `Extracted` s `value`, `confidence` 0–100, `confidence_reasons`, `needs_review`, `evidence` (citace + offsety), `alternatives`, `rules` (citace pravidel MKN-10: `code`, `page`, `quote`, `verified`; zatím jen u `icd10`), `review.state`.

| Metoda | Cesta | Vstup | Výstup | Pozn. |
|---|---|---|---|---|
| GET | `/api/health` | — | `{ok, llm_mode, fhir}` | `fhir` = IRIS FHIR `/metadata` odpovídá |
| GET | `/api/cases` | — | `Case[]` | |
| POST | `/api/cases` | multipart `files[]` (PDF/TXT/MD/XLSX), query `patient_ref?` | `Case` | ingest → `Document.text` (offsety citací se vztahují k tomuto textu) |
| GET | `/api/cases/{id}` | — | `Case` | |
| POST | `/api/cases/{id}/extract` | — | `Case` | `LLM_MODE=live`: jeden LLM dotaz → ověřené citace → kódy NOR → rozpory → jistota. Pole ≥ `AUTO_ACCEPT_THRESHOLD` (85) bez rozporu = předvyplněná (`auto_accepted`), ostatní `needs_review`. Ruší potvrzení. |
| GET | `/api/cases/{id}/review-queue` | — | `[{path, field}]` | rozpory, pole pod prahem a chybějící povinná pole NOR (lékař je doplní, nebo potvrdí `review.state = confirmed`, že v dokumentaci nejsou); nejdřív rozpory, pak nejnižší jistota |
| PUT | `/api/cases/{id}/report` | `NorReport` | `Case` | lékař řeší frontu (`review.state` = confirmed / edited / rejected). Ruší potvrzení. |
| GET | `/api/cases/{id}/uzis-preview` | — | hlášení ve struktuře formuláře ÚZIS + `stav` Úplné / Neúplné + `chybi_povinne` + `pacient_rc` (kontrola RČ: `je_rc`, `platne`, `chyby`, `datum_narozeni`, `pohlavi`) | náhled, který lékař potvrzuje a v němž může pole upravit (ukládá se přes `PUT /report`) |
| PUT | `/api/cases/{id}/patient` | `{patient_ref}` | `Case` | „Pacient RČ“ z náhledu. Hodnota ve tvaru RČ musí projít kontrolou (`app/validate/rodne_cislo.py`), jinak 422; ukládá se jako `RRMMDD/XXXX`. Ruší potvrzení. |
| GET | `/api/codelists` | — | `{pole: [{value, label, search?}]}` | volby rozbalovacích seznamů formuláře NOR; `value` = hodnota v `NorReport`, `label` = text ve formuláři, `search` = názvy orgánů z abecedního seznamu novotvarů (07) pro hledání. Zdroj: balíček MKN-10 ÚZIS v `CODELISTS_DIR` (výchozí `ai-nor/uploads`, UTF-8 i Windows-1250), záloha složka `MKN10_CSV` |

`Case.ai_confidence` (počítané, jen ve výstupu): celková jistota AI `{score 0–100, level, fields_ai, auto_accepted, to_review, conflicts, edited_by_human, missing_required}` – vážený průměr jistoty polí, která vyplnila AI (povinná pole NOR váha 2); pole opravená lékařem se nepočítají, chybějící pole jsou úplnost, ne jistota (`app/confidence.py: overall`).
| POST | `/api/cases/{id}/confirm` | `{by}` | `Case` | **potvrzení celého hlášení**; 409, dokud není fronta prázdná |
| GET | `/api/cases/{id}/uzis-export` | — | JSON hlášení pro ÚZIS | 409 bez potvrzení |
| GET | `/api/cases/{id}/fhir-bundle` | — | FHIR `Bundle` (transaction) | náhled |
| POST | `/api/cases/{id}/submit` | — | FHIR `transaction-response` | zápis do IRIS FHIR; 409 bez potvrzení |
| GET | `/api/cases/{id}/audit` | — | `{iris, entries[]}` | historie změn (kdo, kdy, pole, `old` → `new`, `kind`, `storage` iris/local), nejstarší první; IRIS tabulka `Nor.Audit`, při výpadku IRIS lokální záloha `backend/var/audit/` přesunutá do IRIS po připojení (`app/audit.py`) |
| POST | `/api/export` | `{case_ids[], format: csv|json}` | soubor (příloha) | hromadný export jen potvrzených hlášení (jinak 409), zapíše `exported` do historie změn |
| GET | `/api/exports` | — | `{case_id: {at, actor, detail}}` | poslední export každého hlášení (z historie změn) |
| GET | `/api/nis/inbox` | — | `{iris, patients: [{patient, documents[]}]}` | nové zprávy z NIS v IRIS FHIR (DocumentReference s tagem `urn:ai-nor:inbox|nis`), dosud nenačtené |
| POST | `/api/nis/import` | `{patient, ids[]}` | `Case` | založí případ ze zpráv NIS (pak `/extract`), zapíše `nis_imported` |
| POST | `/api/cases/{id}/index` | — | `{chunks}` | dokumenty → lokální embeddingy → IRIS `Nor.Chunk` |
| GET | `/api/cases/{id}/search?q=&k=` | — | úseky s offsety a skóre | IRIS Vector Search nad dokumenty případu |
| GET | `/api/codes/search?q=&system=&k=` | — | kandidáti kódů | `system` = `mkn10` / `icdo3-morph`; přesná shoda názvu, jinak hybrid vektor + slova (IRIS `Nor.Code`) |

TODO: `POST /api/cases/{id}/events` (čas a opravy z UI), CSV dávka přes FHIR SQL Builder, `GET /api/eval`.

Změnové požadavky (`POST /api/cases`, `/extract`, `PUT /report`, `PUT /patient`, `/confirm`, `/submit`) mohou nést hlavičku `X-Actor` se jménem uživatele (URL-encoded kvůli diakritice); zapíše se do historie změn.
