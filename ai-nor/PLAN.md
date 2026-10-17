# AI NOR — plán aplikace

> Stav: pá 16. 10. 2026, 16:15. Odevzdání **so 13:00** (formulář), **od 14:00 hodnocení u stolu** (živé demo pro Ing. Najbrtovou, FNO), 17:00 vyhlášení.
> Výzvy: **AI NOR (FN Ostrava)** + **InterSystems (AI & interoperabilita)**. Technika: [README.md](README.md), FHIR: [contracts/fhir_mapping.md](contracts/fhir_mapping.md).

---

## 1. Cíl aplikace

**Z volného textu onkologické dokumentace připravit hlášení do Národního onkologického registru (NOR, spravuje ÚZIS)
tak, aby ho zdravotník nemusel ručně přepisovat ani kontrolovat pole po poli.**

U každého údaje aplikace ukáže **odkud ho vzala** (citace v dokumentu) a **jistotu 0–100**.
**Samostatně řešit musí lékař jen dvě situace:**
1. **Rozpor:** dokumenty v systému uvádějí pro stejné pole různé hodnoty.
2. **Nízká jistota:** AI si hodnotou není jistá (skóre pod prahem, výchozí 80).

Ostatní pole (bez rozporu, jistota ≥ 80) jsou **předvyplněná**: lékař je nemusí potvrzovat jednotlivě.
**Nic se ale neodesílá automaticky.** Lékař si na konci zkontroluje **náhled celého hlášení** (všechna pole s citací a jistotou)
a odešle ho tlačítkem **„Potvrdit hlášení“**. Teprve potom jde export do ÚZIS a zápis do FHIR.

| Cíl | Jak ho změříme | Kritérium FNO |
|---|---|---|
| Přesnost vytěžení | shoda s referenčními (gold) hodnotami po polích | Přesnost vytěžení |
| Úplnost | povinná pole vyplněná nebo výslovně označená „chybí“ | Úplnost údajů |
| Správné pole NOR | hodnota v číselníku a správném poli formuláře | Správné přiřazení |
| Dohledatelnost | 100 % vyplněných polí má ověřenou citaci | Dohledatelnost |
| Méně oprav | počet úprav uživatelem na jedno hlášení (měří UI) | Počet oprav |
| Méně kontroly | podíl předvyplněných polí, která lékař nemusel řešit jednotlivě (cíl ≥ 70 %), a jejich přesnost (cíl ≥ 97 %) | Čas na záznam |
| Rychlost | čas od otevření případu po odeslání proti ručnímu postupu (měří UI) | Čas na záznam |
| Důvěra v AI | indikátor jistoty je kalibrovaný: pole s jistotou ≥ 80 jsou opravdu správná | (něco navíc) |

**Výstupy:**
1. **Hlášení pro ÚZIS/NOR** ve struktuře a číselnících formuláře „Incidence zhoubného novotvaru“ (viz §5).
2. **FHIR R4 v InterSystems IRIS**: údaje hlášení + Provenance (kdo hlášení potvrdil, kdy, z jakého dokumentu, které pole lékař řešil ručně a které převzal z předvyplnění) pro interoperabilitu s NIS a budoucí EHDS.

**Demo scénář (3 min u stolu):**
nahrát zprávy pacienta → za několik sekund vyplněný formulář, většina polí předvyplněná →
fronta „Ke kontrole (2)“: rozpor mezi dvěma zprávami (obě citace vedle sebe, vybrat jednu) a jedno nejisté pole (klik ukáže citaci, opravit) →
**náhled hlášení** ve tvaru formuláře ÚZIS → lékař projde a klikne **„Potvrdit hlášení“** → export pro ÚZIS + zápis do FHIR →
na závěr dashboard: přesnost předvyplněných polí, kalibrace jistoty, čas a počet oprav.

---

## 2. Architektura

```
 PDF / TXT / XLSX (export z NIS)
        │
 ┌──────▼──────────────────────── backend (FastAPI) ───────────────────────────────┐
 │ 1 ingest + typ dokumentu + pacient  →  2 sekce + deterministické kotvy           │
 │ 3 index (IRIS Vector Search)  →  4 extrakce po skupinách polí (LLM -dz-eu)       │
 │ 5 ověření citací  →  6 normalizace na číselníky NOR  →  7 validační pravidla     │
 │ 8 skóre jistoty  →  9 review API + audit  →  10 výstupy: ÚZIS export │ FHIR→IRIS │
 └───────────────────────────────────────────────────────────────────────────────────┘
        │                                       │
   frontend (review UI)                InterSystems IRIS for Health
                                        FHIR server · SQL (číselníky, chunky) · FHIR SQL Builder
```

