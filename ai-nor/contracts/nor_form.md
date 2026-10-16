# Formulář NOR „Incidence zhoubného novotvaru“ (aplikace ÚZIS) — pole a číselníky

Zdroj: 3 screenshoty formuláře od FNO (prázdný, `_info` s nápovědou a otevřenými číselníky, `_vyplňeno` = fiktivní vzor: BCC kůže zad).
Leží mimo repo v `../../Rakathon_DATA_NOR/Rakathon_DATA_NOR/`. Formulář má 2 strany a horní menu aplikace NOR:
Domů · Seznam hlášení · **Hlášení relapsu** · Nový pacient · Číselníky · **Vytěžování**.

Legenda „Plní“: **AI** = vytěžíme z dokumentace · **auto** = dopočítá aplikace ÚZIS / my z jiných polí · **kontext** = z NIS / nastavení pracoviště · **—** = nevyplňuje se.

## Hlavička
| Pole | Hodnota / formát | Plní |
|---|---|---|
| Pacient RČ, stav (žijící), trvalé bydliště, PSČ | z kmenových údajů | kontext |
| Evid. č. ZN | `RRRR/NNNNNN` (např. 2026/151516) | auto (ÚZIS) |
| Stav hlášení | **Neúplné / Úplné** | auto |

## Diagnostická část
| Pole | Číselník / formát | Plní | Pozn. |
|---|---|---|---|
| Zařízení (pracoviště) | IČZ + název, např. `00843989000000 - Fakultní nemocnice Ostrava` | kontext | |
| Oddělení | číselník oddělení (87 položek; 01 Interna, 02 Kardiologie, 03 Revmatologie, 04 Diabetologie, 05 Gastroenterologie, 06 Endokrinologie, 07 Klinická farmacie, 08 Geriatrie, 09 Infekční, 10 Alergologie a klin. imunologie, 11 Pneumologie a ftizeologie, 12 Neurologie, 13 Psychiatrie, … 20 Chirurgie …) | kontext / AI (z hlavičky zprávy) | celý číselník chybí, vyžádat |
| Neznámo (bezdomovec, neudaný pobyt) · Cizinec | checkbox | kontext | |
| Země původu | číselník zemí, `203 - Česko` | kontext | |
| **Datum stanovení diagnózy** | datum; „není-li známo, datum vyšetření nebo zahájení léčby“ | **AI** | anonymizovaná data často jen rok/měsíc |
| **K dg. vedla tato vyšetření** | **bitový součet**: 00 klinicky jasné · 01 klinické vyšetření · 02 laboratorní vyš. markery · 04 cytologie · 08 histologie metastázy · 16 histologie primárního nádoru (vzor: `17` = 01 + 16) | **AI** | „zaškrtávají se kolonky podle histologie“ |
| **Lateralita** | `1 - vpravo` · `2 - vlevo` · `3 - oboustranně` · `4 - odpadá` · `9 - neznámo` | **AI** | `4` u nepárových orgánů |
| **Dg. MKN** | MKN-10, formát `C44.5` (výběr `C00.0 - ZN- horní ret, zevní`) | **AI** | |
| Dg. slovně | text z MKN-10 (= sloupec `Nazev` CSV ÚZIS, např. „Jiný ZN – kůže trupu“) | auto | |
| Identifikace specifických diagnóz | číselník | — | „nevyplňuje se“ |
| **Topografie** | MKN-O topografie, např. `C44.5 - Kůže trupu` | **AI** / auto | „v některých případech se vyplní automaticky podle Dg. MKN“ |
| [Vztah Diagnóza / Topografie / Morfologie] | tlačítko = kontrola konzistence | auto | **stejnou kontrolu děláme ve validaci** |

### Morfologie
| Pole | Číselník / formát | Plní |
|---|---|---|
| **Typ morfologie** | `Cytologie` / `Histologie` | **AI** |
| **Kód morfologie** | MKN-O-3 `NNNN/C` (výběr `8000/0 - Nádor, benigní`, `8000/3 - Nádor, maligní`…) | **AI** (patička histologie `M1: M80903` → `8090/3`) |
| **Grading** | `1` dobře diferencovaný · `2` středně · `3` špatně · `4` nediferencovaný, anaplastický · `5` T-buňka · `6` B-buňka · `7` Null buňka · `8` NK buňka · `9` neurčen, neuveden, nepoužitelný | **AI** |
| **Název morfologie** | volný text (vzor „Bazocelulární karcinom, NS, na zádech“) | **AI** |

### TNM
| Pole | Formát | Plní | Pozn. |
|---|---|---|---|
| Skupina | TNM skupina podle lokalizace (vzor „Karcinom kůže (mimo oční víčko…)“) | auto | odvodit z dg. |
| **T / N / M** (klinické) | hodnoty bez prefixu (`1`, `0`, `0`) | **AI** | |
| **y** | checkbox (stav po neoadjuvanci) | **AI** | ypTNM |
| **pT / pN / pM** | hodnoty bez prefixu | **AI** | |
| **pN vyš. / pN poz.** | čísla: vyšetřené / pozitivní uzliny (např. `24/19`) | **AI** | v našem modelu zatím chybí |
| **sn** | sentinelová uzlina, číselník (vzor `X - nestanovena`) | **AI** | ostatní hodnoty číselníku neznáme |
| **Lokalizace vzdálených metastáz** | **bitový součet**: 0 neznámo · 1 plíce · 2 kostní dřeň · 4 kost · 8 pleura · 16 játra · 32 peritoneum · 64 mozek · 128 nadledvinky · 256 uzliny · 512 kůže · 1024 jiný orgán | **AI** | |
| Riziková kategorie · Sérové nádorové markery · p16 pozitivní | | — | „kolonka se nevyplňuje“ |
| **Klinické stádium** | číselník, vzor `1 - Stadium I`; tlačítko „Vyplnit stádium“ dopočítá z TNM | auto / **AI** | kontrola TNM ↔ stádium |

