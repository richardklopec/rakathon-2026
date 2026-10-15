# Rakathon 2026 — poznámky z Pre-hack Day (15. 10.)

> Zdroj: Zoom záznamy (titulky `.cc.vtt` + lokální přepis Whisper), slidy ze Slacku #01-oznameni, chat ze Zoomu.
> Co z toho plyne pro náš plán → [RAKATHON_PLAN.md](RAKATHON_PLAN.md).

| Čas | Přednáška | Zdroj poznámek |
|---|---|---|
| 9:30 | Aleš Tichopád — Cesta onkologického pacienta | slidy (52) + přepis z audia ✅ |
| 10:30 | Michal Opatřil — České eHealth v kostce | slidy + titulky ✅ |
| 11:00 | Hynek Kružík — HL7 FHIR a Common Cancer Model | slidy + poznámky řečníka + titulky ✅ |
| 13:00 | Microsoft (Marušan) — co máte k dispozici | průvodce + slidy + titulky ✅ |
| 14:30 | Ondřej Hoferek — InterSystems | stránka výzvy + Hackathon Kit + titulky + slidy workshopu (Slack) ✅ |
| 15:30 | Luc Chatty — FHIR & PHOENIX | slidy + přepis z audia ✅ |

---

## TL;DR — 10 věcí, které si zapamatovat
1. **Data k výzvám přijdou do Slack kanálů výzev nejpozději se startem hackování** (pá po dopoledním bloku).
2. **FN Ostrava používá InterSystems pro integrace** → AI NOR nad IRIS FHIR = reálná cesta do provozu u zadavatele.
3. **AI převod volného textu → struktura** je přesně to, co Opatřil doporučil zkoušet; lékaře nezahlcovat strukturovanými poli.
4. **FHIR od první hodiny**, ne „až na konci" (InterSystems: týmy, které to odložily, to už nenapasovaly). *Keep it simple* — žádné OAuth.
5. Porota InterSystems dřív oceňovala: promyšlenou reprezentaci dat ve FHIR, interoperabilitu, dopad a **„něco navíc, co v zadání nebylo"**.
6. **Předpřipravený kód smíte použít, ale musíte ho deklarovat**; hodnotí se jen to, co vzniklo během akce. Submissions budou veřejné.
7. **Demo stačí z lokálu.** Azure/InterSystems neovlivňují hodnocení výzev — jen jejich vlastní ceny.
8. **Cloudové LLM jen pokud zadavatel potvrdí anonymní/syntetická data**; jinak lokální model (nedodávají).
9. Kvóty: LLM gateway ~4 M tokenů/tým/den, Azure ~100–200 USD/tým, GPU VM zakázané, Copilot ~100 USD/osobu.
10. **Porota kvůli AI agentům čeká vyšší kvalitu než dřív.** V neděli hlasují i hackeři.

---

## 1. Aleš Tichopád — Cesta onkologického pacienta (ČVUT Health Data Lab)
*Ze slidů + přepisu z audia (Whisper). Záznam dopoledne ~0:03–0:57.*
- **Z přednášky (přepis)**:
  - 0:04–0:18 — biologie rakoviny: histologie jako první milník; vzorek tkáně „cestuje" mezi pracovišti a může se ztratit; výsledky často chodí poštou/na CD; prekancerózy a **screening** (střevo, prs, Barrett); klonální evoluce → léčba musí být rychlá a koordinovaná.
  - 0:24–0:27 — **klinická trajektorie = posloupnost diskrétních událostí z vykázané péče a z NIS**; některé jsou milníky, jiné šum (návštěvy nesouvisející s nádorem).
  - 0:27–0:31 — fáze: příznaky → vstup do systému a suspekce → diagnostika s histologickým potvrzením → **MDT** (je to „právní akt", měl by mít zápis — v praxi často jen telefonát) → léčba a bariéry (kapacity center, čekání, pacient „spadne" o stadium).
  - 0:35–0:38 — koordinace: úkol, vlastník, termín, potvrzení převzetí, eskalace; pacienti často 70+ let, kognitivně slabší, bez smartphonu.
  - 0:38–0:44 — karcinom plic: opakované bronchoskopie (2–4×), 40 % čeká na operaci > 8 týdnů, heterogenita mezi nemocnicemi (MDT vykázané/nevykázané); **sledovat, zda proběhlo prediktivní testování (PD-L1) před rozhodnutím o léčbě**.
  - 0:44–0:48 — algoritmy péče v NIS; koordinátor často není lékař → proces musí být v systému; RL na rozhodování KOC vs regionální centrum.
  - 0:50–0:57 — Q&A: **Šárka Fajtlová (NOC Brno)**: nejpalčivější je bezpečné předávání dokumentace mezi institucemi (různé NIS, GDPR). Odpověď: výměna má jít přes **HL7 FHIR** a národní infrastrukturu; nástroje pro koordinátory mají být napojené na NIS. **Tichopád bude v pátek k dispozici** (Praha/Motol, kontakt přes Slack).