---

## 3. Backend: co dělá

Kód: `backend/app/`. Moduly a stav (✅ hotovo v kostře, 🔨 udělat):

| # | Krok | Modul | Co přesně | Stav |
|---|---|---|---|---|
| 1 | **Ingest** | `ingest/` | PDF (PyMuPDF), TXT, XLSX export z NIS (1 řádek = 1 dokument, Excel data → ISO, HTML → text). Typ dokumentu (AZ / PZ / histologie / MDT / operační protokol) podle názvu a obsahu. Datum dokumentu. Seskupení podle pacienta s **varováním při nesouladu identity** (jiné RČ v jednom dokumentu). | ✅ základ, 🔨 typ z obsahu, datum, identita |
| 2 | **Sekce + kotvy** | `ingest/sections.py` | Rozdělit na sekce (Závěr, Mikropopis, Diagnostický souhrn, Dg., Doporučení) s offsety. **Deterministicky** parsovat patičku histologie `M1: M81403` → morfologie `8140/3`, `TOP: …`, číslovaný „Závěr“ (typ, grading, okraje, uzliny, pTNM), řádky `Dg.: C50.4`. | 🔨 |
| 3 | **Index** | `retrieval/` | Chunky (300–800 znaků s offsety) → embeddingy → tabulka `Nor.Chunk` v IRIS, dotaz `VECTOR_COSINE` filtrovaný na případ. **Záloha bez embeddingů:** klíčová slova a BM25 v Pythonu, ať nás chybějící embedding deployment nezablokuje. | 🔨 (tabulka ✅) |
| 4 | **Extrakce** | `extract/` | LLM přes `llm.py` (EU deployment), **po skupinách polí**: ① diagnóza + topografie + lateralita + datum, ② morfologie + grading, ③ cTNM / pTNM / ypTNM + stádium, ④ metastázy, ⑤ biomarkery, ⑥ léčba, ⑦ progrese. Každá hodnota musí přijít s **doslovnou citací a ID dokumentu**. Pravidla v promptu: negace („bez známek meta“), suspekce ≠ diagnóza, cTNM ≠ pTNM ≠ ypTNM, starý nádor (onkoduplicita) ≠ nové hlášení, nic nedomýšlet. Odpovědi se cachují. | ✅ mock, 🔨 live |
| 5 | **Ověření citací** | `extract/evidence.py` | Citaci najít v textu dokumentu (normalizace mezer, diakritiky, OCR překlepů) → přesné offsety. **Nenalezená citace = hodnota se nezobrazí jako jistá** (viz §4). | 🔨 |
| 6 | **Normalizace na číselníky** | `validate/codes.py` | Hodnotu z textu namapovat na položku číselníku, **nikdy nevymýšlet kód** (viz §3.1): kód v textu → přesná shoda s rejstříkem → sémantický výběr z top 5 kandidátů v IRIS. MKN-10 → kód + „Dg. slovně“, MKN-O-3 morfologie a topografie, pevné číselníky formuláře (lateralita 1/2/3/4/9, grading 1–9, „Onemocnění“ 1/2/9) a **bitové součty** („K dg. vedla vyšetření“, „Lokalizace metastáz“, „Pracoviště hlásící“). | ✅ MKN-10 lookup, 🔨 zbytek |
| 7 | **Validace** | `validate/rules.py` | Platný kód MKN-10 z kapitoly ZN. **Vztah Diagnóza / Topografie / Morfologie** (stejná kontrola jako ve formuláři ÚZIS): C50 ↔ topografie C50.x, chování /3. TNM ↔ stádium. Pořadí dat (dg ≤ operace ≤ adjuvance). Onkoduplicita. Povinná pole → stav **Úplné / Neúplné**. | 🔨 |
| 8 | **Skóre jistoty 0–100** | `confidence.py` | Skóre z ověřitelných signálů, detekce rozporů mezi dokumenty, rozhodnutí „předvyplněno / ke kontrole“. Viz §4. | 🔨 |
| 9 | **Kontrola, potvrzení + audit** | `main.py`, `store/` | Pole s jistotou ≥ 80 bez rozporu jsou předvyplněná. Rozpory a pole pod prahem jdou do fronty, kde je lékař potvrdí / upraví / zamítne. Dokud fronta není prázdná, nejde hlášení potvrdit. **Potvrzení celého hlášení** (`POST /api/cases/{id}/confirm`: kdo, kdy) je jediná cesta k exportu ÚZIS a zápisu do FHIR. Každá změna se loguje (kdo, kdy, před → po) a z logu se počítá počet oprav a čas. | ✅ PUT report, 🔨 potvrzení hlášení, audit, metriky |
| 10a | **Export ÚZIS** | `export/uzis.py` | Viz §5. | 🔨 |
| 10b | **FHIR → IRIS** | `fhir/` | Transaction Bundle (Patient, DocumentReference, Condition, Observation TNM a grading, Provenance). Ověřeno proti běžícímu IRIS. | ✅ základ, 🔨 metastázy, markery, léčba |
| 11 | **Evaluace** | `eval/` | Gold JSON pro syntetických 10 pacientů (XLSX) + pacienty FNO (gold připraví klinik týmu, **mimo repo**). Metriky po polích, kalibrace jistoty, report + graf do pitche. | 🔨 |

