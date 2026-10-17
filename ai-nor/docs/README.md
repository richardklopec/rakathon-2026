# Dokumentace AI NOR

Obsah, který aplikace zobrazuje po kliknutí na **Dokumentace** v pravém horním rohu.
Upravujte ho tady, frontend ho načítá přímo z této složky (po uložení se stránka v `npm run dev` sama obnoví).

| Soubor | Záložka v aplikaci | Pro koho |
|---|---|---|
| [funkce.json](funkce.json) | Využité funkce | porota, prezentace: tabulka použitých služeb, technologií a funkcí |
| [navod.md](navod.md) | Návod pro obsluhu | zdravotníci, kteří aplikaci používají |

## Jak upravovat

- **funkce.json**: kategorie → položky. Každá položka má `nazev`, `sluzba` (technologie nebo služba), `k_cemu`, `kde` (soubor v repu) a `stav`: `hotovo`, `castecne` nebo `plan`.
- **navod.md**: běžný Markdown. Aplikace umí nadpisy `#`/`##`/`###`, odstavce, odrážky `-`, číslované seznamy `1.`, poznámky `>`, **tučné** a `kód`.
