"""PDF of the used functions and services (funkce.json) for the jury: python make_pdf.py  ->  vyuzite-funkce.pdf

Builds an HTML page and prints it with Microsoft Edge in headless mode (installed on Windows), A4 landscape.
"""
import html
import json
import subprocess
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
src, out = HERE / "funkce.json", HERE / "vyuzite-funkce.pdf"
d = json.load(open(src, encoding='utf-8'))
STAV = {'hotovo': ('hotovo', 'ok'), 'castecne': ('částečně', 'part'), 'plan': ('plán', 'plan')}
e = html.escape
items = [p for k in d['kategorie'] for p in k['polozky']]
cnt = {s: sum(p['stav'] == s for p in items) for s in STAV}
body = [f"""<header><h1>AI NOR · Využité funkce a technologie</h1>
<p>Hlášení novotvarů do Národního onkologického registru · Fakultní nemocnice Ostrava · Rakathon 2026</p>
<p>{len(items)} funkcí a služeb v {len(d['kategorie'])} oblastech · hotovo {cnt['hotovo']} · částečně {cnt['castecne']} · v plánu {cnt['plan']} · stav k {date.today():%d. %m. %Y}</p></header>"""]
for k in d['kategorie']:
    rows = "".join(f"<tr><td class=n>{e(p['nazev'])}</td><td>{e(p['sluzba'])}</td><td>{e(p['k_cemu'])}</td><td class=kde>{e(p['kde'])}</td><td><span class='{STAV[p['stav']][1]}'>{STAV[p['stav']][0]}</span></td></tr>" for p in k['polozky'])
    body.append(f"<section><h2>{e(k['nazev'])}</h2><table><colgroup><col style='width:18%'><col style='width:19%'><col><col style='width:19%'><col style='width:8%'></colgroup><thead><tr><th>Funkce</th><th>Služba / technologie</th><th>K čemu slouží</th><th>Kde v kódu</th><th>Stav</th></tr></thead><tbody>{rows}</tbody></table></section>")
css = """@page{size:A4 landscape;margin:12mm 12mm 14mm}*{box-sizing:border-box}body{font-family:Arial,Helvetica,sans-serif;font-size:8.5pt;color:#0f172a;margin:0}
header h1{font-size:17pt;color:#014088;margin:0 0 3pt}header p{margin:0;color:#475569;font-size:9pt}
h2{font-size:11.5pt;color:#014088;margin:12pt 0 4pt;break-after:avoid}table{width:100%;border-collapse:collapse;table-layout:fixed}
thead{display:table-header-group}th{background:#dfeaf7;color:#012a5c;text-align:left;padding:4pt;font-size:8pt}
td{border-bottom:.5pt solid #cbd5e1;padding:4pt;vertical-align:top;overflow-wrap:anywhere}tr{break-inside:avoid}
td.n{font-weight:bold}td.kde{font-family:Consolas,monospace;font-size:7pt;color:#475569}
span{display:inline-block;padding:1pt 4pt;border-radius:3pt;font-size:7.5pt;white-space:nowrap}.ok{background:#ecfdf5;color:#047857}.part{background:#fffbeb;color:#b45309}.plan{background:#f1f5f9;color:#475569}"""
page_html = (f"<!doctype html><html lang=cs><head><meta charset=utf-8><title>AI NOR – Využité funkce</title><style>{css}</style></head><body>{''.join(body)}</body></html>")
with tempfile.TemporaryDirectory() as tmp:
    page = Path(tmp) / "funkce.html"
    page.write_text(page_html, encoding="utf-8")
    subprocess.run([EDGE, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", page.as_uri()],
                   check=True, capture_output=True)
print(f"{out} ({len(items)} položek)")