**API** (doplnit do `contracts/api.md`):
`POST /api/cases` · `POST /api/cases/{id}/extract` · `PUT /api/cases/{id}/report` ·
`POST /api/cases/{id}/events` (čas a opravy z UI) · `POST /api/cases/{id}/confirm` (lékař potvrdí náhled; bez něj export ani FHIR nejdou) · `GET /api/cases/{id}/uzis-export?format=json|xml|csv|pdf` ·
`GET /api/cases/{id}/fhir-bundle` · `POST /api/cases/{id}/submit` (FHIR → IRIS) · `GET /api/eval` (metriky pro dashboard).

### 3.1 Číselníky a výběr kódů pro rozbalovací seznamy

Pole formuláře ÚZIS jsou rozbalovací seznamy nad **oficiálními číselníky** (Dg. MKN, Kód morfologie, Grading…).
**AI nikdy nevymýšlí kód.** Z textu vytáhne hodnotu s citací a backend ji namapuje na existující položku číselníku.
Kód, který v číselníku není, se do hlášení nedostane. Detail polí a hodnot: [contracts/nor_form.md](contracts/nor_form.md).

**Odkud číselníky bereme** (soubory leží mimo repo v `../../Rakathon_DATA_NOR/Rakathon_DATA_NOR/mkn-10-strukturovane-podklady-20260101/`):

| Pole | Zdroj | Máme? |
|---|---|---|
| Dg. MKN + Dg. slovně | **MKN-10 ÚZIS** `cp_utf8/01_MKN10_5E_2026_utf8.csv` (`KodSTeckou`, `Nazev`); pro NOR kapitola C (+ D00–D09 in situ, D37–D48 nejisté) | ✅ celé, už se načítá (`MKN10_CSV` v `.env`) |
| Kód morfologie | **MKN-O-3** morfologie `NNNN/C`. Částečně v rejstříku MKN-10 `cp_utf8/05_…nemoci a poranění_utf8.csv`: **702 kódů** s českými termíny, např. „Adenokarcinom (M8140/3)“, „– duktální (M8500/3)“, „bazocelulární (M8090/3)“ | 🟠 702 kódů; úplný MKN-O-3 vyžádat |
| Topografie | **MKN-O-3** topografie C00.0–C80.9. Kódy se z velké části kryjí s MKN-10 C00–C80, názvy bez „ZN –“ („C44.5 - Kůže trupu“). Rejstřík lokalizací `cp_utf8/07_…novotvary_utf8.csv` | 🟠 přibližně z MKN-10 |
| Typ morfologie, Lateralita, Grading, Onemocnění | malé pevné seznamy ze screenshotu formuláře | ✅ |
| K dg. vedla vyšetření, Lokalizace metastáz, Pracoviště hlásící | pevné bitové hodnoty z formuláře | ✅ |
| Oddělení | číselník oddělení NOR (87 položek) | 🔴 jen ukázka (13 položek + „20 Chirurgie“) |
| sn, Klinické stádium, TNM skupina | číselníky aplikace NOR | 🔴 jen ukázkové hodnoty |

**Co je v balíčku MKN-10-CZ 2026 od ÚZIS a k čemu ho použijeme** (podle `00_MKN10_2026_popis_csv_ciselniku.docx`, NCMNK ÚZIS, úprava 4. 12. 2025):
- Všech 9 CSV je dvakrát: `cp_utf8/` a `cp_w1250/` je stejný obsah v jiném kódování. **Používáme `cp_utf8/`**, oddělovač `;`, některé soubory mají BOM (`utf-8-sig`).
- `MKN10_2026_Tabelární část.xlsx` (listy Popis, Obsah, tab1–tab4) je totéž jako CSV pro lidi; pro kód nepotřebujeme.

