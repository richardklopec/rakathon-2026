# AI NOR — strukturované onkologické hlášení z volného textu

Rakathon 2026 Ostrava · výzva **AI NOR (FN Ostrava)** + výzva **InterSystems (AI & interoperabilita)**. Plán, cíle a návrh UI: [PLAN.md](PLAN.md).

AI z klinické dokumentace (ambulantní a propouštěcí zprávy, histologie, MDT) vytěží pole hlášení do
Národního onkologického registru **s citací zdroje**. Lékař každé pole potvrdí nebo opraví. Hlášení žije v
**InterSystems IRIS for Health** (stejná platforma, kterou FNO používá pro integrace): hned po vytěžení je ve FHIR R4
jako rozpracované, potvrzení lékařem stejný záznam změní na konečný.

```
NIS → HL7v2 MDM (MLLP :2575) → produkce IRIS:     infra/iris/src (AINOR.Production)
      HL7v2 → SDA3 → FHIR DocumentReference          vestavěné převody IRIS for Health
dokumenty (PDF/TXT/XLSX, nebo zprávy z NIS)
  → ingest (text + offsety)                       backend/app/ingest
  → extrakce s citacemi (LLM -dz-eu / mock)       backend/app/extract, app/llm.py
      ↳ retrieval: IRIS Vector Search (Nor.Chunk)
  → validace (MKN-10, TNM, data)                  backend/app/validate
  → review UI: dokument ↔ pole ✓/✗                frontend/
  → případ v IRIS SQL (Nor.CaseRecord)            backend/app/store
  → FHIR záznam (Composition preliminary → final,
     Condition, Observation, Provenance) → IRIS   backend/app/fhir (sync.py, mapping.py)
  → export NOR (FHIR SQL Builder)                 TODO
```

## Spuštění (Windows)

Potřeba: Python 3.12, Node 20+, Docker Desktop (běžící).

```powershell
copy .env.example .env          # doplnit LLM_API_KEY; LLM_MODE=live (mock jede bez klíče). Data FNO (Rakathon_DATA_NOR) patří vedle složky rakathon-2026
cd backend; python -m venv .venv; .\.venv\Scripts\pip install -e ".[dev]"; cd ..
.\start-iris.ps1                # IRIS + FHIR server /fhir/r4 + tabulky Nor.Chunk, Nor.Code, Nor.Rule, Nor.CaseRecord, Nor.Audit + produkce HL7v2 → FHIR
cd backend; .\.venv\Scripts\python -m scripts.index_codes     # číselníky MKN-10 + morfologie do IRIS (~1,5 min)
.\.venv\Scripts\python -m scripts.index_rules     # pravidla MKN-10 z PDF Tabelární část do IRIS (Nor.Rule, ~4 min)
.\.venv\Scripts\python -m scripts.get_tessdata     # čeština pro OCR skenů (Tesseract je v PyMuPDF), do backend/var/tessdata
.\.venv\Scripts\uvicorn app.main:app --port 8001     # 8001: na 8000 běží starý projekt Rakathon2026
cd frontend; npm install; npm run dev     # http://localhost:5173
```

