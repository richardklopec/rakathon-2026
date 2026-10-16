# Prompt: snížit chybovost a zlepšit kalibraci jistoty AI NOR

> Znovupoužitelný prompt pro Claude Code. Vlož celý do nové session nebo napiš „proveď PROMPT_CHYBOVOST_KALIBRACE.md“.
> Referenční (gold) hodnoty pacientů FNO v repu nejsou (AGENTS.md: žádná pacientská data v gitu). Leží v `EVAL_GOLD_DIR`
> mimo repo, plné znění s pacientem pac.7_U je vedle repa.

---

Pracuješ na aplikaci AI NOR (repo rakathon-2026, složka ai-nor/). Z lékařských zpráv předvyplňuje hlášení
„Incidence zhoubného novotvaru“ do Národního onkologického registru (NOR). U každého pole ukazuje hodnotu, jistotu 0–100,
stav („✓ AI“ / „ke kontrole“ / „chybí v dokumentaci“), citaci zdroje a u Dg. MKN citaci pravidla MKN-10.

CÍL: snížit chybovost a zlepšit kalibraci jistoty. Opravuj obecné příčiny, nikdy nic natvrdo pro jednoho pacienta
(žádné řetězce, čísla ani výjimky vázané na konkrétní dokument).

ZÁVAZNÁ PRAVIDLA (AGENTS.md):
- Žádná pacientská data v gitu, testech ani v kódu. Referenční (gold) hodnoty pacientů FNO patří MIMO repo.
  Do repa smí jen syntetická data (data/synthetic/) a syntetické testy.
- contracts/ je zdroj pravdy. Když měníš models.py nebo API, uprav contracts/ a přegeneruj schéma (scripts.export_schema)
  a výslovně to uveď.
- O tom, co jde ke kontrole, rozhoduje jen backend/app/confidence.py. LLM se volá jen přes app/llm.py (EU -dz-eu).
- Chybějící ≠ negativní. Hodnotu nikdy neodvozuj z toho, že v textu něco není.
- Malé commity, zpráva česky v rozkazovacím způsobu. Před každým commitem musí projít `pytest -q` a `npm run build`.

## ZNÁMÉ CHYBY (zjištěné na pacientech FNO)
A) Dopočitatelné hodnoty (M, klinické stádium, rozsah onemocnění) jsou označené „chybí v dokumentaci“.
B) Počet vyšetřených uzlin ze zpráv o více vzorcích (SLN + non-SLN) se nesečte; osamocený zbytek textu z rozvržení PDF
   (např. „(2/0)“) má přednost před souvislým textem.
C) Hodnota Dg. MKN odporuje vlastní citaci pravidla (cituje pravidlo pro .8, vyplní .9).
D) Chybí kontroly vzájemné konzistence polí (TNM ↔ stádium ↔ metastázy ↔ uzliny ↔ data).
E) Nekontroluje se identita dokumentů (různá identifikační čísla, různé kódy diagnózy ve zprávách, nesedící čísla biopsií)
   ani předchozí nádory.
F) Zkratky se nerozlišují podle kontextu (IA, DKK…).
G) Jistota je špatně kalibrovaná: chybná hodnota z jedné zprávy má stejnou jistotu jako hodnota potvrzená třemi zprávami.

---

## FÁZE 0 – PROJDI A POPIŠ (bez změn kódu)
Popiš cestu dat s odkazy na soubory a funkce: ingest (PDF → text, offsety) → typ dokumentu → prompt a schéma
1. kroku LLM (extract/live.py) → ověření citací (extract/evidence.py) → normalizace (validate/normalize.py)
→ výběr vítězné hodnoty a rozpory (_field) → skóre jistoty (_score) → 2. krok kódování MKN-10 (extract/coder.py,
retrieval/rules.py) → review politika (confidence.py) → kontroly případu (validate/rodne_cislo.py) → náhled a export
(export/uzis.py) → UI (frontend/src).
U každé chyby z části „ZNÁMÉ CHYBY“ napiš, kde v kódu vzniká. Pozor: jistota se NEpřebírá od LLM, počítá ji
_score z důkazů. Problém jsou nekalibrované váhy a chybějící stropy, ne zdroj čísla.

## FÁZE 1 – EVALUACE (před jakoukoli opravou)
1. Skript backend/scripts/evaluate.py (v repu): pro každého pacienta spustí extrakci a porovná každé pole s gold
   hodnotou. Gold JSON čte z EVAL_GOLD_DIR (výchozí ../../Rakathon_DATA_NOR/gold/, mimo repo); syntetické goldy
   smí být v repu (eval/gold_synthetic/).