| Soubor | Řádků | Klíčové sloupce | Použití v AI NOR |
|---|---|---|---|
| `01_MKN10_5E_2026` | 39 297 (555 kódů C) | `KodSTeckou`, `Nazev` (≤ 70 znaků), `NazevPlny`, `NepripustnePohlavi`, `NepripustnyVekOd/Do` | **Dg. MKN + Dg. slovně**, platnost kódu. **Validace pohlaví:** `NepripustnePohlavi = 1` → kód nepřípustný u mužů (např. C53 děložní hrdlo), `2` → u žen (např. C61 prostata). Stejně věk. |
| `02_Tabelární část – seznam názvů` | 16 418 | `Kapitola`, `Oddil`, `Kod`, `NazevPlny` | hierarchie (kapitola II Novotvary, oddíly C00–C97, D00–D48) → seskupení a TNM skupina |
| `05_Abecední seznam – nemoci a poranění` | 52 782 | `Úroveň`, `Název`, `Kód` | termíny s **morfologickými kódy** `(M8140/3)`: 702 kódů → mapování názvu morfologie na kód |
| `07_Abecední seznam – novotvary` | 1 558 | `Úroveň`, `Název, specifikace, lokalizace`, kód pro **primární / sekundární / in situ / benigní / nejisté** chování | **lokalizace → kód**: z „prs, horní zevní kvadrant“ + chování primární → `C50.4`. Sloupec **sekundární** (C77–C79) mapuje **lokalizace metastáz**. Řádky jsou stromové (`Úroveň`, `– –`), název se skládá s nadřazenými řádky. |
| 03, 04, 06, 08, 09 | — | aktivity, místo události, potraty, chemikálie, vnější příčiny | nepotřebujeme |

Úplný **MKN-O-3** a číselníky **oddělení, sn, klinických stádií a TNM skupin** má aplikace NOR v menu „Číselníky“.
Vyžádat export přes Ing. Najbrtovou (otázka §10.6). Do té doby pokryjeme běžné nádory 702 kódy z rejstříku MKN-10.

**Jak AI vybere kód** (pořadí od nejjistějšího, modul `validate/codes.py`):
1. **Kód přímo v textu.** Patička histologie `M1: M85003` → `8500/3`, „Dg.: C504“ → `C50.4`. Jen se ověří v číselníku.
2. **Přesná shoda termínu s rejstříkem** (po normalizaci diakritiky, zkratek a pořadí slov): „invazivní duktální karcinom“ → `8500/3`.
3. **Sémantické vyhledání v číselníku:** názvy položek číselníků jsou jako vektory v **IRIS Vector Search** (tabulka `Nor.Code`).
   Dotaz „karcinom NST“ vrátí top 5 kandidátů a LLM **smí vybrat jen z nich**, nebo odpovědět „nelze určit“.
4. **Kontrola vztahu Diagnóza / Topografie / Morfologie** (jako tlačítko ve formuláři ÚZIS): C50.4 ↔ topografie C50.x, chování `/3` u ZN, BCC `8090/3` ↔ kůže C44.
5. **Kontrola pohlaví a věku** podle `NepripustnePohlavi` / `NepripustnyVekOd/Do` z `01_MKN10_5E` (C61 u ženy → chyba, jde ke kontrole).

6. **Druhý krok LLM nad pravidly MKN-10 (varianta B, jen Dg. MKN).** PDF `mkn-tabelarni-cast_1-4-2014_2.pdf` (Tabelární část, ÚZIS 2014)
   je rozparsované celé (`retrieval/rules.py`: 1 971 kategorií s podpoložkami, Patří sem / Nepatří sem, a 391 poznámek kapitol)
   a uložené v IRIS (`Nor.Rule`, vektory 384 dim). Kandidátní kategorie = kód z textu + hledání v `Nor.Code` + hledání v `Nor.Rule`;
   k nim vždy celé poznámky kapitoly II (např. „léze přesahující… → .8“). LLM (`extract/coder.py`) vybere **jen z podpoložek kandidátů**
   a musí **doslovně citovat pravidlo**. Backend ověří kód v CSV 2026 a citaci v textu pravidel (stránka PDF).
   Shoda s kódem z textu → +10; jiný kód než v textu → oba kódy k výběru, jistota max. 70 → ke kontrole;
   kód v textu chybí → kód z pravidel (−5). Citace pravidla se zobrazí u pole (`Extracted.rules`).

