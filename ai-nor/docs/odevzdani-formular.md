=== KRÁTKÝ POPIS ===

AI NOR vyplní hlášení do onkologického registru ze zpráv pacienta s citací zdroje. Lékař potvrdí, data ukládá InterSystems IRIS FHIR.


=== DELŠÍ POPIS ===

AI NOR připraví hlášení „Incidence zhoubného novotvaru“ do Národního onkologického registru (NOR) z běžné dokumentace pacienta. Lékař nepřepisuje formulář, řeší jen pole, kde se zprávy rozcházejí nebo si AI není jistá.

Jak to funguje
1. Zprávy: PDF (i skeny přes OCR), Word, e-mail, TXT, export z NIS, nebo HL7v2 zprávy, které NIS pošle do InterSystems IRIS.
2. Vytěžení: jazykový model v EU Data Zone vrátí pole formuláře NOR. Ke každé hodnotě musí dát doslovnou citaci ze zprávy. Aplikace je připravená i pro lokální model v nemocnici: LLM volá přes OpenAI-kompatibilní API a embeddingy i OCR už běží lokálně.
3. Ověření: citaci dohledáme ve zprávě, kódy MKN-10 a morfologie ověříme v číselnících ÚZIS. AI nesmí vymyslet kód. Kód diagnózy vybírá jen z kandidátů z IRIS Vector Search a cituje pravidlo MKN-10.
4. Jistota 0–100: počítá se z ověřitelných signálů (typ zdroje, shoda zpráv, platnost kódu, „susp.“ v citaci), ne ze sebehodnocení modelu. Pole od 85 bez rozporu se předvyplní, ostatní jdou do fronty Ke kontrole.
5. Lékař: vyřeší frontu, klikem vidí zvýrazněný zdroj každého údaje, zkontroluje náhled ve tvaru formuláře ÚZIS a hlášení potvrdí.

InterSystems IRIS for Health
- Produkce HL7v2 → FHIR: zprávy z NIS (MDM přes MLLP) převede vestavěnými převody přes SDA3 na FHIR DocumentReference.
- FHIR R4 (mCODE, HL7 CZ Core): každé hlášení je jeden záznam. Po vytěžení je rozpracované (Composition preliminary), po potvrzení konečné. Provenance říká, z jaké zprávy údaj je a co opravil lékař.
- Vector Search nad číselníky a pravidly MKN-10.
- SQL: hlášení a auditní log každé změny.

Data
Syntetičtí pacienti a anonymizovaná data FN Ostrava poskytnutá pro hackathon (nejsou v repozitáři). Dále číselníky MKN-10-CZ 2026 a Tabelární část MKN-10 od ÚZIS.

Co jsme stihli
Celou cestu od nahrání zpráv po potvrzené hlášení: OCR, vytěžení s citacemi, skóre jistoty, frontu ke kontrole, náhled formuláře, export pro ÚZIS (JSON, CSV), zápis do IRIS FHIR, produkci HL7v2, historii změn, hlášení relapsu a průvodce aplikací.

Co dál
Napojit produkci na skutečný NIS, doplnit FHIR mapování stádia, metastáz a léčby, domluvit s ÚZIS formát importu, přidat přihlašování a kalibrovat práh jistoty na reálných datech.


=== CO JSTE MĚLI UŽ PŘEDTÍM? ===

Kód aplikace vznikl celý během hackathonu (repo založeno 16. 10. 2026). Předem jsme měli jen poznámky z pre-hack day, plán a brief výzvy AI NOR. Převzali jsme konfiguraci Dockeru a skript pro založení FHIR serveru z FHIR-AI-Hackathon-Kit od InterSystems (MIT) a kostru frontendu z šablony Vite react-ts (MIT). Podrobně v PREEXISTING.md.


=== JAK VYUŽÍVÁTE AI? ===

V aplikaci: LLM gpt-6-luna-dz-eu v EU Data Zone vytěží z českých zpráv pole hlášení NOR. Druhý krok LLM vybírá kód MKN-10 podle pravidel Tabelární části. Lokální embeddingy hledají v číselnících přes IRIS Vector Search. Aplikace je připravená i pro lokální modely: LLM volá přes OpenAI-kompatibilní API, takže jde bez změny kódu přepnout na model v nemocnici (vLLM, Ollama). Embeddingy i OCR už běží lokálně.

Proti halucinacím: každá hodnota musí mít doslovnou citaci, kterou ověříme ve zprávě. Kód musí existovat v číselníku ÚZIS a model ho smí vybrat jen z kandidátů z IRIS. Jistota 0–100 se počítá z ověřitelných signálů, ne z odhadu modelu. Nejistá pole a rozpory jdou k lékaři, nic se neodešle bez potvrzení. Evaluace proti gold hodnotám.

Při vývoji: aplikaci jsme postavili s agenty Claude Code. Agenti pracovali paralelně na backendu, frontendu a FHIR/IRIS podle společného kontraktu a pravidel v AGENTS.md, s 26 skilly pro UI. Přes 100 testů hlídá, že se navzájem nerozbijí.


=== JAKÝ DOPAD MŮŽE PROJEKT MÍT? ===

Hlášení do NOR dnes lékař nebo datová manažerka vyplňuje ručně: hledá diagnózu, TNM, morfologii, grading a data v několika zprávách a přepisuje je do formuláře ÚZIS. AI NOR to otočí. Většinu polí předvyplní s citací a člověk řeší jen rozpory a nejistá pole.

Náš odhad (zatím neměřený na provozu): kontrola hlášení místo ručního vyplnění zkrátí práci z desítek minut na jednotky minut. Násobeno tisíci nových onkologických diagnóz ročně ve velké nemocnici to dělá stovky hodin práce zdravotníků za rok.

Méně chyb: kódy jen z oficiálních číselníků, kontrola vztahu diagnóza, topografie a morfologie, pohlaví a věku. Úplnější a včasnější data v registru zlepší statistiky a výzkum rakoviny v Česku. Data zůstávají ve standardu FHIR v IRIS, takže je jde znovu použít pro další registry a pro evropský prostor zdravotních dat (EHDS).


=== KOMU PROJEKT POMŮŽE NEJVÍC? (zaškrtnout) ===

Lékaři a sestry
Nemocnice a poskytovatelé péče
Výzkum


=== CHCETE PROJEKT DÁL ROZVÍJET S PARTNERY? ===

Ano


=== POUŽÍVÁTE TECHNOLOGIE INTERSYSTEMS? ===

Ano


=== JAK JE POUŽÍVÁTE? ===

IRIS for Health je datová vrstva celé aplikace. Zprávy z NIS přijímá produkce HL7v2 (MLLP) a vestavěnými převody přes SDA3 je ukládá jako FHIR DocumentReference. Každé hlášení je jeden FHIR R4 záznam (mCODE): po vytěžení rozpracovaný, po potvrzení lékařem konečný, s Provenance. Vector Search hledá kódy v číselnících a pravidlech MKN-10. SQL drží hlášení a auditní log změn.
