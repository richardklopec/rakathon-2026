# API kontrakt (backend FastAPI, `http://localhost:8001`)

Typy = `nor_record.schema.json` (generuje `backend/scripts/export_schema.py` z `backend/app/models.py`).
Pole hlášení: `Extracted` s `value`, `confidence` 0–100, `confidence_reasons`, `needs_review`, `evidence` (citace + offsety), `alternatives`, `rules` (citace pravidel MKN-10: `code`, `page`, `quote`, `verified`; zatím jen u `icd10`), `review.state`.

| Metoda | Cesta | Vstup | Výstup | Pozn. |
|---|---|---|---|---|
| GET | `/api/health` | — | `{ok, llm_mode, fhir}` | `fhir` = IRIS FHIR `/metadata` odpovídá |
| GET | `/api/cases` | — | `Case[]` | z IRIS (`Nor.CaseRecord`, `backend/app/store`); 503, když IRIS neodpovídá |
| POST | `/api/cases` | multipart `files[]` (PDF/TXT/MD/XLSX), query `patient_ref?` | `Case` | ingest → `Document.text` (offsety citací se vztahují k tomuto textu) |
| GET | `/api/cases/{id}` | — | `Case` | |
| POST | `/api/cases/{id}/extract` | — | `Case` | `LLM_MODE=live`: jeden LLM dotaz → ověřené citace → kódy NOR → rozpory → jistota. Pole ≥ `AUTO_ACCEPT_THRESHOLD` (80) bez rozporu = předvyplněná (`auto_accepted`), ostatní `needs_review`. Ruší potvrzení. Hned zapíše FHIR záznam případu jako rozpracovaný (viz níže). |
| GET | `/api/cases/{id}/review-queue` | — | `[{path, field}]` | rozpory, pole pod prahem a chybějící povinná pole NOR (lékař je doplní, nebo potvrdí `review.state = confirmed`, že v dokumentaci nejsou); nejdřív rozpory, pak nejnižší jistota |
| PUT | `/api/cases/{id}/report` | `NorReport` | `Case` | lékař řeší frontu (`review.state` = confirmed / edited / rejected). Ruší potvrzení. FHIR záznam se přepíše (vyřešená pole do něj přibudou, zamítnutá zmizí). |
| GET | `/api/cases/{id}/uzis-preview` | — | hlášení ve struktuře formuláře ÚZIS + `stav` Úplné / Neúplné + `chybi_povinne` + `pacient_rc` (kontrola RČ: `je_rc`, `platne`, `chyby`, `datum_narozeni`, `pohlavi`) | náhled, který lékař potvrzuje a v němž může pole upravit (ukládá se přes `PUT /report`) |
| PUT | `/api/cases/{id}/patient` | `{patient_ref}` | `Case` | „Pacient RČ“ z náhledu. Hodnota ve tvaru RČ musí projít kontrolou (`app/validate/rodne_cislo.py`), jinak 422; ukládá se jako `RRMMDD/XXXX`. Ruší potvrzení. |
| PUT | `/api/cases/{id}/form` | `FormFields` | `Case` | pole formuláře NOR, která ve zprávách nejsou (zařízení, oddělení, neznámo / cizinec, země původu, identifikace specifických dg., TNM skupina, riziková kategorie, sérové markery, p16, pracoviště hlásící novotvar); `null` = výchozí hodnota. Zapíše do historie změn, ruší potvrzení. |
| GET | `/api/codelists` | — | `{pole: [{value, label, search?}]}` | volby rozbalovacích seznamů formuláře NOR; `value` = hodnota v `NorReport`, `label` = text ve formuláři, `search` = názvy orgánů z abecedního seznamu novotvarů (07) pro hledání. Zdroj: balíček MKN-10 ÚZIS v `CODELISTS_DIR` (výchozí `ai-nor/uploads`, UTF-8 i Windows-1250), záloha složka `MKN10_CSV` |