Cesta, kterou kód vznikl, se promítá do skóre jistoty (§4): krok 1 > krok 2 > krok 3. Kódy z kroku 3 obvykle skončí pod prahem a jdou ke kontrole.
Číselníky v IRIS jsou zároveň další smysluplné použití InterSystems (SQL tabulky + Vector Search nad číselníkem, nejen nad zprávami).

---

## 4. Indikátor jistoty AI 0–100 a kdy jde pole ke kontrole (požadavek organizátora)

**Princip:** jistota není „co si model myslí“, ale **skóre 0–100 složené z ověřitelných signálů**. Samohodnocení modelu má jen malou váhu,
protože bývá špatně kalibrované.

### Pravidlo kontroly
| Situace | Co se stane |
|---|---|
| Jistota **≥ 80**, žádný rozpor, citace ověřena | **Předvyplněno.** Pole je vidět s jistotou a citací a jde opravit. Lékař ho nemusí potvrzovat jednotlivě, ale vidí ho v náhledu, který potvrzuje jako celek. |
| **Rozpor** mezi dokumenty v systému (jiná hodnota stejného pole) | **Ke kontrole** vždy, bez ohledu na skóre. UI ukáže všechny verze s citacemi, uživatel vybere jednu nebo zadá vlastní. |
| Jistota **< 80** | **Ke kontrole.** Uživatel potvrdí, opraví nebo zamítne. |
| Údaj v dokumentaci **chybí** | Nejde do fronty kontroly. Zobrazí se v přehledu „Chybí v dokumentaci“. Pokud je pole povinné, hlášení je „Neúplné“ a uživatel ho může doplnit. |
| **Celé hlášení** | Až je fronta prázdná, lékař otevře **náhled hlášení** a klikne **„Potvrdit hlášení“**. Bez toho se nic neexportuje do ÚZIS ani nezapíše do FHIR. |

Práh 80 (původně 85) je nastavitelný (`AUTO_ACCEPT_THRESHOLD`) a doladí se kalibrací na gold datech (viz níže).

### Výpočet skóre (výchozí body, doladit na gold datech)
| Signál | Body |
|---|---|
| **Citace nalezena doslova** v dokumentu | povinná podmínka; bez ní je skóre max **30** a pole jde vždy ke kontrole |
| **Typ zdroje**: histologický závěr nebo patička M-kódu / MDT zápis / ambulantní či propouštěcí zpráva | základ **70 / 60 / 50** |
| **Shoda více dokumentů** se stejnou normalizovanou hodnotou | **+10** za každý další zdroj (max +20) |
| **Kód platný** v číselníku (MKN-10, MKN-O-3, číselník NOR) | **+10**; neplatný kód → max **40** |
| **Cesta ke kódu** (§3.1): kód přímo v textu / přesná shoda s rejstříkem / sémantický výběr z kandidátů / zvolen podle pravidel MKN-10 | **+10 / 0 / −15 / −5** |
| **Pravidla MKN-10** (§3.1 krok 6): potvrzují kód z textu / navrhují jiný kód / model si není jistý | **+10 / max. 70 / max. 70** |
| **Konzistence** (vztah Dg / Topografie / Morfologie, TNM ↔ stádium, pořadí dat) | porušení **−25** a varování |
| **Explicitní vs odvozené** („pT1c“ přímo v textu vs stádium dopočtené z TNM, lateralita z „l.sin.“) | odvozené **−15** (model vrací `derived: true`) |
| **Zajišťovací výrazy** v citaci („susp.“, „v.s.“, „nelze vyloučit“, „?“) | **−30** |
| Samohodnocení modelu (0–100) | ±5 |
| Rozpor | stav `conflict` → ke kontrole vždy (skóre se zobrazí, ale nerozhoduje) |

Výsledek se ořízne na 0–100.

