# AI NOR — pravidla pro AI agenty (Claude Code, Copilot, Cursor)

## Cíl
Z české onkologické dokumentace (ambulantní/propouštěcí zprávy, histologie, MDT, operační protokoly) vytěžit
pole hlášení do **Národního onkologického registru (NOR)** s **citací zdroje**. Pole s jistotou ≥ 85 (0–100) bez rozporu se přijmou automaticky; lékař kontroluje jen rozpory mezi dokumenty a nejistá pole.
Hlášení se ukládají do **InterSystems IRIS for Health** (výzva AI NOR + výzva InterSystems): pracovní stav v SQL tabulce
`Nor.CaseRecord`, klinický záznam jako **FHIR R4** (po vytěžení rozpracovaný, po potvrzení lékařem konečný). Zprávy z NIS
přicházejí jako HL7v2 a na FHIR je převádí produkce v IRIS (`infra/iris/src`).

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
- Do FHIR jdou jen pole `auto_accepted`, `confirmed` nebo `edited`; rozpory a pole pod prahem nikdy bez člověka. Rozhodnutí o kontrole dělá **výhradně** `backend/app/confidence.py`.
- Každý případ má ve FHIR **jeden záznam** se stálými id (`backend/app/fhir/sync.py`), který se po každé změně přepíše (PUT): po vytěžení jako rozpracovaný (Composition `preliminary`, Condition `provisional`), konečný (`final`, `confirmed`) až po potvrzení celého hlášení člověkem.
- Případy se čtou a ukládají **výhradně** přes `backend/app/store` (IRIS `Nor.CaseRecord`); testy jedou proti paměti a falešnému FHIR (`backend/tests/conftest.py`), nikdy proti běžícímu IRIS.
- **Žádná pacientská data v gitu, testech ani promptech nástrojů.** Data FNO leží mimo repo (`../../Rakathon_DATA_NOR`, `../../Rakathon_DATA` vedle repa rakathon-2026); v repu jen `data/synthetic/`.
- Před commitem: `pytest -q` (backend) a `npm run build` (frontend) musí projít.
- Malé commity, zpráva česky v rozkazovacím způsobu.
