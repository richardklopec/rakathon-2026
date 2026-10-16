# InterSystems, FHIR a IRIS — vše pro AI NOR

> Stav 16. 10. 2026. Zdroje: stránka výzvy InterSystems, přednáška Hoferka (přepis ElevenLabs, #02-dotazy), FHIR AI Hackathon Kit (`skills/`, `Tutorials/`), HL7 EU Common Cancer Model 1.0.0-ballot, mCODE STU4, HL7 CZ Core 1.1.0.

## 1. Výzva InterSystems (1 500 €)
- **Název:** Best Use of InterSystems Technology for AI and Interoperability. Lze ji **kombinovat s libovolnou jinou výzvou** (tedy s AI NOR).
- **Technologie:** IRIS for Health · FHIR server · Vector Search · agenti / MCP · IntegratedML (AutoML v SQL) · libovolná kombinace.
- **Kritéria:** Innovation · Real-world impact · **Use of InterSystems technology** · **Technical coherence**. Hledají: jasně definovaný zdravotnický problém, chytré použití AI a/nebo FHIR, **dobře navržený datový model a architekturu**, realistickou cestu k MVP/startupu a jasně vysvětlený dopad.
- **Co řekl Hoferek (přepis):**
  - Interoperabilitu přes FHIR server berou jako **„ještě důležitější“** část hodnocení. FHIR server v kitu = simulace napojení na nemocnici.
  - Data od zadavatele je dobré **převést do FHIR**. Výsledky publikovat do FHIR = plus.
  - FHIR server smí být i **primární databáze** aplikace.
  - Vítězové dřív: promyšlená reprezentace ve FHIR, „co všechno je interoperabilní“, dopad a **něco navíc nad zadání**.
  - **FHIR od první hodiny**, ne „nice to have na později“. Keep it simple — žádné OAuth.
- **Mentoři:** Ostrava **Daniel Kutáč** (na místě), Praha Hoferek + Gabriel, Brno Radek Zájem / Daniel Drozdov; v noci online 24/7. Slack `#best-use-of-intersystems-technology-for-ai-and-fhir`, `#08-tech-helpdesk`.
- **Bonus:** Caelestinus (inkubátor s InterSystems, 3 měsíce online, divoká karta pro 1+ tým) a InterSystems Ventures (granty).
- **FN Ostrava používá IRIS pro integrace** → řešení nad IRIS FHIR = realistická cesta do provozu u zadavatele.

## 2. Lokální prostředí (kit)
| Co | Hodnota |
|---|---|
| Start | `.\docker-iris-fhir\start.ps1` (PowerShell) — build image, FHIR server, nahraje Synthea data |
| Kontejner | `iris-fhir` (compose service `iris`), data ve volume `iris-data` |
| FHIR base | `http://localhost:52773/fhir/r4/` · Basic auth `SuperUser` / `SYS` |
| Ověření | `GET /fhir/r4/metadata` → 200 |
| Swagger | `http://localhost:52773/fhir/swagger-ui/index.html` |
| Management Portal | `http://localhost:52773/csp/sys/UtilHome.csp` |
| FHIR management (+ SQL Builder) | `http://localhost:52773/csp/fhir-management/home` |
| SQL (Python `import iris`) | `localhost:1972`, namespace `FHIRSERVER` |
| Python | `.venv` v kitu už existuje (PyMuPDF, fhir.resources, fhirpy, fastmcp, langchain) |

Nástrahy:
- Opakovaný `start.ps1` na existujícím volume **znovu nahraje Synthea data → duplicity**. Čistý stav: `docker compose down -v`. Pro AI NOR ukázková data smazat nebo založit nový FHIR server.
- FHIR server je **R4** (`hl7.fhir.r4.core@4.0.1`), úložiště JSON.
- Neznámé search parametry server **tiše ignoruje** (vrátí vše).
- Community Edition má **malý limit spojení** → vždy `cursor.close(); conn.close()`.
- `fhir.resources`: posílat `data=model.model_dump_json()`, ne `json=` (datumy).
- Odkazy musí být `Patient/123`, holé `123` server odmítne. Chyba validace = 400 + `OperationOutcome`.
- V transakci nové zdroje odkazovat přes `urn:uuid:…` (fullUrl); server přepíše na reálná ID. Jedna chyba = nic se neuloží (to chceme).
- Proti duplicitám: `PUT Patient?identifier=…` nebo `ifNoneExist`.
- Embeddingy v kitu: OpenAI `text-embedding-3-small` (1536). **My máme jen gateway** → ověřit, zda je tam embedding deployment (`-dz-eu`); jinak lokální embedding model a upravit dimenzi `VECTOR(DOUBLE, n)`.
- VZP výzvy mají IRIS i v Azure (pro nás nepodstatné, jedeme lokálně).

## 3. Co z IRIS použít v AI NOR (a proč to boduje)
| Schopnost IRIS | Použití v AI NOR | Kritérium |
|---|---|---|
| **FHIR server** | Zdrojové zprávy jako `DocumentReference`; potvrzené hlášení jako **transakční Bundle** (Condition, Observation TNM/grade/markery, Procedure, MedicationAdministration) | interoperabilita, datový model |
| **Provenance** | Ke každému potvrzenému údaji: kdo potvrdil, kdy, z jakého dokumentu + citace (offset) → „každý údaj dohledatelný“ | důvěra, technická ucelenost |
| **Vector Search (SQL `VECTOR`, `VECTOR_COSINE`)** | Chunky zpráv → vyhledání pasáží pro každou skupinu polí → citace; filtr `WHERE PatientId = ?` + vektor | AI |
| **SQL tabulky** | Číselníky: MKN-10 CSV (`01_MKN10_5E_2026_utf8.csv`), MKN-O morfologie, číselníky formuláře NOR → validace kódů a „Dg. slovně“ | AI + determinismus |
| **FHIR SQL Builder** | Projekce potvrzených Condition/Observation do SQL → **export NOR** (CSV) + statistika úplnosti | něco navíc |
| **Agent tools / MCP (FastMCP)** | Nástroje `search_chunks`, `lookup_mkn10`, `fhir_query`; volitelně MCP server „NOR asistent“ nad IRIS | agentic |
| IntegratedML | nepotřebujeme (případně jen „riziko chybějícího pole“ — nedělat) | — |

Pitch věta: *„Zprávy z NIS → FHIR (DocumentReference) → AI vytěží → lékař potvrdí → FHIR Condition/Observation/Procedure + Provenance v IRIS → NOR export přes FHIR SQL Builder. Stejná platforma, kterou FNO už pro integrace používá.“*

## 4. FHIR datový model pro hlášení NOR
Common Cancer Model (EU) zatím definuje hlavně **logické modely** (CancerConditionAtDiagnosis, CancerStage clinical/pathological, Surgery, Radiotherapy, SystemicTreatment, ClinicalCancerProgression, LastFollowUp…). FHIR profily jsou zatím jen Patient a Comorbidity. Proto (dle rady Kružíka a Chattyho) **FHIR resources podle mCODE STU4**, pojmenování a struktura podle CCM, české identifikátory a MKN-10 podle CZ Core.

### Identifikátory a kódové systémy (CZ)
| Co | system |
|---|---|
| MKN-10 | `https://uzis.cz/terminology/CodeSystem/mkn-10` (CZ Core příklad; ValueSet `https://ncez.mzcr.cz/terminology/ValueSet/condition-cz`) |
| Rodné číslo | `https://ncez.mzcr.cz/fhir/sid/rcis` |
| Resortní ID pacienta (kmenový registr) | `https://ncez.mzcr.cz/fhir/sid/rid` → „bílé místo“ pro ověření proti registru |
| Zdravotnický pracovník (KRZP) | `https://ncez.mzcr.cz/fhir/sid/krzp` |
| ICD-O-3 (morfologie i topografie) | `http://terminology.hl7.org/CodeSystem/icd-o-3` |
| SNOMED CT (volitelně) | `http://snomed.info/sct` |
| Profily CZ | `https://hl7.cz/fhir/core/StructureDefinition/{cz-patient-core, condition-cz-core, cz-provenance}` |

### Mapování polí formuláře NOR → FHIR
| Pole NOR | FHIR (profil mCODE) | Kód / hodnota |
|---|---|---|
| Pacient (RČ, bydliště) | `Patient` (CZ core) | identifier `rcis` |
| Dg. MKN + Dg. slovně | `Condition` = **mcode-primary-cancer-condition** · `code` | MKN-10 (`C50.4`) |
| Datum stanovení dg. | `Condition.onsetDateTime` (nebo `recordedDate`) | přesnost rok/měsíc/den |
| Topografie | `Condition.bodySite` | ICD-O-3 topografie (`C50.4`) |
| Lateralita | `Condition.bodySite.extension:lateralityQualifier` | SNOMED `7771000` vlevo, `24028007` vpravo, `51440002` oboustranně, `399488007` střed; „odpadá“ = bez extenze |
| Kód + název morfologie | `Condition.extension:histologyMorphologyBehavior` | ICD-O-3 `8140/3` |
| Grading | `Observation` = **mcode-histologic-grade** (code NCIt `C18000`) | G1–G4, X, 9 |
| K dg. vedla vyšetření (bitmask) | `Condition.evidence.code` (víc hodnot) | klinické / markery / cytologie / histologie metastázy / histologie primáru |
| cT / cN / cM | `Observation` **tnm-primary-tumor / regional-nodes / distant-metastases-category** | code SNOMED `399504009` cT, `399534004` cN, `399387003` cM |
| pT / pN / pM (+ y prefix) | totéž, patologické | `384625004` pT, `371494008` pN, `371497001` pM; ypTNM = prefix ve value / poznámka |
| Klinické stádium (skupina) | `Observation` **tnm-stage-group** | `399537006` klinické / `399588009` patologické; `method` UICC (NCIt `C188404`) nebo AJCC 8 (`897275008`) |
| Lokalizace vzdálených metastáz (bitmask) | `Condition` = **mcode-secondary-cancer-condition** (1 za orgán), `bodySite` | MKN-10 C77–C79 / ICD-O-3 topografie |
| Biomarkery (ER, PR, HER2, Ki-67, PD-L1, p16, MSI) | `Observation` = **mcode-tumor-marker-test** | LOINC; `relatedCondition` na primár |
| Operace | `Procedure` = **mcode-cancer-related-surgical-procedure** | text + datum (+ SNOMED volitelně), `reasonReference` → Condition |
| Radioterapie | `Procedure` = **mcode-radiotherapy-course-summary** (code SNOMED `1217123003`) | dávka, frakce, období |
| Systémová léčba (CHT, HT, imuno) | `MedicationAdministration` / `MedicationRequest` = **mcode-cancer-related-medication-*** | ATC; intent (neoadj./adj./paliativní) |
| Recidiva / progrese / „Onemocnění“ | `Observation` = **mcode-cancer-disease-status** (LOINC `97509-4`) | stav + datum + typ důkazu |
| Zdroj údaje | `DocumentReference` (zpráva) + `Provenance` (target = vytvořené zdroje, entity = dokument, agent = lékař/AI) | citace + offsety |
| Hlášení jako celek | `Bundle` type `transaction` (zápis); volitelně `Composition` „Hlášení NOR“ | stav Úplné/Neúplné |

Pozn.: přesné LOINC kódy markerů, číselník gradingu a výběr TNM edice ověřit u FNO / v datovém slovníku. Nepřidávat zbytečné detaily (rada Hoferka: řešit jen to, co se ukáže v demu).

## 5. Minimální implementační kroky (pro tým)
1. `start.ps1`, ověřit `/metadata`; smazat Synthea data (`down -v` + nový server nebo prázdný namespace).
2. Načíst dokumenty pacienta → `DocumentReference` (base64 text, `subject` → Patient).
3. Chunky + embeddingy → tabulka `Nor.Chunk(DocRef, PatientId, Start, End, Text, Embedding VECTOR)`.
4. Extrakce po skupinách polí (retrieval z IRIS → LLM `-dz-eu`) → JSON s citacemi.
5. Validace kódů přes SQL tabulku MKN-10.
6. Po potvrzení: `Bundle` (Condition + Observations + Procedures + Provenance) → `POST /fhir/r4/`.
7. FHIR SQL Builder projekce → `SELECT … ` → CSV export NOR + dashboard úplnosti.
8. (Stretch) FastMCP server nad stejnými nástroji → „zeptej se registru“ nebo MDT shrnutí.

## 6. Učební materiály (ze stránky výzvy)
Kit walkthrough video, „What is FHIR“ (1 min), „Concept of FHIR“ (23 min), „HL7 FHIR Specification“ (15 min), RAG (11 min), MCP (9 min). Kit tutoriály: 3.1–3.5 (FHIR), 4.1 (vector), 5.1 (agenti), 5.2 (MCP).