- **Patient pathway** (klinická trajektorie) vs **patient journey** (prožitek pacienta). 7 kroků: prevence/záchyt → první projevy a odeslání → diagnóza, staging, plán → léčba → následná péče → recidiva/metastázy → konec života.
- **Pojmy, které software musí rozlišovat**: suspekce vs potvrzený nádor, histologie a staging, MDT, remise vs recidiva, KOC vs regionální péče.
- **Data plátců vyprávějí příběh pacienta** (MKN, léky, výkony, odbornosti v čase). Karcinom plic od 1. bronchoskopie: **58 % čeká na operaci > 6 týdnů, 64 % na RT, 47 % na farmakoterapii** (doporučení: operace do 4 týdnů).
- **Hanna et al., BMJ 2020**: každé 4 týdny zpoždění léčby = vyšší mortalita; zrychlení o 1–3 týdny má klinický význam.
- **Koordinace**: úkol → vlastník a termín → potvrzení převzetí (odeslaná žádanka ≠ provedené vyšetření) → výjimka a eskalace. Klinická rozhodnutí zůstávají u lékaře.
- Jeho vlastní „výzvy": (1) od podezření k dokončené diagnostice, (2) správná péče na správném pracovišti KOC ↔ region, (3) dopravní služba pro koordinátora, (4) dokumentace dostupná koordinátorovi + **extrakce nezbytných informací z dokumentace s odkazem na zdroj a lidskou kontrolou**.
- Testovací scénáře: ztracený výsledek, nepřevzatá péče, výpadek dopravy, **chyba extrakce (negovaný nález, starý termín)**.

## 2. Michal Opatřil — České eHealth v kostce (Umbrellateam)
- **4 vrstvy**: EU (EHDS, MyHealth@EU) → stát (kmenové registry, eŽádanky, oprávnění) → výměnná vrstva (AAfD) → poskytovatelé (NIS/LIS/RIS/PACS). Dnes v ČR koexistují proprietární sítě (eSpráva, eMedox, ReDiMed…).
- **Právo**: 372/2011 (zdravotní služby), 325/2021 (elektronizace, novela 2.0 v připomínkách), **vyhláška 444/2024 o zdravotnické dokumentaci** — *„při promptování na ni mrkněte"*.
- **EHDS**: primární využití (péče o pacienta) vs sekundární (výzkum, přes HDAB). Prioritní kategorie: pacientský souhrn, propouštěcí zpráva, laboratoř, zobrazování, ZZS.
- **EHR ≠ zdravotnická dokumentace ≠ informační systém.** PDF = lidsky čitelná příloha / fallback; struktura = FHIR.
- **Klíčový citát pro nás**: lékaři chtějí narativ, strukturovaná data jsou přesnější, ale *„nesmíte je ubít tím, že těch strukturovaných dat bude moc"* → AI, která z narativu udělá strukturu — *„pohrajte si s tím"*.
- **Kmenové registry** (pacient, zdravotnický pracovník, poskytovatel) — v nemocnicích běžně duplicity pacientů. V řešení nechat **„bílé místo" pro ověření pacienta proti registru**, nestavět izolovanou DB pacientů.
- **Nestavět vlastní eŽádanky** — stát chystá centrální systém.
- Neříkat „sdílet" dokumentaci, ale **„zpřístupnit"** (dokumentace patří poskytovateli).
- **AAfD** = směrovač/index, ne centrální úložiště; data zůstávají u PZS. **IHE MHD**: ITI-65 publish, ITI-67 find, ITI-68 retrieve; ATNA = audit.
- **Terminologie v ČR**: MKN-10 (jediná všeobecně ujatá), NČLP pro laboratoře (LOINC zatím ne), SNOMED málokdo zná — pokud ho použijete, ať ho AI generuje z narativu.
- **Slide 19 — tři věrohodné typy prototypů**: A) cesta pacienta / MDT, **B) vytěžování zpráv s citací a lidským potvrzením**, C) data pro hodnocení / NOR.
- **Cena**: vítězný tým jde celý na „Národní dialog pro digitalizaci" 19. 10. v ILF Praha.

