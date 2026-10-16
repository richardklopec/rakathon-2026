# AI NOR — brief (jen to, co potřebujeme)

> Výzva 4, zadavatel **FN Ostrava**. Hackování pá 14:00 → so 13:00 (odevzdání), od 14:00 hodnocení u stolu, 17:00 vyhlášení v Ostravě.
> Plný plán: [RAKATHON_PLAN.md](RAKATHON_PLAN.md) · všechny poznámky: [PREHACK_POZNAMKY.md](PREHACK_POZNAMKY.md) · InterSystems/FHIR: [INTERSYSTEMS_FHIR.md](INTERSYSTEMS_FHIR.md)

## ✅ Rozhodnutí (16. 10. 2026)
**Bereme výzvu 4. AI NOR (FN Ostrava) + výzvu InterSystems „Best Use of InterSystems Technology for AI and Interoperability“ (1 500 €).**
- Obě výzvy jdou kombinovat; řešení postavíme na **InterSystems IRIS for Health**: FHIR server (vstupní zprávy i potvrzené hlášení jako FHIR + Provenance), Vector Search (citace zdrojů), SQL (číselníky MKN-10), FHIR SQL Builder (export NOR).
- Kapitán: vybrat na https://submit.rakathon.cz/vyzvy/vybrat výzvu **AI NOR** do 16. 10. 19:00 (InterSystems výzva se nevybírá formulářem — hodnotí se napříč výzvami).

## Zadání
> Automatizujte jednu z nejnáročnějších částí onkologické administrativy. AI nástroj vytěží z klinické dokumentace **diagnózu, stadium, TNM, morfologii, biomarkery, výkony, léčbu i průběh onemocnění**, připraví je pro registr v jednotné podobě a umožní **rychlou kontrolu zdravotníkem**.

## Proč to dává smysl (argumenty z pre-hack day)
- **Opatřil**: lékaři píšou volný text; strukturovaná data jsou přesnější, ale *„nesmíte je ubít tím, že těch strukturovaných dat bude moc"* → AI z narativu udělá strukturu. Jeho slide 19 přímo: **„vytěžování zpráv s citací zdroje, lidským potvrzením a validací"** a **„podklady pro NOR"**.
- **Chatty**: *„Co když nemocnice má jen PDF?"* → je potřeba vlastní **„transformátor"**, který data vezme a převede do standardizovaného (EHDS/FHIR) formátu. AI NOR je přesně tohle.
- **FN Ostrava sama používá InterSystems pro integrace** (Hoferek) → řešení nad IRIS FHIR = reálná cesta k nasazení u zadavatele.
- NOR = sekundární využití dat (EHDS) — jedna věta do pitche, ne víc.

