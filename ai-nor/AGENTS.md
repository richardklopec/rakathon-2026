# AI NOR — pravidla pro AI agenty (Claude Code, Copilot, Cursor)

## Cíl
Z české onkologické dokumentace (ambulantní/propouštěcí zprávy, histologie, MDT, operační protokoly) vytěžit
pole hlášení do **Národního onkologického registru (NOR)** s **citací zdroje**. Lékař každé pole potvrdí/opraví.
Potvrzené hlášení se uloží jako **FHIR R4** do **InterSystems IRIS for Health** (výzva AI NOR + výzva InterSystems).

## Zdroj pravdy
- `contracts/` — datový kontrakt (`nor_record.schema.json` generovaný z `backend/app/models.py`), API (`api.md`), FHIR mapování (`fhir_mapping.md`).
- Kontrakt neměň bez výslovného pokynu. Když nesedí, napiš to.

## Stack
- Backend: Python 3.12, FastAPI, pydantic v2, pytest. Spouštění z `backend/` (`.venv`).
- Frontend: React 19 + TypeScript + Vite + Tailwind v4. Žádné další UI knihovny bez důvodu.
- IRIS for Health (Docker, `infra/iris`): FHIR server `http://localhost:52773/fhir/r4` (SuperUser/SYS, jen dev), SQL `localhost:1972` namespace `FHIRSERVER`.

## Pravidla
- LLM se volá **výhradně** přes `backend/app/llm.py` (EU deployment `-dz-eu`, hlavička `api-key`, backoff na 429). Žádné klíče v kódu ani ve frontendu.
- FHIR se volá **výhradně** přes `backend/app/fhir/client.py`; Bundle staví `backend/app/fhir/mapping.py`.
- Každé vytěžené pole MUSÍ mít `evidence` (citace + offsety v dokumentu), nebo mít stav `missing`. Chybějící ≠ negativní.
- Nic se neodesílá do FHIR bez potvrzení lékařem.
- **Žádná pacientská data v gitu, testech ani promptech nástrojů.** Data FNO leží mimo repo (`../Rakathon_DATA_NOR`, `../Rakathon_DATA`); v repu jen `data/synthetic/`.
- Před commitem: `pytest -q` (backend) a `npm run build` (frontend) musí projít.
- Malé commity, zpráva česky v rozkazovacím způsobu.
