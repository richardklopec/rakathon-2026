# Dokumentace AI NOR

| Soubor | K čemu |
|---|---|
| [navod.md](navod.md) | Návod pro obsluhu. Aplikace ho zobrazuje po kliknutí na **Dokumentace** v pravém horním rohu. |
| [vyuzite-funkce.pdf](vyuzite-funkce.pdf) | Využité funkce, služby a technologie pro porotu (tabulka, A4 na šířku). |
| [funkce.json](funkce.json) | Zdroj tabulky využitých funkcí: kategorie → položky (`nazev`, `sluzba`, `k_cemu`, `kde`, `stav`: `hotovo` / `castecne` / `plan`). |
| [make_pdf.py](make_pdf.py) | Z `funkce.json` vytvoří `vyuzite-funkce.pdf` (tisk přes Microsoft Edge): `python make_pdf.py` |

`navod.md` je běžný Markdown. Aplikace umí nadpisy `#`/`##`/`###`, odstavce, odrážky `-`, číslované seznamy `1.`, poznámky `>`, **tučné** a `kód`.