### Zobrazení
- U každého pole **číslo 0–100** a barva: 🟢 80–100 (předvyplněno) · 🟠 60–79 · 🔴 0–59 · ⚠️ rozpor · ⚪ chybí.
- Po najetí myší se zobrazí **důvody**, např. „✓ citace ověřena · ✓ 2 zdroje se shodují · ✓ kód platný v MKN-10 · −15 odvozeno z TNM“.
- **Na úrovni hlášení:** úplnost povinných polí (např. 14/17), počet polí ke kontrole, počet předvyplněných, stav „připraveno k potvrzení“ / „potvrzeno“.
- Fronta „Ke kontrole“ obsahuje jen rozpory a pole pod prahem: nejdřív rozpory, pak podle skóre od nejnižšího.

### Kalibrace (tohle porotu přesvědčí)
Na gold datech změřit **přesnost podle pásma skóre** (např. „80–100: 97 % správně, 60–79: 80 %, 0–59: 45 %“).
Hlavně **přesnost předvyplněných polí**, protože ta lékař jednotlivě neřeší a vidí je jen v náhledu. Pokud vyjde pod 97 %, práh zvednout.
Výsledek ukázat v dashboardu jako graf spolehlivosti spolu s podílem polí, která šla ke kontrole.

**Kontrakt (už upraveno v `backend/app/models.py`):** `Extracted.confidence` je celé číslo 0–100, přibyly `confidence_reasons: list[str]`
a `needs_review: bool`, `ReviewState.auto_accepted` (= předvyplněno), `Evidence.verified`.
**Ještě upravit v kódu:** přidat potvrzení celého hlášení (`Case.confirmed_by`, `Case.confirmed_at`, endpoint `/confirm`).
`/submit` a export ÚZIS musí bez potvrzení vrátit chybu (dnes kód zapisuje předvyplněná pole hned). Provenance: verifier = lékař, který hlášení potvrdil;
u každého pole navíc tag, zda ho lékař řešil ručně, nebo převzal z předvyplnění.

---

## 5. Výstup do ÚZIS / NOR (požadavek organizátora)

NOR spravuje **ÚZIS** v rámci NZIS. FNO dnes vyplňuje formulář „Incidence zhoubného novotvaru“ ručně ve webové aplikaci NOR
(screenshot formuláře máme od FNO). **Pole, číselníky a co plní AI: [contracts/nor_form.md](contracts/nor_form.md).**

| Výstup | Obsah | Priorita |
|---|---|---|
| **Náhled hlášení** v rozložení formuláře ÚZIS | sekce Diagnostická část / Diagnóza / Morfologie / TNM / Ostatní, kódy i texty; stav Úplné / Neúplné | MVP |
| **JSON / XML hlášení NOR** | pole a kódy přesně podle formuláře a číselníků NOR (bitové součty jako čísla) | MVP |
| **CSV dávka** | víc hlášení najednou, 1 řádek = 1 hlášení (přes FHIR SQL Builder nebo přímo) | MVP+ |
| **PDF** | tisknutelné hlášení pro dokumentaci | nice-to-have |
| **Přímé odeslání do ÚZIS** | adaptér `export/uzis.py` s vyměnitelným formátem; v architektuře „bílé místo“ (jako napojení na kmenové registry) | jen v pitchi, bez specifikace ÚZIS nestavět |

- **Kontrola před odesláním** stejnými pravidly jako aplikace ÚZIS (povinná pole, vztah Dg / Topografie / Morfologie). Hlášení „Neúplné“ nejde exportovat bez potvrzení výjimky.
- **Neodhadovat formát ÚZIS.** Přesný formát importu (XML dávka podle datového rozhraní NZIS?) a verzi číselníků zjistit u Ing. Najbrtové nebo organizátora. Do té doby JSON podle polí formuláře.

---

## 6. Frontend: jak bude vypadat

React + TS + Tailwind (`frontend/`). Čeština, světlý a klidný klinický vzhled, ovládání i klávesnicí.

