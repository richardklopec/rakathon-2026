# Návod pro obsluhu

AI NOR připraví hlášení **Incidence zhoubného novotvaru** do Národního onkologického registru (NOR) ze zpráv, které už máte v nemocničním systému. Hlášení nemusíte přepisovat ručně. Aplikace údaje vyplní, u každého ukáže, odkud ho vzala, a vy zkontrolujete jen to, co AI neví jistě.

> Nic se neodesílá automaticky. Hlášení odchází až po vašem potvrzení.

## Co budete potřebovat

- Zprávy jednoho pacienta: ambulantní a propouštěcí zprávy, histologie, zápis z MDT, operační protokol.
- Formát **PDF**, **TXT** nebo **XLSX** (export z NIS, jeden řádek = jedna zpráva).
- Webový prohlížeč s adresou aplikace (při lokálním spuštění `http://localhost:5173`).

## Záložky aplikace

- **Domů**: kolik hlášení je v jakém stavu, co čeká na vaši kontrolu a stav systému (jazykový model, IRIS FHIR, číselníky).
- **Seznam hlášení**: všechna hlášení v tabulce. Hledání podle pacienta nebo diagnózy, filtr podle stavu, řazení podle sloupců. Klik na řádek otevře hlášení ve Vytěžování.
- **Hlášení relapsu**: zápis recidivy nebo progrese k pacientovi s potvrzeným hlášením.
- **Nový pacient**: nahrání zpráv a spuštění vytěžování.
- **Číselníky**: MKN-10, topografie, morfologie a další číselníky formuláře NOR s hledáním.
- **Vytěžování**: kontrola hlášení jednoho pacienta, náhled formuláře a potvrzení.
- **Dokumentace** (vpravo nahoře): tento návod a přehled použitých technologií.

Hlášení prochází stavy **Nevytěženo → Ke kontrole → K potvrzení → Potvrzeno → Uloženo ve FHIR**. Číslo u záložky Seznam hlášení ukazuje, kolik hlášení čeká na kontrolu.

## Postup krok za krokem

### 1. Nahrajte zprávy pacienta

1. Otevřete záložku **Nový pacient**.
2. Přetáhněte zprávy do vyznačeného pole, nebo klikněte na **Vybrat soubory**. Vyberte všechny zprávy jednoho pacienta najednou. U každého souboru uvidíte odhad typu zprávy, chybně vybraný soubor odeberete křížkem.
3. Rodné číslo vyplňovat nemusíte, AI ho vezme ze zpráv. Když ho vyplníte, aplikace ho porovná se zprávami.
4. Klikněte na **Nahrát a vytěžit**. Vytěžení obvykle trvá 20–40 sekund, pak se hlášení samo otevře ve Vytěžování.

### 2. Podívejte se na souhrn

V záhlaví hlášení ve Vytěžování uvidíte:

- stav hlášení a počet nahraných zpráv,
- **ke kontrole**: kolik polí čeká na vaše rozhodnutí,
- **Jistota AI**: celkové skóre hlášení 0–100 (po najetí myší se zobrazí podrobnosti),
- žluté **upozornění**, pokud aplikace našla problém: různá rodná čísla ve zprávách, neplatné rodné číslo, diagnóza nepřípustná pro pohlaví pacienta nebo jiný (starší) nádor, který se v tomto hlášení nehlásí.

### 3. Vyřešte pole ke kontrole

Oranžově orámovaný blok **Ke kontrole** obsahuje jen dvě situace:

- **Rozpor**: dvě zprávy uvádějí pro stejné pole různou hodnotu. Klikněte na **citace 1**, **citace 2** a porovnejte zdroje. Pak klikněte na tlačítko se správnou hodnotou.
- **Nízká jistota**: AI si hodnotou není jistá (skóre pod 85). Ověřte ji v citaci a zvolte:
  - **Potvrdit**: hodnota je správně,
  - **návrh**: vybrat jinou hodnotu, kterou AI našla v dokumentaci,
  - **Upravit**: zadat vlastní hodnotu,
  - **Zamítnout**: pole zůstane prázdné.

Pole se seřadí tak, že rozpory jsou nahoře a pak pole od nejnižší jistoty. U diagnózy může být uvedené i pravidlo MKN-10, podle kterého AI kód zvolila.

### 4. Zkontrolujte zdroj kteréhokoli údaje

Pod blokem ke kontrole je vlevo text zprávy a vpravo celý formulář rozdělený na **Diagnóza**, **Morfologie**, **TNM** a **Ostatní**. U každého pole:

- **číslo** je jistota AI (zelená 85–100, oranžová 60–84, červená pod 60, fialová rozpor); po najetí myší vidíte důvody,
- **předvyplněno** = převzato od AI automaticky, **potvrzeno** = potvrdili jste, **opraveno** = změnili jste hodnotu,
- **zdroj** otevře zprávu vlevo a žlutě zvýrazní přesné místo, odkud údaj pochází,
- „chybí v dokumentaci“ znamená, že údaj ve zprávách není. AI ho nedomýšlí.

