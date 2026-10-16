# Rakathon 2026 · Ostrava — plán týmu

> Stav k 15. 10. 2026 (pre-hack day). Zdroje: rakathon.cz, Slack #01-oznameni (všech 35 zpráv + 2 vlákna), slidy Tichopád / Opatřil / Kružík / Microsoft / Chatty, InterSystems Challenge, MS průvodce, FHIR AI Hackathon Kit, HL7 EU Common Cancer Model, SYNDERAI.

---

## 1. Finální zhodnocení výzvy

### Matice (1–5, vyšší = lepší)

| Výzva (Ostrava) | Proveditelnost za 24 h | Dostupnost dat | Návaznost na briefing* | Měřitelnost / demo | Konkurence | Stack cen** | **Σ** |
|---|---|---|---|---|---|---|---|
| **4. AI NOR** | 5 | 4 (syntetika snadná) | 5 | 5 | 4 | 5 | **28** |
| 2. AI asistent MDT | 4 | 4 | 5 | 3 | 2 (Asseco MDT Copilot v Praze, VZP „Cesta pacienta") | 4 | 22 |
| 1. Onkologický AI průvodce | 4 | 3 (schválené materiály FNO?) | 3 | 2 | 1 (RAG chatbot udělá každý) | 4 | 17 |
| 3. Plánování stacionáře | 3 | 1 (provozní data FNO neznámá) | 1 | 3 | 4 | 2 | 14 |
| 5. AI Surgical Copilot | 1 | 1 (operační video + kinematika) | 1 | 2 | 5 | 2 | 13 |

\* Opatřil slide 19 výslovně: *„B / vytěžování zpráv — AI extrakce klinických faktů s citací zdroje, lidským potvrzením, validace vůči profilům"* a *„C / podklady pro NOR"*. Kružík: Cancer Common = přesně pole NOR (diagnóza, CancerStage TNM, Surgery, Radiotherapy, SystemicTreatment, Progression).
\*\* Celkové pořadí (100k/50k/25k) + **cena děkana FEI VŠB-TUO** (technická kvalita, předává se v sobotu v Ostravě) + **InterSystems 1 500 EUR** (FHIR server + Vector Search) + Hackers' choice / Caelestinus / Asseco.

### Rozhodnutí
> ✅ **Potvrzeno 16. 10. 2026: AI NOR (FN Ostrava) + výzva InterSystems (1 500 €)**, řešení postavené na IRIS for Health (FHIR server, Vector Search, SQL, FHIR SQL Builder). Detaily: [INTERSYSTEMS_FHIR.md](INTERSYSTEMS_FHIR.md).

**Jdeme do 4. AI NOR.** Produkt pojmout jako *„strukturovaný onkologický záznam z volného textu"*:
- primární výstup = **hlášení do NOR** k potvrzení lékařem,
- stejná data uložená jako **FHIR (HL7 EU Common Cancer Model / mCODE)** v IRIS,
- **stretch**: druhá obrazovka **„MDT shrnutí"** (časová osa, chybějící údaje, rozpory) nad stejnými daty → pokryjeme i příběh výzvy 2 bez rizika rozplizlého scope.

### Co k tomu přidaly záznamy z pre-hack day
- **FN Ostrava sama používá technologii InterSystems pro integrace** (Hoferek: „fakultka v Ostravě… tuhle technologii pro tyhle účely používá"). AI NOR postavené na IRIS FHIR serveru = věrohodná cesta do reálného provozu přímo u zadavatele. Mentor InterSystems v Ostravě: **Dan Kutáč** (+ online 24/7).
- **Opatřil**: lékaři píšou volný text, strukturovaná data jsou přesnější, ale *„nesmíte je ubít tím, že těch strukturovaných dat bude moc"* — AI převod narativu na strukturu výslovně doporučil zkoušet. To je přesně argument AI NOR.
- **Hoferek (co přesvědčilo porotu dřív)**: promyšlená reprezentace dat ve FHIR, interoperabilita, dopad, a *„co jste přinesli navíc, co v zadání nebylo"*. Rada: **FHIR od první hodiny, ne „až na konci"**, a *keep it simple* (žádné OAuth apod.).
- **Organizátor**: porota čeká kvůli AI agentům **vyšší kvalitu výstupů než dřív**; v neděli hlasují i hackeři.

### Pivot pravidlo
Pokud v pátek 9:30–12:00 mentor FNO řekne, že pro AI NOR **nejsou žádná data ani přesný formát hlášení** a výzvu 2 má podloženou daty → přepneme na MDT asistenta. Jádro (extrakce s citacemi → FHIR) je v obou případech **stejné**, mění se jen UI. Rozhodnutí padne **nejpozději v 13:00**.

---

## 2. Otázky na mentora/zadavatele FNO (pátek dopoledne, PRVNÍ věc)

1. Dáte k výzvě data? Jaká (anonymizované zprávy / jen vzory)? Jak s nimi smíme zacházet (EU-only zpracování, žádné nahrávání do cloudových AI nástrojů)?
2. **Přesný seznam polí hlášení NOR**, který chcete vyplňovat (hlášenka, číselníky MKN-10, MKN-O-3 morfologie, grading, lateralita, cTNM/pTNM/ypTNM, stadium, způsob verifikace, léčba + data).
3. Z jakých dokumentů se dnes hlášení vyplňuje (propouštěcí zpráva, histologie, MDT zápis, operační protokol)? Kolik jich typicky na jednoho pacienta?
4. **Kolik času dnes hlášení zabere** (min / pacient, kdo ho dělá, kolik hlášení ročně FNO)? → *číslo do pitche, nevymýšlet!*
5. Nejčastější chyby / chybějící údaje v hlášeních?
6. Můžeme se v sobotu ráno ukázat na 10 minut a nechat si prototyp „otestovat" klinikem? (citát do pitche)

---

## 3. Setup prostředí

### 3.0 Pravidla a fakta z pre-hack day (záznamy)
- **Data k výzvám** se nasdílí do Slack kanálů výzev **nejpozději se startem hackování** (pátek po dopoledním bloku). Do té doby jsou kanály prázdné.
- **Předem připravený kód / boilerplate / UI komponenty smíte použít**, ale **musíte transparentně deklarovat**, co vzniklo před a co během Rakathonu; hodnotí se jen to, co vzniklo během. Submissions budou zveřejněny.
- **Demo stačí z lokálu**, Azure není povinný. Použití Azure / InterSystems **nemá vliv na hodnocení výzev** — jen na jejich vlastní ceny.
- **Cloudové LLM** jen pokud zadavatel potvrdí, že data jsou anonymní/syntetická. Jinak by byl potřeba lokální model (organizátoři ho nedodávají) → ptát se FNO (otázka 1 v §2).
- Azure: rozpočet ~100–200 USD / tým, **GPU VM zakázané**, role jen Contributor (žádné přiřazování RBAC). 429 na gateway = rate limit → **exponential backoff** v kódu.
- Copilot: ~**100 USD kreditu na osobu**; v Copilotu jsou i modely Anthropic/Google; na subagenty vybírat menší modely, drahé (reasoning „high") jen na architekturu/plánování. Copilot umí i **cloud agenta**, který jede, když notebook spí.
- Opatřil: „sdílet" zdravotnickou dokumentaci nejde — v řešení i pitchi říkat **„zpřístupnit"**. Nestavět vlastní eŽádanky. Počítat s ověřením pacienta proti **kmenovým registrům** (stačí jako „bílé místo"/stub v architektuře). Kódovat **MKN-10**; SNOMED v ČR málokdo zná (Kružík: nové CZ profily na SNOMED přecházejí → mít ho jako volitelný sloupec). DASTA pro nový vývoj nepoužívat.
- **Vyhláška 444/2024 Sb. o zdravotnické dokumentaci** — Opatřil radí mrknout při promptování, co je a není součástí ZD.

### 3.1 Účty a přístupy (jednou za tým, pátek ráno)
- [ ] Tým nahlášen organizátorům (ve vítací zprávě chybí odkaz za *„Tým nám pak nahlaste zde:"* → zeptat se v #02-dotazy).
- [ ] Slack jméno: `Jméno Příjmení (hacker - <tým> - Ostrava)`; join `#ai-nor`, `#08-tech-helpdesk`.
- [ ] Týmová kartička (UPN + TAP) → https://aka.ms/rakathon2026 → zkopírovat **API klíč**, Base URL, názvy deploymentů. **Kartičku/klíč nikdy do gitu, Slacku ani screenshotů.**
- [ ] Ověřit `rg-teamNN` v Azure Portalu (role Contributor).
- [ ] Každý: GitHub Copilot přes portál (osobní GitHub, ne EMU; pozor — **zruší existující individuální Copilot**; organizace akce se **19. 10. maže** → repo držet na vlastním GitHubu).

### 3.2 LLM gateway (pro naši aplikaci)
- Base URL: `https://apim-rakathon-q7146n.azure-api.net/openai/v1/` (ověřit v portálu)
- Hlavička **`api-key`**, ne `Authorization: Bearer`. Do `model` jde **název deploymentu**, ne zobrazovaný název.
- Pro zdravotnický text **jen deploymenty `-dz-eu`** (EU Data Zone), např. `gpt-6-1-sol-dz-eu`. Global = zpracování mimo EU.
- Kvóta: **~4 M tokenů / tým / den** sdílených pro všechny textové modely. Při 401 = klíč / pozastaveno, 429 = limit → čekat, nesmyčkovat.
- Dostupné (14. 10.): gpt-6.1-sol, gpt-6-astra, gpt-6-luna, grok-4.7, DeepSeek-V4-Pro, Kimi-K2.7-Code, MAI-Thinking-1, MAI-Image-2.5 (obrázky — hodí se na pitch vizuály).

```python
# backend/app/llm.py — jediné místo, kde se volá model
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key="unused",
    default_headers={"api-key": os.environ["LLM_API_KEY"]},
)
MODEL = os.environ.get("LLM_MODEL", "gpt-6-1-sol-dz-eu")
```

### 3.3 Lokální stack (Windows; každý vývojář)
Potřeba: Git, Python 3.12, Node 20+, Docker Desktop (běžící), VS Code / Cursor.

```bash
git clone https://github.com/intersystems-community/FHIR-AI-Hackathon-Kit.git
```

```powershell
cd FHIR-AI-Hackathon-Kit; .\docker-iris-fhir\start.ps1
```

- Ověřit, že FHIR endpoint odpovídá (adresa a credentials jsou v README kitu / `docker-iris-fhir`), projít tutoriály **3.1–3.4 (FHIR)** a **4.1 (Vector Search)** — to je přesně to, co použijeme.
- Co kit umí (z workshopu Hoferka): předpřipravený FHIR repozitář R4 (s ukázkovými vygenerovanými daty — **smazat/založit nový**), POST jednotlivých resources i **transakčních Bundle** (3.4), bulk import velkých souborů, Management Portal, **FHIR SQL Builder** (projekce FHIR → SQL tabulky — hodí se na export NOR), tabulky s typem `VECTOR` + embeddingy (4.1), Python agent tools nad SQL / vector / FHIR (5.1) a **MCP server přes FastMCP** (5.2). Skript v 3.0 vytvoří FHIR server i na vzdálené instanci (např. v Azure Container Apps).
- Kit čte OpenAI klíč z `.env` → nastavit base URL + `api-key` z gateway (nebo jen převzít kód a volat přes náš `llm.py`).
- **Dnes (čtvrtek) večer**: stáhnout Docker image IRIS a ověřit start — na Wi-Fi v sále to může trvat. *Produktový kód až od pátku 12:00 (pravidla hackathonu) — dnes jen prostředí a čtení dokumentace.*

### 3.4 AI nástroje pro vývoj
| Nástroj | Na co |
|---|---|
| **Claude Code** (CLI / desktop) | hlavní agent: scaffolding, větší featury, refaktory, testy; běží paralelně ve více worktrees |
| **GitHub Copilot** (zdarma od MS) | inline doplňování v editoru, rychlé dotazy; Copilot CLI jako druhý agent |
| **Cursor** (volitelně) | kdo je zvyklý; stejná pravidla z `AGENTS.md` |
| **Gateway modely** | jen runtime aplikace + generování syntetických dat |

**Pravidlo dat:** reálná (i anonymizovaná) data od FNO **nevkládat do Claude Code / Copilot / Cursor promptů**. Agenti pracují se syntetikou; reálná data jdou jen přes naši aplikaci na `-dz-eu` deployment, pokud to FNO povolí.

---

## 4. Repo setup

### 4.1 Struktura
```
ai-nor/
├─ AGENTS.md                    # pravidla pro všechny AI agenty (CLAUDE.md = kopie/odkaz)
├─ .github/copilot-instructions.md
├─ README.md                    # problém, architektura, jak spustit (FEI cena!)
├─ .env.example                 # LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, FHIR_BASE_URL
├─ docker-compose.yml           # iris-fhir + api + web
├─ contracts/                   # ⬅ PRVNÍ COMMIT, pak se mění jen po domluvě
│  ├─ nor_record.schema.json    # pole NOR + evidence {quote, doc_id, start, end} + confidence
│  ├─ fhir_mapping.md           # pole NOR → Common Cancer Model / mCODE / FHIR resource
│  └─ api.md                    # POST /extract, GET /cases/{id}, PUT /cases/{id}/fields, POST /cases/{id}/fhir, GET /cases/{id}/nor-export
├─ backend/                     # FastAPI (Python)
│  ├─ app/main.py
│  ├─ app/llm.py
│  ├─ app/ingest/               # pdf/docx/txt → text + sekce
│  ├─ app/extract/              # retrieval (IRIS vector) + LLM structured output per skupina polí
│  ├─ app/validate/             # pravidla: TNM konzistence, data, číselníky, negace
│  ├─ app/fhir/                 # build Bundle + POST do IRIS FHIR
│  └─ tests/
├─ frontend/                    # Vite + React + TS + Tailwind (+ shadcn/ui)
├─ data/synthetic/{reports,gold}/
├─ eval/run_eval.py             # přesnost/úplnost po polích → eval/report.md + graf
└─ docs/{architecture.md, pitch/}
```

### 4.2 `AGENTS.md` (zkopírovat do repa a doplnit)
```markdown
# AI NOR — pravidla pro agenty
- Cíl: z české onkologické dokumentace vytěžit pole hlášení NOR s citací zdroje; lékař potvrzuje.
- Kontrakty v /contracts jsou zdroj pravdy. Neměň je bez výslovného pokynu; když nesedí, napiš to.
- Backend: Python 3.12, FastAPI, pydantic v2, pytest. Frontend: React + TS + Tailwind, bez dalších UI knihoven bez důvodu.
- LLM voláme výhradně přes backend/app/llm.py. Žádné klíče v kódu ani ve frontendu.
- Každé vytěžené pole MUSÍ mít evidence (citace + offset) nebo být `null` se stavem "chybí".
- Žádné reálné pacientské údaje v kódu, testech ani promptech. Jen data/synthetic.
- Před commitem: `pytest -q` a `npm run build` musí projít.
- Malé commity, zpráva česky v rozkazovacím způsobu.
```

### 4.3 Git workflow (4 lidi + N agentů)
- `main` vždy spustitelný. Krátké větve `feat/<oblast>`, merge každé 1–2 h. Žádné velké PR review — rychlá kontrola diffu partnerem.
- **Vlastnictví složek** = žádné konflikty: Backend/AI → `backend/app/extract|llm|validate`, FHIR/IRIS → `backend/app/fhir` + docker, Frontend → `frontend/`, Klinik/eval/pitch → `data/`, `eval/`, `docs/pitch`.
- Paralelní agenti: každý ve vlastním **git worktree** (`git worktree add ../ai-nor-ui feat/ui`), jinak si přepisují soubory.
- Kontrakt-first: první hodina = `contracts/` + mock odpovědi API → frontend jede proti mocku, backend proti testům, nikdo na nikoho nečeká.

---

## 5. Jak efektivně vibecodovat

1. **Plán před kódem.** Každý větší úkol: *„Přečti AGENTS.md a contracts/. Navrhni plán v bodech, nic neměň."* → schválit → *„Proveď body 1–3, spusť testy."*
2. **Úkoly velikosti 20–40 min.** Jedna featura = jeden prompt + ověření. Velké „udělej celou appku" = chaos.
3. **Testy jako řídítka.** U extrakce nejdřív napsat `gold` JSON pro 3 zprávy + pytest, pak nechat agenta iterovat, dokud neprojde.
4. **Agent nesmí hádat API IRIS/FHIR** — dej mu odkaz na konkrétní notebook z Hackathon Kitu nebo příklad z Common Cancer Model jako vzor.
5. **Každých ~60 min integrace** na `main` a ruční proklik celé cesty (upload → extrakce → potvrzení → FHIR → export).
6. **Agent zasekne > 15 min** → stop, `git restore`, přeformulovat menší krok nebo napsat ručně.
7. **Syntetická data generuje LLM** (gateway, ne Claude Code): prompt s personou, diagnózou, stadiem → *„napiš propouštěcí zprávu + histologii + MDT zápis ve stylu české nemocnice, s typickými zkratkami (st.p., l.dx., susp., neg.)"* a **současně** gold JSON. Inspirace stylu: SYNDERAI, Common Cancer Model příklad (karcinom plic).
8. Záměrně přidat **těžké případy**: negace („bez známek meta"), více dat a staging v čase (cTNM vs pTNM vs ypTNM), protichůdné údaje, chybějící údaj. To je to, co porota ocení.
9. Tokeny: cache odpovědí LLM podle hashe (dokument + prompt + model), eval jen na změněné, žádné retry smyčky.

---

## 6. Architektura řešení

```
dokumenty (PDF/DOCX/TXT)
   │ ingest: text + sekce + offsety
   ▼
IRIS Vector Search (chunky)  ──►  retrieval pro každou skupinu polí
   ▼
LLM (EU deployment), structured output dle nor_record.schema.json
   │   každé pole: hodnota + kód (MKN-10 / MKN-O-3 / TNM) + citace + confidence
   ▼
validace pravidly (TNM ↔ stadium, data v pořadí, negace, číselníky) → flagy ⚠
   ▼
UI „review": vlevo dokument se zvýrazněnou citací, vpravo pole ✓/✎/✗
   ▼ po potvrzení
FHIR Bundle (Common Cancer Model / mCODE) → IRIS FHIR server
   ▼
export NOR (JSON/CSV) + audit (kdo co potvrdil/opravil)
   ▼ (stretch)
MDT shrnutí: časová osa, chybějící podklady, rozpory
```

Klíčové designové body pro porotu:
- **Human-in-the-loop**: AI navrhuje, lékař potvrzuje — nic se neodesílá automaticky.
- **Každé tvrzení dohledatelné** (citace), nejistota viditelná, chybějící ≠ negativní.
- **Standardy**: FHIR R4, HL7 EU Common Cancer Model, mCODE; EU-only zpracování.
- **Měřitelné**: eval tabulka přesnost/úplnost po polích + čas „ručně vs s AI".

---

## 7. Časový plán

| Kdy | Co | Výstup |
|---|---|---|
| **Čt večer** | Docker + IRIS kit běží u ≥ 2 lidí, Copilot registrace, projít tutoriály 3.x + 4.1, slidy Opatřil 17–19 | ověřené prostředí |
| **Pá 9:30–12:00** | registrace, představení výzev, **otázky z §2 mentorovi FNO**, kartička + API klíč, první volání modelu | odpovědi, rozhodnutí výzvy |
| **12:00–13:00** | repo, `AGENTS.md`, **contracts/**, mock API, rozdělení rolí | kostra na `main` |
| **13:00–16:00** | ingest, extrakce 1. skupiny polí (diagnóza, morfologie, TNM) s citacemi; UI kostra; IRIS FHIR POST; 10 syntetických případů + gold | první end-to-end „tracer bullet" |
| **16:00–20:00** | všechna pole (léčba, data, biomarkery), validace, review UI se zvýrazněním; vector search v IRIS | funkční MVP |
| **20:00 checkpoint** | proklik s mentorem, **zmrazit scope** | seznam „must / nice" |
| **20:00–02:00** | eval skript + report, těžké případy, FHIR Bundle dle Common Cancer Model, export NOR, audit; stretch MDT pohled | čísla do pitche |
| **02:00–07:00** | spánek na směny (vždy min. 1 vzhůru na integraci) | — |
| **So 07:00–09:00** | bugfix, deploy (Container Apps / SWA v `rg-teamNN`), **záložní video dema** | veřejná URL + video |
| **09:00 FEATURE FREEZE** | jen pitch: deck, demo script, 3× generálka s časomírou | — |
| **12:00** | **odevzdání** (repo, README, video, deck) | — |
| **13:00** | lokální pitch Ostrava; 17:00 vyhlášení → neděle 14:00 finále Praha | — |

---

## 8. Strategie na výhru

### Co reálně vyhrává hackathony
1. **Funkční živé demo end-to-end** > množství featur. Jedna cesta, která 100 % funguje.
2. **Konkrétní problém s číslem od zadavatele** („hlášení NOR trvá X min, FNO jich dělá Y ročně" — z §2 otázky 4).
3. **Porota = lidé z nemocnice + technici** → mluvit jejich jazykem: bezpečnost, odpovědnost, kdo co potvrzuje, jak to zapadne do NIS.
4. **Důvěryhodnost**: citace u každého pole, evaluační čísla, přiznané limity. Žádné „AI vyřeší vše".
5. **Cesta dál**: standardy (FHIR/EHDS) = „nebude to jen pro FNO" (Chatty: *make the next hospital say yes*). Pro AI NOR navíc: **FNO už InterSystems pro integrace používá** → „napojení na vaši stávající integrační platformu".
6. **„Něco navíc, co v zadání nebylo"** (InterSystems o minulých vítězích) — u nás: detekce rozporů mezi dokumenty, upozornění na chybějící údaje pro NOR, eval dashboard, MDT pohled.
7. **Porota kvůli AI agentům čeká vyšší laťku** (organizátor) → kvalita a dotaženost > počet featur.
8. **Mentora/zadavatele zapojit průběžně** — kdo s ním mluvil 3× a zapracoval feedback, má v porotě spojence.

### Pitch (3–5 min, ověřit limit u organizátorů)
1. **Hook (20 s)**: příběh — lékařka po ambulanci přepisuje z 5 zpráv údaje do registru. Číslo od FNO.
2. **Problém (30 s)**: čas, chyby, neúplná data v NOR → horší data pro celé Česko.
3. **Demo (2 min)**: nahraj zprávy → za X s vyplněné hlášení → klik na pole ukáže citaci → ⚠ rozpor TNM → lékař opraví → potvrdí → FHIR v IRIS + export NOR.
4. **Proč tomu věřit (40 s)**: eval tabulka (přesnost po polích), human-in-the-loop, EU-only zpracování, Common Cancer Model / FHIR.
5. **Dopad a další krok (30 s)**: úspora času × počet hlášení; pilot ve FNO; přenositelnost (EHDS).
6. **Ask**: „Chceme to pilotovat na Vašem oddělení."

### Mapování na ceny
| Cena | Co ukázat |
|---|---|
| Celkové pořadí | dopad + demo + čísla |
| **FEI VŠB-TUO** (technika, sobota) | čisté repo, README, architektura, testy, eval, docker-compose — „funguje u vás za 5 min" |
| **InterSystems 1 500 €** | IRIS FHIR server jako úložiště potvrzených dat + **Vector Search** pro citace; v pitchi 1 slide „proč IRIS"; zmínit kritéria: inovace, dopad, využití IS, technická ucelenost |
| Hackers' choice (hlasují hackeři v neděli) | hezké UI, srozumitelný příběh, buďte vidět ve Slacku/na místě, pomáhejte ostatním |
| Opatřil (Umbrellateam) — vstup na „Národní dialog pro digitalizaci" 19. 10. v ILF | pro vítězný tým; FHIR / IHE MHD / kmenové registry v architektuře |
| Caelestinus / Asseco / MEDDI | slide „cesta k produktu" (pilot → další nemocnice → integrace s NIS) |

### Rizika a mitigace
| Riziko | Mitigace |
|---|---|
| Žádná data od FNO | syntetika + gold set od 13:00; v pitchi přiznat a ukázat eval |
| Vyčerpání tokenů | cache, malé prompty, eval jen na diff, 1 člověk hlídá spotřebu |
| IRIS/Docker zlobí | FHIR adaptér za rozhraním; fallback = uložit Bundle JSON, IRIS dopojit později |
| Výpadek Wi-Fi/gateway při pitchi | **nahrané video dema** + předpočítané výsledky v aplikaci |
| Scope creep (MDT, chatbot…) | freeze ve 20:00, MDT jen pokud MVP + eval hotové |
| Halucinace | povinná citace, jinak pole `null`; validace pravidly; lékař potvrzuje |

---

## 9. Odkazy
- Portál účastníků: https://aka.ms/rakathon2026 · MS průvodce: https://michalmar.github.io/rakathon-env/docs/newcomer-guide.standalone.html
- InterSystems Challenge: https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/
- FHIR AI Hackathon Kit: https://github.com/intersystems-community/FHIR-AI-Hackathon-Kit
- HL7 EU Common Cancer Model: https://hl7.eu/fhir/cancer-common/ (artefakty + příklad karcinomu plic)
- mCODE STU4: https://hl7.org/fhir/us/mcode/STU4/ · CZ FHIR: https://hl7.cz/fhir/
- Syntetická EU FHIR data: https://synderai.net/ · Synthea: https://synthetichealth.github.io/synthea/

---

## 10. Změny po pátku (16. 10., ~14:30)

Zdroje: slidy výzev (Google Drive „Prezentace/Ostrava“), Slack #01-oznameni, #02-dotazy, #05-info-ostrava, kanály výzev, živý přehled https://submit.rakathon.cz/vyzvy.

### Obsazenost ostravských výzev (14:32)
| Výzva | Týmy | Data od zadavatele (ze slidů) |
|---|---|---|
| 1. Onkologický AI průvodce | 1 (Wigym Trio) | informační materiály, Modrá kniha, EQ-5D, FAQ, kontakty |
| 2. AI asistent MDT | 1 (Codebridge) | dokumentace fiktivních pacientů, struktura MDT protokolu FNO |
| 3. Plánování stacionáře | **0** | **anonymizované objednávky (30 dní) + aplikační rozpis chemoterapie** |
| **4. AI NOR** | **0** | modeloví pacienti (amb. zprávy, histologie, propouštěcí zprávy), ukázka hlášení, datový slovník MKN-10 |
| 5. AI Surgical Copilot (FNOL) | 2 | Dropbox: data + videa |
| VZP společné (konec života, mamograf, cesta pacienta) | 0 v Ostravě | data v portálu účastníka (Azure) |

Náš tým na přehledu figuruje jako **„www.pixed.cz“ (stůl 11) bez vybrané výzvy** → kapitán musí vybrat na https://submit.rakathon.cz/vyzvy/vybrat **do 19:00**.

### Přehodnocení
| Výzva | Proveditelnost | Data | Briefing | Demo | Konkurence | Ceny | Σ | změna |
|---|---|---|---|---|---|---|---|---|
| **4. AI NOR** | 5 | 5 | 5 | 5 | 5 | 5 | **30** | data potvrzena, 0 týmů, zadavatel dal i kritéria |
| 3. Stacionář | 4 | 4 | 1 | 4 | 5 | 3 | 21 | ↑ data existují (dřív 14) |
| 2. MDT | 4 | 4 | 5 | 3 | 3 | 4 | 23 | Asseco MDT Copilot v Praze bez týmu, v Ostravě 1 tým |
| 1. Průvodce | 4 | 4 | 2 | 3 | 3 | 3 | 19 | |
| 5. Surgical | 1 | 3 | 1 | 2 | 2 | 2 | 11 | |

**Verdikt: AI NOR platí.** Žádná konkurence v lokalitě, data i vzor hlášení od FNO, hodnoticí kritéria zadavatele se kryjí s naším eval plánem (přesnost, úplnost, správné pole, dohledatelnost, počet oprav, čas). Pivot na MDT už nedává smysl (má tým, my bychom byli druzí). Stacionář je rozumná záloha jen pokud by data k NOR nepřišla — je ale mimo FHIR/LLM příběh, takže slabší na InterSystems a briefing.

### Okamžité kroky
1. Kapitán: vybrat výzvu AI NOR na submit.rakathon.cz (do 19:00).
2. Vyzvednout data u mentorky FNO (místnost mentorů) — zeptat se na formát a zda smí do cloud LLM `-dz-eu`.
3. Z ukázky hlášení + datového slovníku udělat `contracts/nor_record.schema.json`.

### Doplnění (16. 10., ~15:00) — z info.rakathon.cz a Slacku
- **Odevzdání je v sobotu ve 13:00** přes formulář (po 13:00 už nic nepřijme), ne ve 12:00. Feature freeze tedy posunout na ~10:00.
- **Hodnocení zadavatelem je osobně u stolu**: od 14:00 Ing. Najbrtová obchází týmy své výzvy a hodnotí každý zvlášť → **živé demo u stolu**, ne jen pitch. Vítěz výzvy hlášen do 16:00, vyhlášení 17:00–18:00, **vítěz každé výzvy postupuje do nedělního finále v Praze** (Kampus Plzeňská, finalisté do 13:00).
- AI NOR má zatím 0 týmů → pokud zůstane, soutěžíme hlavně sami se sebou o postup do finále.
- #ai-nor je zatím prázdný (jen joiny); data FNO se rozdávají osobně (máme je, viz `../Rakathon_DATA_NOR/PREHLED_DAT.md`, mimo repo).
- Konkurenční signál: hacker „Stan“ (#06-hledam-tym) staví MEMOyA — AI přečte spis, najde chybějící a rozporné údaje s doslovnou citací; cílí na MDT + InterSystems. Podobné jádro jako my → odlišit se FHIR (Common Cancer Model) výstupem a přesným mapováním na formulář NOR.