`Case.ai_confidence` (počítané, jen ve výstupu): celková jistota AI `{score 0–100, level, fields_ai, auto_accepted, to_review, conflicts, edited_by_human, missing_required}` – vážený průměr jistoty polí, která vyplnila AI (povinná pole NOR váha 2); pole opravená lékařem se nepočítají, chybějící pole jsou úplnost, ne jistota (`app/confidence.py: overall`).
| POST | `/api/cases/{id}/confirm` | `{by}` | `Case` | **potvrzení celého hlášení**; 409, dokud není fronta prázdná. Stejný FHIR záznam se změní na konečný (`final`). |
| GET | `/api/cases/{id}/uzis-export` | — | JSON hlášení pro ÚZIS | 409 bez potvrzení |
| GET | `/api/cases/{id}/fhir-bundle` | — | FHIR `Bundle` (transaction) | náhled toho, co by zapsal příští zápis |
| POST | `/api/cases/{id}/fhir-sync` | — | `Case` | znovu zapíše FHIR záznam případu i se zdrojovými zprávami (po výpadku IRIS); jinak se zapisuje sám po každé změně; 409 před vytěžením |
| GET | `/api/cases/{id}/audit` | — | `{iris, entries[]}` | historie změn (kdo, kdy, pole, `old` → `new`, `kind`, `storage` iris/local), nejstarší první; IRIS tabulka `Nor.Audit`, při výpadku IRIS lokální záloha `backend/var/audit/` přesunutá do IRIS po připojení (`app/audit.py`) |
| POST | `/api/export` | `{case_ids[], format: csv|json}` | soubor (příloha) | hromadný export jen potvrzených hlášení (jinak 409), zapíše `exported` do historie změn |
| GET | `/api/exports` | — | `{case_id: {at, actor, detail}}` | poslední export každého hlášení (z historie změn) |
| GET | `/api/nis/inbox` | — | `{iris, patients: [{patient, documents[]}]}` | nové zprávy z NIS v IRIS FHIR (DocumentReference s tagem `urn:ai-nor:inbox|nis`), dosud nenačtené |
| POST | `/api/nis/import` | `{patient, ids[]}` | `Case` | založí případ ze zpráv NIS (pak `/extract`), zapíše `nis_imported` |
| POST | `/api/cases/{id}/index` | — | `{chunks}` | dokumenty → lokální embeddingy → IRIS `Nor.Chunk` |
| GET | `/api/cases/{id}/search?q=&k=` | — | úseky s offsety a skóre | IRIS Vector Search nad dokumenty případu |
| GET | `/api/codes/search?q=&system=&k=` | — | kandidáti kódů | `system` = `mkn10` / `icdo3-morph`; přesná shoda názvu, jinak hybrid vektor + slova (IRIS `Nor.Code`) |

**Záznam ve FHIR** (`backend/app/fhir/sync.py`): každý případ má v IRIS FHIR jeden záznam se stálými id odvozenými z id
případu, zapsaný jednou transakcí (PUT) po vytěžení a přepsaný po každé změně (`/report`, `/patient`, `/confirm`).
Do potvrzení je rozpracovaný (Composition `preliminary`, Condition `provisional`, Observation `preliminary`) a obsahuje
jen pole `auto_accepted` / `confirmed` / `edited`; potvrzení ho změní na konečný (`final`). Zdroje, které z případu
vypadly, se ve stejné transakci smažou. Výsledek je v `Case.fhir` `{status: preliminary|final, composition, version,
resources[], synced_at, error}`; když zápis selže (IRIS neběží), případ se uloží a `error` říká proč, zaostalé záznamy
dopíše `/fhir-sync` nebo start backendu. Detail mapování: `fhir_mapping.md`.

`Case.document_rc` (počítané, jen ve výstupu): rodné číslo ze zpráv (to, které uvádí nejvíc dokumentů, i neplatné); UI podle něj pojmenuje pacienta, pokud lékař v náhledu nezadal jiné.

`Case.nis_ids`: zprávy z NIS (id DocumentReference), ze kterých případ vznikl; schránka NIS podle nich skrývá načtené.

TODO: `POST /api/cases/{id}/events` (čas a opravy z UI), CSV dávka přes FHIR SQL Builder, `GET /api/eval`.

Změnové požadavky (`POST /api/cases`, `/extract`, `PUT /report`, `PUT /patient`, `/confirm`, `/fhir-sync`) mohou nést hlavičku `X-Actor` se jménem uživatele (URL-encoded kvůli diakritice); zapíše se do historie změn.