Předvyplněná pole nemusíte potvrzovat jednotlivě, ale můžete je kdykoli opravit.

### 5. Otevřete náhled a potvrďte hlášení

1. Klikněte na **Náhled a potvrzení**. Pod dokumenty se otevře hlášení ve tvaru formuláře ÚZIS.
2. Projděte ho. Pokud chybí povinná pole, vypíší se nahoře a stav je **Neúplné**.
3. Údaje můžete upravit přímo v náhledu. Kódy (Dg. MKN, topografie, morfologie…) vybíráte z rozbalovacího seznamu, do kterého lze psát a hledat.
4. Doplňte nebo opravte **rodné číslo pacienta**. Neplatné rodné číslo aplikace nepřijme.
5. Napište **své jméno** a klikněte na **Potvrdit hlášení**.

Tlačítko je neaktivní, dokud ve frontě **Ke kontrole** zbývá nějaké pole.

### 6. Export a uložení

Po potvrzení se zobrazí:

- **Export pro ÚZIS (JSON)**: hlášení ve struktuře formuláře NOR ke stažení,
- **Uložit do IRIS FHIR**: zapíše hlášení do nemocničního FHIR úložiště (InterSystems IRIS) včetně záznamu, kdo hlášení potvrdil a které údaje opravil.

> Jakákoli další úprava hlášení potvrzení zruší. Hlášení pak musíte potvrdit znovu.

## Hlášení relapsu

1. Otevřete záložku **Hlášení relapsu** a vlevo vyberte pacienta. Nabízejí se jen pacienti s potvrzeným hlášením incidence.
2. Nahoře vidíte souhrn primárního nádoru a dříve zapsané události.
3. V části **Nová událost** zvolte **Recidiva** nebo **Progrese**, datum zjištění a případně lokalizace vzdálených metastáz. Aplikace sama spočítá kód pro NOR (součet).
4. Zkontrolujte své jméno a klikněte na **Uložit a potvrdit**. Uložením znovu potvrzujete celé hlášení pacienta.

Chybně zapsanou událost odeberete ikonou koše. Relaps se zatím nepropisuje do exportu pro ÚZIS ani do FHIR.

## Číselníky

V záložce **Číselníky** vyberete číselník a hledáte v něm podle kódu, názvu nebo orgánu, například „prs“, „C50“ nebo „adenokarcinom“. Na diakritice nezáleží. Jsou to stejné číselníky, ze kterých vybírá AI i rozbalovací seznamy v náhledu hlášení.

## Tlačítko Vytěžit znovu

Spustí vytěžení znovu ze stejných zpráv. Použijte ho po změně nastavení nebo když se vytěžení přerušilo. **Pozor:** vaše dosavadní rozhodnutí v případu se přepíšou a hlášení bude třeba znovu potvrdit.

## Barvy a značky

- **Zelená 85–100**: předvyplněno, citace ověřena, žádný rozpor.
- **Oranžová 60–84**: ke kontrole.
- **Červená 0–59**: ke kontrole, ověřte zvlášť pečlivě.
- **Fialová, rozpor**: zprávy si odporují, vyberte správnou hodnotu.
- **Chybí v dokumentaci**: údaj ve zprávách není.

## Časté situace

**Nahoře svítí „IRIS FHIR: offline“.**

Úložiště IRIS neběží. Hlášení můžete vytěžit, zkontrolovat, potvrdit i exportovat pro ÚZIS, jen tlačítko „Uložit do IRIS FHIR“ je neaktivní. Kontaktujte správce.

**Nahoře svítí „AI: zkušební režim“.**

Aplikace běží bez jazykového modelu a vytěží jen několik údajů s kódem přímo v textu (MKN-10, morfologie, pTNM). Pro ostrý provoz kontaktujte správce.

**AI vyplnila údaj, který ve zprávě nevidím.**

Klikněte na **zdroj**. Pokud citace nesedí, pole opravte (Upravit) nebo zamítněte (Zamítnout). Aplikace nikdy nepředvyplní pole, jehož citaci nenašla v textu.

**Ve zprávách je i starší nádor.**

Aplikace hlásí jen aktuální primární nádor. Na ostatní upozorní žlutým pruhem, abyste mohli založit samostatné hlášení.

**Potvrzení nejde kliknout.**

Zkontrolujte, že jste vyplnili své jméno a že blok **Ke kontrole** je prázdný.

**Pacient chybí v Hlášení relapsu.**

Relaps lze zapsat jen k potvrzenému hlášení incidence. Hlášení nejdřív dokončete a potvrďte ve Vytěžování.

## Ochrana údajů

- Zprávy zpracovává jazykový model výhradně v datových centrech EU.
- Vyhledávání v textu (vektory) běží na serveru nemocnice, text tam zůstává.
- Pracujte jen s pacienty, ke kterým máte oprávnění.