- Syntetičtí pacienti k nahrání: `data/synthetic/PAC001` … `PAC010` (vytvoří `python -m scripts.export_synthetic <složka s XLSX>`).
- Číselníky formuláře (MKN-10, topografie, morfologie): balíček MKN-10 od ÚZIS ve složce `uploads/` (CSV v UTF-8 i Windows-1250, `CODELISTS_DIR`), jinak složka `MKN10_CSV`.
- Pravidla MKN-10: PDF `uploads/mkn-tabelarni-cast_1-4-2014_2.pdf` (Tabelární část MKN-10 od ÚZIS, `MKN10_RULES_PDF`). Druhý krok LLM podle nich volí kód Dg. MKN a cituje pravidlo (PLAN.md §3.1 krok 6).
- Vstupy: PDF (skeny přes OCR), JPG/PNG/TIFF (OCR), DOCX, EML s přílohami, TXT, XLSX z NIS. Zprávy z NIS přes IRIS: demo odesílatel `python -m scripts.nis_demo_send` pošle fiktivní zprávy jako HL7v2 MDM^T02 přes MLLP na port 2575, produkce `AINOR.Production` je v IRIS převede na FHIR DocumentReference (`--fhir` je zapíše rovnou do FHIR).
- Hlášení se ukládají do IRIS (`Nor.CaseRecord`) a při startu backendu se odtud načtou; staré JSON soubory z `backend/var/cases` se při prvním startu přesunou do IRIS (složka zůstane jako `cases-presunuto-do-iris`). Případ, jehož FHIR záznam zaostal (IRIS neběželo), se při startu dopíše.
- Produkce HL7v2 → FHIR: Management Portal → Interoperability → Production (`AINOR.Production`), zprávy v Interoperability → Messages, převodní tabulka typů dokumentů `AINOR.DocumentType`. Po změně tříd v `infra/iris/src` stačí znovu `python -m scripts.setup_iris`.
- LLM: `gpt-6-luna-dz-eu` (EU Data Zone), `reasoning_effort=low`, odpovědi se cachují v `backend/var/llm-cache`.
- Embeddingy běží **lokálně** (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dim, model se stáhne do `backend/var/models`), text zpráv neopouští počítač.
- FHIR: `http://localhost:52773/fhir/r4/metadata` (SuperUser / SYS — jen dev) · Management Portal: `http://localhost:52773/csp/sys/UtilHome.csp`
- Testy: `cd backend; .\.venv\Scripts\pytest -q` · build: `cd frontend; npm run build`
- Evaluace proti gold hodnotám: `cd backend; .\.venv\Scripts\python -m scripts.evaluate [--runs 2 --fresh-cache]` (gold JSON v `EVAL_GOLD_DIR` mimo repo, výsledky v `backend/var/eval/`; formát a srovnání dvou běhů viz `scripts/evaluate.py`).

## Lokální model nemocnice místo cloudu

AI se volá jen z `backend/app/llm.py` přes API kompatibilní s OpenAI. Přepnutí na model na serverech nemocnice
(vLLM, Ollama, llama.cpp, TGI) je jen změna `.env`, zbytek aplikace (citace, číselníky, výpočet stádia, kontroly,
fronta ke kontrole, IRIS, FHIR) zůstává stejný. Embeddingy a IRIS už běží lokálně, model je jediná cloudová část.

```
LLM_BASE_URL=http://llm.nemocnice.local:8000/v1/   # adresa serveru modelu
LLM_MODEL=<název modelu podle /v1/models>
LLM_AUTH=bearer          # api-key | bearer | none
LLM_OUTPUT=schema        # json, když server neumí striktní JSON schéma (odpověď se pak ověří tady)
LLM_REASONING_EFFORT=    # prázdné: lokální servery parametr většinou neznají
LLM_TEMPERATURE=0
```

Před ostrým provozem: model musí mít kontext na celý případ (všechny zprávy pacienta v jednom dotazu, desítky tisíc
tokenů) a jeho přesnost je potřeba přeměřit na referenčních pacientech (`python -m scripts.evaluate --runs 2 --fresh-cache`),
protože prahy jistoty jsou laděné na Lunu. Odpovědi se cachují podle názvu modelu, odpovědi Luny se tedy nepoužijí.

## Struktura
| Složka | Obsah | Vlastník |
|---|---|---|
| `contracts/` | JSON schéma hlášení, API, FHIR mapování — **zdroj pravdy** | všichni po domluvě |
| `backend/app/extract`, `llm.py`, `validate` | extrakce, LLM, validace | Backend/AI |
| `backend/app/fhir`, `infra/`, `scripts/setup_iris.py` | FHIR + IRIS | FHIR/IRIS |
| `frontend/` | review UI | Frontend |
| `data/synthetic`, `eval/` | syntetická data, gold, evaluace | Klinik/eval |

Data FNO **nejsou v repu** (leží mimo, viz `AGENTS.md`). Převzatý kód: `PREEXISTING.md`.