### Ostatní
| Pole | Číselník | Plní |
|---|---|---|
| **Onemocnění** | `1 - lokalizované` · `2 - pokročilé` · `9 - neznámo` | **AI** / auto (ze stádia) |
| Datum hlášení | datum | auto |
| Jméno hlásícího lékaře | text | kontext (přihlášený uživatel) |
| **Pracoviště hlásící novotvar** | **bitový součet**: 1 stanovilo diagnózu · 2 léčí pacienta (vzor `03`) | kontext / AI |

## Odkud se berou kódy pro rozbalovací seznamy

AI **nikdy nevymýšlí kód**. Vytáhne z textu hodnotu (a citaci) a backend ji namapuje na položku číselníku.
Kód, který v číselníku není, se do hlášení nedostane.

| Pole | Zdroj číselníku | Máme? |
|---|---|---|
| Dg. MKN, Dg. slovně | **MKN-10 ÚZIS** `01_MKN10_5E_2026_utf8.csv` (`KodSTeckou`, `Nazev`), jen kapitola C (+ D00–D09 in situ, D37–D48 nejisté) | ✅ celý (39 191 řádků) |
| Topografie | MKN-O-3 topografie C00.0–C80.9. Kódy se z velké části kryjí s MKN-10 C00–C80, názvy bez „ZN –“ („C44.5 - Kůže trupu“). Rejstřík lokalizací: `07_…novotvary_utf8.csv` (lokalizace → kód primární / sekundární / in situ / benigní / nejisté) | 🟠 přibližně z MKN-10; přesný číselník vyžádat |
| Kód morfologie | MKN-O-3 morfologie `NNNN/C`. Částečně v rejstříku MKN-10 `05_…nemoci a poranění_*.csv`: 704 kódů s českými termíny, např. „Adenokarcinom (M8140/3)“, „– duktální (M8500/3)“, „bazocelulární (M8090/3)“ (2 překlepy ÚZIS opraveny: `M90013/0` → 9013/0, `M91200/3` → 9120/3). Lymfomy a leukemie (96xx–99xx) v rejstříku skoro chybí: doplněny z přílohy PDF Tabelární části (Klasifikace SZO hematopoetických a lymfoidních nádorů, str. 867–870) → `uploads/morfologie_hematologie_szo_pdf2014_utf8.csv` (`scripts/extract_pdf_morphology.py`) | 🟠 793 kódů; úplný MKN-O-3 (aplikace NOR → Číselníky) vyžádat od FNO / ÚZIS |
| Typ morfologie, Lateralita, Grading, Onemocnění | malé pevné seznamy ze screenshotu formuláře (viz tabulky výše) | ✅ |
| K dg. vedla vyšetření, Metastázy, Pracoviště hlásící | pevné bitové hodnoty z formuláře | ✅ |
| Oddělení | číselník oddělení NOR (87 položek) | 🔴 jen prvních 13 + „20 Chirurgie“ |
| sn, Klinické stádium, TNM skupina | číselníky aplikace NOR | 🔴 jen ukázkové hodnoty |

### Jak AI vybere kód (pořadí, od nejjistějšího)
1. **Kód přímo v textu** (patička histologie `M1: M85003` → `8500/3`, „Dg.: C504“ → `C50.4`) → ověřit v číselníku → vysoká jistota.
2. **Přesná shoda termínu** s rejstříkem (normalizace diakritiky, zkratek, pořadí slov): „invazivní duktální karcinom“ → `8500/3`.
3. **Sémantické vyhledání** v číselníku: názvy položek číselníku jsou jako vektory v **IRIS Vector Search**. Dotaz „karcinom NST“ vrátí top 5 kandidátů
   a LLM z nich **vybírá** (nemůže vrátit jiný kód) nebo odpoví „nelze určit“. Nižší jistota, typicky → ke kontrole.
4. **Kontrola vztahu Dg / Topografie / Morfologie**: kód C50.4 ↔ topografie C50.x, chování `/3` u ZN, BCC `8090/3` ↔ kůže C44 atd.

Do skóre jistoty se promítne, kterou cestou kód vznikl (1 > 2 > 3).

## Co z toho plyne pro implementaci
- **Export ÚZIS** (`export/uzis.py`) produkuje přesně tato pole a kódy (číselné kódy, ne naše enumy). Mapování z `models.py`:
  `Laterality` → 1/2/3/4/9 (`midline` → 4), `grade` → 1–9, `disease_extent` → 1/2/9, bitové součty jako `int`.
- **Chybí v kontraktu** (`backend/app/models.py`, doplnit po domluvě): `morphology_type` (Cytologie/Histologie), `pn_examined`, `pn_positive`,
  `department`, `reporting_unit_role` (1/2), TNM `site_group`. `sentinel_node` už je, ale potřebuje kódy číselníku.
- **Neodhadovat**: celý číselník oddělení, číselník `sn`, klinických stádií a TNM skupin vyžádat od FNO / ÚZIS.
- Aplikace NOR má i formulář **Hlášení relapsu** a menu **Vytěžování**: zeptat se Ing. Najbrtové, co dnes „Vytěžování“ dělá
  (případně na něj navázat) a zda máme řešit i relapsy (máme data s progresí).