### Obrazovka 1: Seznam případů
```
┌ AI NOR ──────────────────────────────────────────── LLM: live · IRIS FHIR: online ┐
│ [+ Nahrát dokumenty]                                         hledat pacienta…      │
│ Pacient   Dokumenty  Dg      Úplnost  Předvypl.   Ke kontrole   Stav              │
│ PAC001    4          C18.7   17/17    17          0             k potvrzení        │
│ PAC002    4          C50.4   15/17    13          ⚠️1  🟠1      ke kontrole (2)    │
│ PAC003    4          C34.11  12/17    8           ⚠️2  🔴2      ke kontrole (4)    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Obrazovka 2: Hlášení s frontou ke kontrole (jádro dema)
```
┌ PAC002 · 4 dokumenty · Úplnost 15/17 · předvyplněno 13 · ke kontrole 2              [Náhled a potvrzení →] ┐
├──────────── Dokumenty (≈55 %) ─────────────┬────────── Hlášení NOR (≈45 %) ─────────────────────────────┤
│ [Histologie] [Amb. zpráva] [PZ] [MDT]      │ ┌ Ke kontrole (2) ─────────────────────────────────────┐ │
│                                            │ │ ⚠️ ER   95 % (Histologie, 88)  ×  90 % (MDT, 74)     │ │
│ …Mikropopis: … ▓ER 95 % pozitivní▓ …       │ │        [vybrat 95 %] [vybrat 90 %] [jiná hodnota]    │ │
│                                            │ │ 🟠 62  Datum dg.  05/2026  „…2026 CCB…“ ✓ ✎ ✗        │ │
│ …Závěr:                                    │ └──────────────────────────────────────────────────────┘ │
│ 1. typ nádoru – ▓invazivní karcinom NST▓   │ ▸ Diagnóza                                               │
│ 2. grading – ▓G2▓                          │   Dg. MKN-10    C50.4 ZN – horní zevní kvadr.  🟢 97 ✓AI │
│ …                                          │   Lateralita    vlevo                          🟢 92 ✓AI │
│ 10. pTNM – ▓pT1c pN0(sn)▓                  │ ▸ Morfologie                                             │
│                                            │   Kód           8500/3                         🟢 98 ✓AI │
│ (klik na pole → skok na citaci;            │   Grading       2                              🟢 95 ✓AI │
│  u rozporu obě citace)                     │ ▸ TNM          klinické        patologické               │
│                                            │   T            cT1c 🟢 86 ✓AI  pT1c 🟢 98 ✓AI            │
│                                            │   N            cN0  🟢 85 ✓AI  pN0(sn) 🟢 97 ✓AI         │
│                                            │ ▸ Chybí v dokumentaci: cM, pM                            │
├────────────────────────────────────────────┴──────────────────────────────────────────────────────────┤
│ ⏱ 00:41 · opravy: 0 · po vyřešení fronty → Náhled a potvrzení                                         │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
- Nahoře je **fronta „Ke kontrole“** jen s rozpory a poli pod prahem. Dokud není prázdná, tlačítko „Náhled a potvrzení“ je neaktivní.
- Pod ní je celé hlášení v **sekcích a pořadí formuláře ÚZIS**, ať je zdravotníkovi povědomé. Předvyplněná pole mají ✓AI a skóre.
  Kliknutím jde zobrazit citaci a pole opravit; jednotlivě se potvrzovat nemusí, protože je lékař uvidí v náhledu.
- **✎ úprava** = výběr z číselníku (MKN-10 s vyhledáváním, lateralita, grading, TNM), ne volný text.
- U rozporu jsou všechny verze s citací a skóre vedle sebe a uživatel vybere jednu, nebo zadá vlastní hodnotu.
- Klávesnice: `J/K` další / předchozí položka fronty, `1/2` vybrat verzi rozporu, `Enter` potvrdit, `E` upravit, `X` zamítnout.
- Lišta dole měří **čas na záznam** a **počet oprav** (posílá do `/events`).

### Obrazovka 3: Náhled a potvrzení hlášení
- Náhled celého hlášení v rozložení formuláře ÚZIS (obě strany), u každého pole hodnota, jistota a odkaz na citaci; stav **Úplné / Neúplné**.
- Lékař hlášení projde a klikne **„Potvrdit hlášení“** (zaznamená se kdo a kdy). Tlačítko „Zpět k úpravám“ vrátí na obrazovku 2.
- **Až po potvrzení** se zpřístupní stažení JSON / XML / CSV (PDF) pro ÚZIS a provede se zápis do FHIR.
- Záložka **FHIR**: seznam zapsaných zdrojů, odkaz do IRIS, Provenance („potvrdil: …, zdroj: Histologie …“).

### Obrazovka 4: Dashboard (stretch, ale silný do pitche)
- Přesnost a úplnost po polích (tabulka a graf), **kalibrace jistoty** (přesnost podle pásma), průměrný čas a opravy na hlášení, AI vs ruční postup.

---