2. Formát gold pole: {"value": …, "status": "explicit" | "derived" | "missing" | "open", "alternatives": [...], "note": "…"}.
   Pole se stavem "open" se nehodnotí, jen vypíšou (čekají na odpověď FNO, viz Fáze 2).
3. Sada: všichni dostupní pacienti FNO (cíl ≥ 10) + 10 syntetických. Jeden pacient na kalibraci nestačí.
4. Metriky (tabulka v markdownu + JSON pro srovnání běhů):
   - přesnost po polích a celkem
   - falešně chybějící (gold má hodnotu, aplikace „chybí“) a falešně vyplněné (gold „missing“, aplikace hodnotu má)
   - záchyt chyb: podíl chybných hodnot, které aplikace sama poslala ke kontrole
   - ZÁROVEŇ podíl polí přijatých automaticky a jejich přesnost. Záchyt chyb samotný jde splnit tím, že vše pošleš ke kontrole.
   - přesnost podle pásma jistoty (85–100 / 60–84 / 0–59) a počet polí v pásmu
   - očekávaná vs vydaná varování
5. Kvůli opakovatelnosti používej LLM cache (backend/var/llm-cache). Po změně promptu se cache neuplatní, proto pusť
   baseline dvakrát a uveď rozptyl mezi běhy.
6. Spusť baseline a výsledky mi ukaž.

STOP: pošli mi popis z Fáze 0, baseline z Fáze 1 a plán. Kód extrakce měň až po mém potvrzení.

## TESTOVACÍ PACIENTI
Gold hodnoty a očekávaná varování jsou v EVAL_GOLD_DIR (mimo repo), první je pac.7_U z `Rakathon_DATA_NOR`.
Sporná pole jsou v goldu ve stavu "open" (viz Fáze 2), např. pM, „žádné“ metastázy, rozsah onemocnění, pořadí novotvaru.
Datum stanovení diagnózy, které v dokumentaci výslovně není, se podle formuláře („není-li známo, uvést datum vyšetření
nebo zahájení léčby“) vyplní jako odvozené a jde vždy ke kontrole. Nesmí se hodnotit jako „chybí“.

## FÁZE 2 – OTEVŘENÉ OTÁZKY (polož mi je, nekóduj odhad)
1. Jak NOR zapisuje „vzdálené metastázy nejsou“, když 0 = neznámo? (Dnes aplikace „žádné“ převádí na 0, tedy „neznámo“.
   To je chyba, oprav ji podle odpovědi.)
2. Pravidlo pro „Onemocnění“ (rozsah): podle M, nebo podle stádia (I–II = 1, III–IV = 2)? Kód teď odvozuje z M,
   contracts/nor_form.md píše „ze stádia“. Sjednotit až po odpovědi.
3. pM: zapisuje NOR „X“, nebo pole nechává prázdné? (TNM 7/8 kategorie pMX ani pM0 nezná.)
4. K dg. vedla vyšetření: obsahuje aktuální formulář i 32 a 99 (metodika 2018), nebo jen 00–16 (screenshoty FNO)?
5. Je „pořadí novotvaru“ pole formuláře Incidence? Když ano, je to změna kontraktu.
6. Stádium: UICC TNM 8 anatomické (předpoklad), ne AJCC prognostické?
Dokud odpověď nemám: pole vyplň jako ke kontrole s důvodem „pravidlo NOR neověřeno“, žádná pevná pravidla.

## FÁZE 3 – OPRAVY (v tomto pořadí; každý krok = malý commit + testy + nový běh evaluace a srovnání)

1. Konzistenční validátory (nový modul validate/consistency.py, dopad do jistoty přes confidence.py, varování u pole v UI):
   - cM/pM 1 ↔ vyplněná lokalizace metastáz; M0 ↔ žádné metastázy (až po otázce 1)
   - stádium ↔ TNM; rozsah ↔ stádium/M (až po otázce 2)
   - pN poz. ≤ pN vyš.; pN0 ↔ pN poz. = 0; sn ↔ nález v SLN
   - K dg. vedla vyšetření ↔ typ morfologie (16 jen s histologií primárního nádoru, 04 jen s cytologií)
   - Dg. MKN ↔ topografie ↔ morfologie (C50.x ↔ C50.x, chování /3 u ZN)
   - datum diagnózy ≤ datum operace / první léčby
   Porušení: strop jistoty (např. 50) + ke kontrole + text důvodu.