## Z pátečních slidů zadavatelky (Ing. Magdaléna Najbrtová, FNO)
*Zdroj: Google Drive „Prezentace/Ostrava/4 - FN Ostrava – AI NOR.pptx“, odkaz v #01-oznameni 16. 10. 11:43.*
- **Pole, která má nástroj najít**: datum stanovení dg., diagnóza a lokalizace (MKN-10), lokalizace primárního nádoru, lateralita, histologický typ, kód morfologie, grading, TNM, klinické stadium, metastázy, systémová léčba, radioterapie, recidiva/progrese.
- **Požadovaný workflow**: (1) vstup = anonymizovaná dokumentace → (2) vyhledání informací v českém textu → (3) extrakce → (4) přiřazení k položkám formuláře → (5) **dohledání zdroje** (propojení s místem v textu) → (6) zdravotník potvrdí/upraví → (7) vyplněný formulář odpovídající registru.
- **Data od FNO**: modeloví pacienti — onkologické ambulantní zprávy, výsledky histologie, propouštěcí zprávy; **ukázka onkologického hlášení**; **datový slovník (MKN-10)**. Data v Ostravě rozdává mentorka osobně v místnosti mentorů (#01-oznameni 16. 10. 12:30); do #ai-nor zatím nic nepřišlo.
- **Hodnoticí kritéria zadavatele** (= naše eval tabulka): přesnost vytěžení vs reference · úplnost (povinné položky vyplněné nebo označené jako chybějící) · správné pole NOR · dohledatelnost zdroje · počet oprav uživatelem · čas na záznam vs ručně.
- **Konkurence**: na submit.rakathon.cz/vyzvy (16. 10. 14:32) AI NOR v Ostravě **nemá žádný tým**. Výzvu musí kapitán vybrat do **16. 10. 19:00**.

## Co zjistit v pátek dopoledne od mentora FNO
1. Data: dostaneme anonymizované zprávy? Smíme je poslat do cloudového LLM (EU)? *(Jinak jen syntetika.)*
2. **Přesný seznam polí hlášení NOR** a číselníky.
3. Z jakých dokumentů se hlášení dnes vyplňuje (propouštěcí zpráva, histologie, MDT zápis, operační protokol…).
4. **Kolik času hlášení zabere a kolik jich FNO ročně dělá** → číslo do pitche.
5. Nejčastější chyby / chybějící údaje.
6. Můžeme v sobotu ráno nechat klinika prototyp vyzkoušet?

## Datový model (cíl extrakce)
Pole NOR (ověřit u FNO) → HL7 EU **Common Cancer Model** / **mCODE** → FHIR R4:

| Údaj | Kód / číselník | Common Cancer Model | FHIR |
|---|---|---|---|
| Diagnóza, lokalizace, lateralita, datum dg. | MKN-10 | CancerConditionAtDiagnosis | Condition |
| Morfologie, grading | MKN-O-3 | CancerConditionAtDiagnosis | Condition / Observation |
| Stadium, **cTNM vs pTNM (vs ypTNM)** | TNM | **CancerStage** (klinické / patologické) | Observation (+ components T, N, M) |
| Biomarkery (HER2, ER/PR, PD-L1, EGFR…) | — | (mCODE tumor markers) | Observation |
| Operace | výkony | Surgery | Procedure |
| Radioterapie | — | Radiotherapy | Procedure |
| Systémová léčba (CHT, hormon., bio) | ATC | SystemicTreatment | MedicationAdministration / Procedure |
| Průběh / odpověď / follow-up | — | ClinicalCancerProgression, OverallCancerTreatmentResponse, LastFollowUp | Observation |

- Vzor: Common Cancer Model má **kompletní ukázkový případ karcinomu plic** (diagnóza, cTNM, pTNM, operace, RT, CHT, progrese, follow-upy) → https://hl7.eu/fhir/cancer-common/artifacts.html
- Terminologie: **MKN-10 povinně**, SNOMED jen volitelně (v ČR málo známý).

## Architektura (MVP)
```
zprávy (PDF/DOCX/TXT)
 → ingest (text + offsety)
 → IRIS Vector Search (chunky) → najdi pasáže pro každou skupinu polí
 → LLM (gateway, deployment -dz-eu), structured output: hodnota + kód + CITACE + confidence
 → validace pravidly (TNM ↔ stadium, pořadí dat, negace, číselníky) → ⚠ flagy
 → review UI: vlevo dokument se zvýrazněnou citací, vpravo pole ✓ / ✎ / ✗
 → po potvrzení: transakční FHIR Bundle → IRIS FHIR server
 → export NOR (JSON/CSV, přes FHIR SQL Builder nebo vlastní mapování) + audit
```
**Musí platit:** každé pole má citaci nebo je „chybí"; nic se neodesílá bez potvrzení lékařem; chybějící ≠ negativní.

## Technika
- **InterSystems FHIR AI Hackathon Kit** (docker → IRIS + FHIR R4): https://github.com/intersystems-community/FHIR-AI-Hackathon-Kit — notebooky **3.1–3.4** (FHIR load/search/create/**transaction Bundle**), **4.1** (Vector Search), FHIR SQL Builder. Ukázková data ve FHIR serveru smazat.
- **LLM**: `https://apim-rakathon-q7146n.azure-api.net/openai/v1/`, hlavička `api-key`, model = název deploymentu (např. `gpt-6-1-sol-dz-eu`). ~4 M tokenů/tým/den → cache, žádné retry smyčky, 429 → backoff.
- **Rady InterSystems**: FHIR **od první hodiny**; *keep it simple* (žádné OAuth). Mentor v Ostravě: **Daniel Kutáč**; online mentoři pá 20–24 (Henry Hamon Pereira), so 0–4 (Jose Roberto Pereira), so 4–8 (Semen Makarov). Slack: #best-use-of-intersystems-technology-for-ai-and-fhir, #08-tech-helpdesk.
- **Slidy InterSystems workshopu** (Slack, kanál InterSystems): AI NOR řadí do kategorie **„Zapsat do databáze — validace / FHIR / API"** (spolu s PillGaze, ProstaPaper). Doporučení: *„FHIR na vstupu i výstupu, vlastní datový model možný uvnitř řešení"*, **FHIR server jako hlavní datové úložiště**, **Provenance** zaznamená původ strukturovaného výstupu (→ citace zdroje u každého pole). Pozor: *„Kód od agentů vyžaduje testy a kontrolu."*

## Testovací data a evaluace
- Syntetické české zprávy generované LLM + **gold JSON** ke každé (styl: zkratky st.p., l.dx., susp., neg.).
- **Záludné případy** (Tichopád „chyba extrakce" + naše): negace („bez známek meta"), starý vs aktuální termín, **cTNM vs pTNM**, rozpor mezi dokumenty, chybějící údaj.
- Eval: přesnost / úplnost po polích → tabulka do pitche.

## Pravidla, která nás omezují
- Data k výzvě přijdou do Slack kanálu **#ai-nor nejpozději se startem hackování**.
- **Cloudové LLM jen se souhlasem FNO** (anonymní/syntetická data). Reálná data nikdy do Claude Code / Copilot promptů.
- Předpřipravený kód jen **deklarovaný**; hodnotí se práce během akce.
- Demo stačí z lokálu; nahrát **záložní video**.

## Co ocení porota (a co jim ukázat)
| Kdo | Co chce vidět |
|---|---|
| FNO (zadavatel) | úsporu času, spolehlivost, lékař má kontrolu, zapadne do jejich prostředí |
| InterSystems (1 500 €) | promyšlená FHIR reprezentace, IRIS FHIR + vector search smysluplně, technická ucelenost, **něco navíc nad zadání** |
| FEI VŠB-TUO (technika) | funkční, čistá architektura, testy, eval, README |
| Všichni | živé demo end-to-end, číslo dopadu, přiznané limity |

**„Něco navíc"**: detekce rozporů mezi dokumenty, upozornění na chybějící údaje pro NOR, eval dashboard, (stretch) MDT shrnutí ze stejných dat.

## Relevantní místa v záznamech pre-hack day
Rozsahy = pozice ve stažených souborech v `Downloads` (přesnost ±30 s). Tučně = nejdůležitější pro AI NOR. Ve Zoom odkazu v prohlížeči můžou být časy posunuté.

**Dopoledne — `GMT20261015-072521_Recording_2560x1440.mp4`** (záznam začíná 9:25)

| Rozsah ve videu | Reálný čas | Kdo | Co | Proč pro nás |
|---|---|---|---|---|
| 01:00:41–01:30:50 | 10:26–10:56 | Opatřil | celá přednáška České eHealth | — |
| **01:11:06–01:15:28** | 10:36–10:40 | Opatřil | EHDS, EHR, **narativ vs strukturovaná data, AI z narativu dělá strukturu** | hlavní argument AI NOR do pitche |
| 01:16:51–01:19:01 | 10:42–10:44 | Opatřil | kmenové registry, duplicity pacientů | identita pacienta = napojovací místo v architektuře |
| 01:24:01–01:25:10 | 10:49–10:50 | Opatřil | terminologie: MKN-10, NČLP, SNOMED | jaké kódy použít |
| 01:30:55–02:11:49 | 10:56–11:37 | Kružík | celá přednáška HL7 FHIR + Q&A | — |
| **01:44:22–01:51:21** | 11:09–11:16 | Kružík | **European Common Cancer Model** (konceptuální a logický model) | cílové schéma extrakce |
| **01:51:21–01:52:53** | 11:16–11:18 | Kružík | **CancerStage — TNM klinické vs patologické** | nejtěžší pole NOR |
| 01:52:53–01:57:18 | 11:18–11:22 | Kružík | mapování na FHIR a OMOP, SNOMED v CZ profilech | sekundární využití / kódy |
| **02:08:10–02:11:03** | 11:33–11:36 | Kružík | **rada pro 24h prototyp: stavební bloky FHIR + terminologie, pre-/post-koordinace** | jak navrhnout datový model |

**Odpoledne — `GMT20261015-105031_Recording_2560x1440.mp4`** (záznam začíná 12:50)

| Rozsah ve videu | Reálný čas | Kdo | Co | Proč pro nás |
|---|---|---|---|---|
| 00:23:47–00:24:37 | 13:14–13:15 | Microsoft | data k výzvám přijdou nejpozději se startem hackování | kdy čekat data |
| 00:34:41–00:36:12 | 13:25–13:26 | Studeník | předpřipravený kód jen s deklarací, submissions veřejné | pravidla |
| 00:47:19–00:48:01 | 13:37–13:38 | Microsoft | rate limit 429 → exponential backoff | implementace LLM klienta |
| 01:07:41–01:09:12 | 13:58–13:59 | Microsoft | použití Azure neovlivňuje hodnocení | demo může běžet lokálně |
| 01:11:31–02:09:50 | 14:02–15:00 | Hoferek | celá přednáška InterSystems + Q&A | — |
| **01:14:50–01:15:40** | 14:05–14:06 | Hoferek | **FN Ostrava používá InterSystems pro integrace** | argument pro IRIS u zadavatele |
| 01:25:45–01:27:00 | 14:16–14:17 | Hoferek | největší překážka nasazení = napojení na NIS → FHIR | proč FHIR |
| **01:34:22–01:35:39** | 14:24–14:26 | Hoferek | **FHIR server pro hackathon = simulace interoperability** | co ukázat porotě |
| 01:37:35–01:42:18 | 14:28–14:32 | Hoferek | Hackathon Kit, notebooky, CSV → IRIS | setup |
| 01:42:18–01:53:28 | 14:32–14:43 | Hoferek | FHIR: nahrání, vyhledávání, vytváření resources | práce s FHIR serverem |
| 01:53:28–01:55:47 | 14:43–14:46 | Hoferek | transakční Bundle | uložení hlášení jako 1 transakce |
| **01:55:47–01:56:36** | 14:46–14:47 | Hoferek | **FHIR SQL Builder (FHIR → SQL)** | export do NOR |
| 01:56:36–01:58:13 | 14:47–14:48 | Hoferek | Vector Search v IRIS, embeddingy, chunking | citace zdrojů |
| 01:58:13–02:00:30 | 14:48–14:51 | Hoferek | agent tools + MCP server | volitelně |
| **02:04:30–02:06:04** | 14:55–14:56 | Hoferek | **FHIR od začátku, keep it simple** | postup |
| **02:07:05–02:08:14** | 14:57–14:58 | Hoferek | **co přesvědčilo porotu u minulých vítězů** | strategie |
| 02:08:19–02:09:45 | 14:58–15:00 | Hoferek | cloudové LLM jen u anonymních dat, jinak lokální | otázka na FNO |
| 02:12:18–02:47:14 | 15:02–15:37 | Chatty | celá přednáška FHIR & PHOENIX (anglicky) | — |
| 02:24:04–02:25:00 | 15:14–15:15 | Chatty | SYNDERAI: ~237 synt. pacientů, propouštěcí zprávy, lab reporty | zdroj testovacích dat |
| 02:29:49–02:32:56 | 15:20–15:23 | Chatty | Common Cancer Model, „v prototypu se držte FHIR resources", mCODE | datový model |
| 02:37:44–02:38:46 | 15:28–15:29 | Chatty | kódy ne text, původ dat, testovat na syntetice | zásady návrhu |
| **02:43:19–02:44:36** | 15:33–15:35 | Chatty | **nemocnice mají jen PDF → potřebujete „transformátor" do standardního formátu** | **argument pro AI NOR do pitche** |
| 02:49:43–02:51:00 | 15:40–15:41 | Studeník | porota čeká vyšší kvalitu díky AI | laťka |

**Tichopád (dopoledne, celé 0:03–0:57)** — hlavně koordinace péče, pro AI NOR jen okrajově:
| Rozsah ve videu | Reálný čas | Co | Proč pro nás |
|---|---|---|---|
| 0:24:27–0:26:30 | 9:50–9:52 | trajektorie pacienta = diskrétní události z vykázané péče a NIS | časová osa léčby (průběh onemocnění v NOR) |
| 0:27:14–0:31:00 | 9:52–9:56 | diagnostika → histologické potvrzení → MDT (zápis jako právní akt) | odkud se berou dg., histologie, plán léčby |
| 0:44:03–0:44:40 | 10:09–10:10 | sledovat, zda proběhlo prediktivní testování (PD-L1) | biomarkery jako pole NOR |
| 0:50:21–0:57:00 | 10:15–10:22 | Q&A: předávání dokumentace mezi nemocnicemi → HL7 FHIR | argument pro FHIR výstup |

## Pitch (3–5 min)
1. Příběh: lékař přepisuje z 5 zpráv údaje do registru — **číslo od FNO**.
2. Demo: nahrát zprávy → vyplněné hlášení → klik = citace → ⚠ rozpor TNM → oprava → potvrzení → FHIR v IRIS → export NOR.
3. Důvěra: eval čísla, citace, lékař potvrzuje, EU-only zpracování, Common Cancer Model / FHIR.
4. Dopad + další krok: úspora × počet hlášení; pilot ve FNO nad jejich InterSystems integrací.