## 3. Hynek Kružík — HL7 FHIR a European Common Cancer Model (NCEZ, HL7 CZ)
- FHIR = resources (Patient, Condition, Observation…) skládané do profilů; pravidlo 80/20 + extensions. V EU se jede **R4**, přechod na R6 odhadem do roka.
- ČR se podílí na EU prováděcích aktech EHDS (do března příštího roku); české IG jsou kompatibilní s EU.
- **Common Cancer Model (HL7 Europe, 1.0.0-ballot)**: konceptuální → logický model (CancerPatient, CancerConditionAtDiagnosis, **CancerStage — TNM, klinické vs patologické**, Surgery, Radiotherapy, SystemicTreatment, ClinicalCancerProgression, OverallCancerTreatmentResponse, LastFollowUp). Mapování na FHIR zatím jen pacient; mapování na **OMOP** pro sekundární využití.
- Pohlaví: *sex at birth* vs administrative gender (důležité pro interpretaci laboratoře).
- **SNOMED**: nové CZ profily na něj přecházejí (mimo NČLP) — trochu jiný pohled než Opatřil.
- **mCODE** (US) a Common Cancer Model se doplňují; EU budoucí profily = EU Base + adopce z mCODE.
- DASTA pro nový vývoj nepoužívat.
- **Rada pro 24h prototyp**: dívat se na základní stavební bloky (resources) a **terminologie**; pozor na pre- vs post-koordinaci kódů.
- Akce: HL7 WGM Malaga 16.–20. 11. (den o Common Cancer Model).

## 4. Microsoft (Michal Marušan) — prostředí
- **Portál** https://aka.ms/rakathon2026: API klíč, endpoint gateway, modely, data (jen VZP).
- **Modely** přes 1 klíč: OpenAI gpt-6.1-sol / astra / luna, grok-4.7, DeepSeek-V4-Pro, Kimi-K2.7-Code, MAI-Thinking-1, MAI-Image-2.5. Do `model` jde název deploymentu; pro zdravotní data **`-dz-eu`**.
- **Azure**: vlastní resource group, role Contributor (RBAC si přiřadit nejde — řešit na Slacku), Entra ID / DevOps nejsou. Budget ~100–200 USD/tým, **GPU VM zakázané**, free tiery jsou sdílené přes celou subskripci.
- **429** = rate limit → exponential backoff; **401/403** = revokace/limit → Slack #08-tech-helpdesk (poslat tým, endpoint, deployment, čas — **nikdy TAP ani klíč**).
- **Copilot**: licence na osobu (~100 USD kredit), modely i od Anthropic/Google; levnější modely na subagenty, reasoning high jen na architekturu; **cloud agent** jede i když notebook spí; doporučuje worktrees pro paralelní sessions; Copilot umí Claude Code skills.
- Pokud máš placený Copilot, **použij nový GitHub účet** — organizace by ho nahradila.
- **Pravidla (Tomáš Studeník)**: předem připravený boilerplate/UI **lze, ale musí se transparentně deklarovat**; hodnotí se jen práce během Rakathonu; submissions budou zveřejněny.
- **Demo stačí z lokálu** (Lada Vasicek). Použití Azure **nemá vliv na hodnocení**.

## 5. Ondřej Hoferek — InterSystems
- InterSystems: Epic běží na jejich technologii, IntelliCare (AI-first NIS, MDR IIa), národní výměnné sítě. V ČR: IKEM (Zlatokop), **FN Ostrava používá IRIS pro integrace**.
- **Caelestinus** — inkubátor (3 měsíce online), divoká karta pro 1+ tým.
- **Výzva 1 500 €**: využít IRIS pro AI (vector search, agenti) a/nebo interoperabilitu přes FHIR.
- Největší překážka nasazení v praxi = **napojení na NIS** → FHIR to řeší; IRIS FHIR server berte jako **simulaci interoperability** (reálné prostředí nemocnice na hackathonu nebude).
- **FHIR server může být i vaše primární databáze** (dotazníky, plány péče, klinická data) přes REST.
- **Hackathon Kit**: docker compose → IRIS + FHIR R4 (s ukázkovými daty — smazat), notebooky: CSV→SQL, FHIR load/search/create, **transakční Bundle**, bulk import, **FHIR SQL Builder** (FHIR → SQL tabulky), VECTOR typ + embeddingy + chunking, agent tools (SQL / vector / FHIR), **MCP server (FastMCP)**; skript na FHIR server ve vzdálené instanci.
- **Co přesvědčilo porotu dřív**: promyšlená reprezentace dat ve FHIR, co všechno je interoperabilní, dopad, inovace **„co v zadání nebylo"**.
- **Rady**: FHIR hned od začátku; neřešit každý detail (např. OAuth); konzultovat architekturu s nimi + se zadavatelem.
- **Cloud LLM vs lokální**: jen pokud zadavatel potvrdí anonymní/syntetická data; jinak lokální model (nedodávají).
- Mentoři: Ostrava **Dan Kutáč**, Praha Hoferek + Gabriel, Brno Daniel Drozdov; v noci online 24/7. Slack: #08-tech-helpdesk + kanál výzvy InterSystems.

