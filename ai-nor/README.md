# AI NOR — strukturované onkologické hlášení z volného textu

Rakathon 2026 Ostrava · výzva **AI NOR (FN Ostrava)** + výzva **InterSystems (AI & interoperabilita)**. Plán, cíle a návrh UI: [PLAN.md](PLAN.md).

AI z klinické dokumentace (ambulantní a propouštěcí zprávy, histologie, MDT) vytěží pole hlášení do
Národního onkologického registru **s citací zdroje**. Lékař každé pole potvrdí nebo opraví a potvrzené
hlášení se uloží jako **FHIR R4** do **InterSystems IRIS for Health** (stejná platforma, kterou FNO používá pro integrace).

```
dokumenty (PDF/TXT/XLSX z NIS)
  → ingest (text + offsety)                       backend/app/ingest
  → extrakce s citacemi (LLM -dz-eu / mock)       backend/app/extract, app/llm.py
      ↳ retrieval: IRIS Vector Search (Nor.Chunk)
  → validace (MKN-10, TNM, data)                  backend/app/validate
  → review UI: dokument ↔ pole ✓/✗                frontend/
  → FHIR transaction Bundle + Provenance → IRIS   backend/app/fhir
  → export NOR (FHIR SQL Builder)                 TODO
```

## Spuštění (Windows)

Potřeba: Python 3.12, Node 20+, Docker Desktop (běžící).

```powershell
copy .env.example .env          # doplnit LLM_API_KEY; LLM_MODE=live (mock jede bez klíče). Data FNO (Rakathon_DATA_NOR) patří vedle složky rakathon-2026
cd backend; python -m venv .venv; .\.venv\Scripts\pip install -e ".[dev]"; cd ..
.\start-iris.ps1                # IRIS + prázdný FHIR server /fhir/r4 + tabulky Nor.Chunk, Nor.Code
cd backend; .\.venv\Scripts\python -m scripts.index_codes     # číselníky MKN-10 + morfologie do IRIS (~1,5 min)
.\.venv\Scripts\uvicorn app.main:app --port 8000
cd frontend; npm install; npm run dev     # http://localhost:5173
```

- Syntetičtí pacienti k nahrání: `data/synthetic/PAC001` … `PAC010` (vytvoří `python -m scripts.export_synthetic <složka s XLSX>`).
- Číselníky formuláře (MKN-10, topografie, morfologie): balíček MKN-10 od ÚZIS ve složce `uploads/` (CSV v UTF-8 i Windows-1250, `CODELISTS_DIR`), jinak složka `MKN10_CSV`.
- LLM: `gpt-6-luna-dz-eu` (EU Data Zone), `reasoning_effort=low`, odpovědi se cachují v `backend/var/llm-cache`.
- Embeddingy běží **lokálně** (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dim, model se stáhne do `backend/var/models`), text zpráv neopouští počítač.
- FHIR: `http://localhost:52773/fhir/r4/metadata` (SuperUser / SYS — jen dev) · Management Portal: `http://localhost:52773/csp/sys/UtilHome.csp`
- Testy: `cd backend; .\.venv\Scripts\pytest -q` · build: `cd frontend; npm run build`

## Struktura
| Složka | Obsah | Vlastník |
|---|---|---|
| `contracts/` | JSON schéma hlášení, API, FHIR mapování — **zdroj pravdy** | všichni po domluvě |
| `backend/app/extract`, `llm.py`, `validate` | extrakce, LLM, validace | Backend/AI |
| `backend/app/fhir`, `infra/`, `scripts/setup_iris.py` | FHIR + IRIS | FHIR/IRIS |
| `frontend/` | review UI | Frontend |
| `data/synthetic`, `eval/` | syntetická data, gold, evaluace | Klinik/eval |

Data FNO **nejsou v repu** (leží mimo, viz `AGENTS.md`). Převzatý kód: `PREEXISTING.md`.