2. Citace musí hodnotu podporovat (extract/coder.py):
   - citovaný řádek podpoložky musí mít stejný kód jako zvolená hodnota; citovaná poznámka „→ .8“ musí odpovídat kódu .8.
     Jinak strop 60 a ke kontrole.
   - Deterministická kontrola kvadrantu prsu jako druhý nezávislý názor (ne náhrada LLM): bradavka .0, centrální .1,
     HVK .2, DVK .3, HZK .4, DZK .5, axilární výběžek .6, rozhraní / více kvadrantů (HKK, DKK, ZKK, VKK v popisu prsu) .8,
     NS .9. Neshoda s LLM → ke kontrole. „DKK/HKK“ mimo kontext prsu jsou končetiny.

3. Identita a dokumenty:
   - porovnávej VŠECHNA identifikační čísla tvaru RČ (i neplatná / anonymizovaná) a označení „RČ“, „r. č.“, „č. poj.“,
     „číslo pojištěnce“. Rozdíl = varování „nesoulad identity“ s názvy souborů. (Dnes validate/rodne_cislo.py porovnává
     jen platná RČ, takže anonymizovaná čísla nesoulad neukážou.)
   - rozdílné kódy diagnózy napsané v různých zprávách → varování (i když vyhraje kód z pravidel)
   - čísla biopsií a odkazy na ně → jen varování (různé laboratoře mají různé řady)

4. Strop jistoty při rozporu: pole se stavem conflict max 60 (dnes si drží skóre vítěze, např. 80 s ⚠).

5. Uzliny (pN vyš. / pN poz.):
   - počítej po vzorcích: SLN a non-SLN z jednotlivých histologických nálezů se SČÍTAJÍ. Stejný vzorek zmíněný v AZ
     i v histologii se NEsčítá dvakrát (zdroj pravdy jsou histologie, souhrny slouží jen ke kontrole).
   - výsledek porovnej se souhrny („N0 (0/3)“, „N0 /3/0/“, „0/3“). Neshoda → varování + ke kontrole.
   - citace bez souvislé věty (osamocené „(2/0)“ z rozvržení PDF) mají nižší váhu než souvislý text.
   - dnešní _field bere různé počty z různých zpráv jako soupeřící hodnoty. Pro uzliny to je špatný model, potřebují
     vlastní agregaci.

6. Deterministická odvození (nový modul, tabulkami řízený a rozšiřitelný po lokalizacích, začni prsem):
   - stádium z TNM (UICC 8): pT/pN mají přednost před cT/cN, M z cM/pM
   - rozsah onemocnění až po odpovědi na otázku 2
   - cM0 jen z výslovného stagingu („M0“, „bez známek generalizace“, negativní staging vyšetření) a vždy ke kontrole.
     Z mlčení nic.
   - tři stavy: explicit / derived (s viditelným postupem, např. „pT1b + pN0 + cM0 → IA“) / missing
   - jistota odvozené hodnoty = minimum jistot vstupů − 5. Plošných −15 za odvození platí jen pro úsudek LLM,
     ne pro výpočet z ověřených vstupů.

7. Chybějící pole:
   - nejdřív deterministické hledání v textech (regex + vyhledávání v IRIS Nor.Chunk), pak JEDNO společné LLM volání
     pro povinná pole, která stále chybí, s povinnou doslovnou citací. Ne zvláštní průchod pro každé pole.
   - UI: chybějící POVINNÉ pole je viditelně nehotové (ke kontrole / zřetelný styl). Chybějící nepovinné pole zůstává
     neutrální.

8. Kalibrace (až s daty z evaluace): uprav váhy v _score a stropy podle přesnosti v pásmech. Cíl: v pásmu 85–100
   aspoň 95 % správně. Žádné ladění na jednoho pacienta.

9. Slovník zkratek (sdílený modul pro prompty i regexy) s rozlišením podle kontextu: IA (inhibitor aromatázy × stádium IA),
   DKK (dolní kvadranty × dolní končetiny), HZK, HVK, DZK, DVK, MASC, CCB, BCS, SLN/SLNB, CHT, RT, HT a další.
   Část už je v promptu coder.py a v _SITE_SENTENCE v live.py, sjednoť to.

## VÝSTUP NA KONCI
- srovnání evaluace před a po (po polích + metriky z Fáze 1), u každého kroku Fáze 3 jeho vlastní přínos
- seznam commitů
- co zůstává nejisté a otevřené otázky pro FNO / ÚZIS
- změny kontraktu (contracts/), pokud nějaké byly