## 6. Luc Chatty — Beyond the hackathon: FHIR & PHOENIX (Fyrstain, HL7 Europe)
*Ze slidů + přepisu z audia (Whisper). Záznam odpoledne 2:12–2:47.*
- **Z přednášky (přepis)**:
  - 2:14–2:16 — udělat „wow" prototyp s AI je snadné; v první nemocnici narazíte na 40 let staré standardy a chybějící terminologie, ve druhé to zas funguje jinak.
  - 2:16–2:18 — FHIR: vlastní DB + FHIR API, nebo FHIR warehouse, nebo kombinace; mapování lokálních kódů na mezinárodní terminologie. Pull model = nová bezpečnostní otázka (přístup ≠ právo vidět vše).
  - 2:20–2:23 — nemocnice ve Francii = ~150 aplikací s vlastními DB; skutečný problém není FHIR, ale **jak ze 150 zdrojů udělat jeden agregovaný pohled na pacienta**.
  - **2:24–2:25 — SYNDERAI**: knihovna syntetických EU dat — ~237 pacientů, ~4 000 lab reportů, pacientské souhrny, propouštěcí zprávy (medikace a zobrazování zatím ne).
  - 2:25–2:27 — onkologie ve FHIR je složitá: nádor zmizí a vrátí se i po 15 letech, víc stadií, víc léčeb a odpovědí → potřeba historie.
  - 2:29–2:33 — Common Cancer Model: nejdřív klinický význam, pak logický model (např. *cancer condition at diagnosis: subject, histology behavior, body site*), FHIR mapování rozpracované; **„v prototypu se co nejvíc držte FHIR resources", inspirace mCODE**.
  - 2:37:44–2:38:46 — rady: začni klinickým kontextem; dohodni FHIR kontrakty; **kódy a terminologie, ne text**; security a původ dat; testuj na syntetických datech a příkladech, „dej modelu zabrat".
  - 2:40–2:42 — Q&A: AI v onkologii bude nejspíš zdravotnický prostředek → certifikace **3–5 let**; stavět pro stav světa za 5 let (EHDS formáty).
  - **2:43:19–2:44:36 — „Co když nemocnice má jen PDF?" → potřebujete vlastní „transformátor", který data vezme a převede do standardizovaného formátu. Přesně argument pro AI NOR.**
- Prototyp je začátek; skutečný test je, **jestli ho druhá nemocnice pochopí, bude mu věřit a nasadí ho**.
- „Uložit JSON" ≠ interoperabilita: potřeba profily, terminologie, security, workflow.
- **Hospitals on FHIR** (komunita nemocnic), **PHOENIX** (EU onkologický datový model + FHIR, navazuje na mCODE), **XiA** (vzdělávání, micro-credentials).
- Onkologie = časová řada rozhodnutí napříč odděleními: diagnóza → staging → léčba → odpověď → follow-up.
- **6 voleb pro prvních 48 h**: začni workflow; FHIR kontrakty a hotové profily; standardní kódování (žádné ad-hoc stringy); důvěra od 1. dne (identita, přístup, provenance); testuj mimo demo s realistickými daty a validací; sdílej artefakty (mapování, předpoklady, příklady, testy).
- *„Your future customer is not only the clinician: it is also the next hospital."*
- Syntetická data: **SYNDERAI** (synderai.net). Akce: Pisa 19.–21. 10.

## 7. Organizace a chat
- Zítra (pá) dopoledne: představení výzev, týmové kanály na Slacku, kartičky s přístupy.
- Organizátor: *„Na ničem teď nepracujte, vyspěte se"*; porota čeká vyšší kvalitu díky AI agentům; v neděli hlasují i hackeři; duch vzájemné pomoci.
- Nepouštět do callů AI notetakery (Fireflies) — vše se nahrává centrálně.
- Otázky z chatu, které stojí za sledování: přístup k datům přes FHIR token (→ řeší se s výzvami), „hodnotí se víc nápad nebo technika?" (nezodpovězeno — zeptat se v pátek).