## 7. Data a evaluace
- **Vývoj:** syntetických 10 pacientů z XLSX exportů (konzistentní, jasná pravda) + `data/synthetic/`.
- **Těžké případy:** 10 pacientů FNO (rozpor dg mezi dokumenty, ypTNM po neoadjuvanci, onkoduplicita, nesoulad identity, suspekce vs definitivní histologie, chybějící data po anonymizaci) + MDT PDF (OCR šum, relapsy, ne-ZN jako negativní kontrola).
- **Data FNO nikdy v gitu.** Gold k nim leží mimo repo. Přehled dat: `../../Rakathon_DATA_NOR/PREHLED_DAT.md` (lokálně).
- **Eval skript** `eval/run_eval.py` → `eval/report.md` + graf; spouštět jen na změny (šetřit tokeny, cache LLM).

---

## 8. Harmonogram (od teď)
| Kdy | Co | Hotovo když |
|---|---|---|
| **pá 16:30–19:00** | Live extrakce skupin ①–③ s citacemi a ověřením citací. UI: sekce formuláře, skóre 0–100 (zatím z citace a kódu), fronta ke kontrole. **Kapitán vybere výzvu AI NOR do 19:00.** | PAC001 projde celou cestou s live LLM |
| 19:00–20:00 | Večeře, **checkpoint s Ing. Najbrtovou** (ukázat, zeptat se na formát ÚZIS a povinná pole) a **s Danem Kutáčem** (IRIS architektura) | odpovědi zapsané v §10 |
| 20:00–24:00 | Číselníky do IRIS (MKN-10, morfologie z rejstříku, pevné číselníky formuláře) a výběr kódu podle §3.1. Skóre jistoty 0–100 (všechny signály), předvyplnění, detekce rozporů, náhled + „Potvrdit hlášení“, validační pravidla, stav Úplné / Neúplné, export ÚZIS JSON + náhled, IRIS Vector Search, gold pro 10 syntetických pacientů | demo scénář §1 funguje |
| 00:00–04:00 | Skupiny ④–⑦, eval a kalibrace, CSV dávka přes FHIR SQL Builder, dashboard. Spánek na směny. | čísla do pitche |
| so 07:00–10:00 | Bugfixy, data na demo, **záložní video**, README. **10:00 feature freeze.** | |
| 10:00–13:00 | Scénář dema u stolu, pitch, 3× nanečisto, **odevzdání formulářem do 13:00** (repo public!) | odevzdáno |
| 14:00 | Hodnocení u stolu: živé demo + dashboard | |

## 9. Rozdělení práce (podle složek, ať se nepřepisujeme)
| Role | Složky | Odpovídá za |
|---|---|---|
| **Backend / AI** | `backend/app/extract`, `llm.py`, `confidence.py`, `retrieval/` | extrakce, citace, skóre jistoty |
| **FHIR / IRIS / ÚZIS** | `backend/app/fhir`, `export/`, `validate/`, `infra/` | FHIR bundle, export ÚZIS, číselníky, pravidla, Vector Search, SQL Builder |
| **Frontend** | `frontend/` | obrazovky 1–4, fronta ke kontrole, klávesnice, měření času a oprav |
| **Klinik / eval / pitch** | `eval/`, gold mimo repo, pitch | gold data, eval, otázky na FNO, scénář dema |

Kontrakt (`contracts/`) se mění jen po domluvě. Merge na `main` každé 1–2 h, před merge `pytest -q` a `npm run build`.

## 10. Otevřené otázky (FNO / organizátor)
1. **Formát výstupu do ÚZIS**: import XML dávkou (které datové rozhraní / verze)? Nebo stačí strukturovaný výstup pro ruční vložení?
2. Která pole formuláře jsou **povinná** pro stav „Úplné“?
3. Číselníky NOR: lateralita, grading, „Onemocnění“, oddělení (kódy a verze), edice TNM (UICC 8?).
4. Stačí FNO, že lékař jednotlivě řeší jen rozpory a pole pod 80 a zbytek potvrdí v náhledu celého hlášení? Má chybějící povinné pole jít také ke kontrole?
5. Kolik minut dnes trvá jedno hlášení a kolik jich FNO ročně podává (číslo do pitche)?
6. Celé číselníky: **MKN-O-3** (morfologie a topografie), **oddělení** (87 položek), **sn**, **klinické stádium**, **TNM skupina**. Jde je vyexportovat z menu „Číselníky“ v aplikaci NOR? Co dělá menu **„Vytěžování“** v aplikaci NOR? Máme řešit i **Hlášení relapsu**?

## 11. Co neděláme
OAuth a správa uživatelů · skutečné odeslání do ÚZIS · OCR skenů (máme text) · editace zdrojových dokumentů ·
MDT shrnutí (jen pokud zbude čas po 04:00).
