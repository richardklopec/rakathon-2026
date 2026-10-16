"""Evaluate the extraction against gold (reference) values, field by field (PLAN.md §4 and step 11).

Gold = one JSON per patient in EVAL_GOLD_DIR. FNO patients are never in the repo (AGENTS.md); synthetic gold may live
in ai-nor/eval/gold_synthetic/.

    {
      "patient": "pac.X",
      "documents_dir": "folder with the patient's documents (absolute, or relative to the gold file)",
      "fields": {"icd10": {"value": "C34.1", "status": "explicit", "alternatives": [], "note": "…"}, …},
      "warnings": [{"id": "identity", "desc": "…", "match": "regex searched in the case warnings"}]
    }

status: explicit | derived (a value is expected) · missing (the field must stay empty) · open / todo (not scored).
Values use the NOR form codes: laterality "2", grade "2", diagnosis_basis 17 (sum), metastasis_sites [1, 16] (bits,
[] = none), diagnosis_date "2026-04-02" / "2026-04" / "2026", TNM without prefix ("1b", "X").

Usage (from backend/):
  .venv/Scripts/python -m scripts.evaluate [--runs 2] [--fresh-cache] [--gold DIR] [--only PAC001] [--out DIR]
  .venv/Scripts/python -m scripts.evaluate --compare before.json after.json
  .venv/Scripts/python -m scripts.evaluate --render result.json      (metrics + report again, without the LLM)
  .venv/Scripts/python -m scripts.evaluate --template PATIENT_DIR OUT.json
Results contain patient values: they go to backend/var/eval/ (not in git).
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.models import Extracted, FieldStatus, Laterality, NorReport, PartialDate, ReviewState
from app.validate.normalize import LATERALITY_NOR

FIELDS = [
    ("diagnosis_date", "Datum stanovení dg"), ("diagnosis_basis", "K dg. vedla vyšetření"), ("laterality", "Lateralita"),
    ("icd10", "Dg. MKN"), ("topography", "Topografie"), ("morphology_type", "Typ morfologie"),
    ("morphology_code", "Kód morfologie"), ("grade", "Grading"), ("morphology_name", "Název morfologie"),
    ("tnm_clinical.t", "T"), ("tnm_clinical.n", "N"), ("tnm_clinical.m", "M"),
    ("tnm_pathological.t", "pT"), ("tnm_pathological.n", "pN"), ("tnm_pathological.m", "pM"),
    ("pn_examined", "pN vyš."), ("pn_positive", "pN poz."), ("sentinel_node", "sn"),
    ("metastasis_sites", "Lokalizace metastáz"), ("clinical_stage", "Klinické stádium"), ("disease_extent", "Onemocnění"),
    ("tumour_order", "Pořadí novotvaru"),  # not in the data model (yet): always empty in the app
]
LABELS = dict(FIELDS)
NOT_SCORED = {"open", "todo"}
ERRORS = ("wrong", "false_missing", "false_filled")
BANDS = [(85, 100, "85–100"), (60, 84, "60–84"), (0, 59, "0–59")]


# --- comparing one field ---------------------------------------------------------------------------------------------

def get_field(report: NorReport, path: str) -> Extracted | None:
    obj = report
    for part in path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj if isinstance(obj, Extracted) else None


def app_value(f: Extracted | None, path: str):
    """The field's value in NOR form codes, or None when the app leaves it empty."""
    if f is None or f.value is None or f.status in (FieldStatus.missing, FieldStatus.not_applicable):
        return None
    if f.review.state == ReviewState.rejected:
        return None
    v = f.value
    if path == "laterality":
        return LATERALITY_NOR[Laterality(v)]
    if path == "diagnosis_basis":
        return sum(int(x) for x in v)
    if path == "metastasis_sites":
        return sorted(int(x) for x in v)
    if isinstance(v, PartialDate):
        return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate((v.year, v.month, v.day)) if x)
    return v


def norm(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        return ",".join(str(int(x)) for x in sorted(v))
    s = unicodedata.normalize("NFKD", str(v))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[+;,]", " ", s)  # free text: "adenokarcinom + složka" == "adenokarcinom, složka"; keeps "8140/3" and "C34.1"
    return re.sub(r"\s+", " ", s).strip(" .")


def judge(gold: dict, app) -> str:
    """correct | wrong | false_missing | false_filled | open"""
    status = gold.get("status")
    if status in NOT_SCORED:
        return "open"
    if status == "missing":
        return "correct" if app is None else "false_filled"
    if app is None:
        return "false_missing"
    accepted = {norm(gold.get("value")), *(norm(a) for a in gold.get("alternatives", []))}
    return "correct" if norm(app) in accepted else "wrong"


def flagged(f: Extracted | None) -> bool:
    """Would the clinician see this field in the review queue? (missing fields are not reviewed today)"""
    return bool(f and f.status != FieldStatus.missing and f.needs_review and f.review.state == ReviewState.pending)


def rows_for(patient: str, run: int, report: NorReport, gold_fields: dict) -> list[dict]:
    rows = []
    for path, label in FIELDS:
        gold = gold_fields.get(path, {"status": "todo"})
        f = get_field(report, path)
        app = app_value(f, path)
        rows.append({
            "patient": patient, "run": run, "path": path, "label": label,
            "gold": gold.get("value"), "gold_status": gold.get("status"), "note": gold.get("note", ""),
            "app": app, "confidence": f.confidence if f and app is not None else None,
            "state": f.review.state.value if f and app is not None else "missing",
            "conflict": bool(f and f.status == FieldStatus.conflict),
            "flagged": flagged(f), "outcome": judge(gold, app),
            "reasons": f.confidence_reasons if f else [],
        })
    return rows


def match_warnings(expected: list[dict], warnings: list[str], report: NorReport) -> list[dict]:
    """Expected warnings found in the case warnings, or only in a field's confidence reasons (tooltip), or not at all."""
    reasons = [r for _, f in _all_fields(report) for r in f.confidence_reasons]
    out = []
    for w in expected:
        rx = re.compile(w["match"], re.IGNORECASE)
        where = "varování" if any(rx.search(x) for x in warnings) else "jen v důvodech pole" if any(rx.search(x) for x in reasons) else None
        out.append({**w, "found": where})
    return out


def _all_fields(report: NorReport):
    for path, _ in FIELDS:
        if f := get_field(report, path):
            yield path, f


# --- metrics -----------------------------------------------------------------------------------------------------

def _pct(a: int, b: int) -> str:
    return f"{a}/{b} = {100 * a / b:.0f} %" if b else "–"


def metrics(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["outcome"] != "open"]
    errors = [r for r in scored if r["outcome"] in ERRORS]
    auto = [r for r in scored if r["state"] == "auto_accepted"]
    bands = []
    for lo, hi, name in BANDS:
        inband = [r for r in scored if r["confidence"] is not None and lo <= r["confidence"] <= hi]
        bands.append({"band": name, "n": len(inband), "correct": sum(r["outcome"] == "correct" for r in inband)})
    per_field = {}
    for path, _ in FIELDS:
        fr = [r for r in scored if r["path"] == path]
        if fr:
            per_field[path] = {k: sum(r["outcome"] == k for r in fr) for k in ("correct", *ERRORS)} | {
                "n": len(fr), "errors_flagged": sum(r["outcome"] in ERRORS and r["flagged"] for r in fr)}
    return {
        "scored": len(scored),
        "correct": sum(r["outcome"] == "correct" for r in scored),
        "wrong": sum(r["outcome"] == "wrong" for r in scored),
        "false_missing": sum(r["outcome"] == "false_missing" for r in scored),
        "false_filled": sum(r["outcome"] == "false_filled" for r in scored),
        "errors": len(errors),
        "errors_flagged": sum(r["flagged"] for r in errors),
        "auto": len(auto),
        "auto_correct": sum(r["outcome"] == "correct" for r in auto),
        "bands": bands,
        "per_field": per_field,
    }


def run_variance(rows: list[dict]) -> list[dict]:
    """Fields that differ between runs (LLM nondeterminism): in value, or only in confidence / review state."""
    by_key = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["run"]):
        by_key[(r["patient"], r["path"])].append(r)
    out = []
    for (patient, path), rs in by_key.items():
        values = [json.dumps(r["app"], ensure_ascii=False, default=str) for r in rs]
        scores = [f"{r['confidence']} {r['state']}{' → ke kontrole' if r['flagged'] else ''}" for r in rs]
        if len(set(values)) > 1 or len(set(scores)) > 1:
            out.append({"patient": patient, "path": path, "kind": "value" if len(set(values)) > 1 else "score",
                        "values": values, "scores": scores})
    return out


# --- running -----------------------------------------------------------------------------------------------------

def load_gold(gold_dir: Path, only: list[str] | None) -> list[tuple[Path, dict]]:
    files = sorted(gold_dir.glob("*.json")) if gold_dir.is_dir() else []
    golds = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in files]
    return [(p, g) for p, g in golds if not only or g.get("patient") in only]


def documents(gold_path: Path, gold: dict):
    from app import ingest

    folder = Path(gold["documents_dir"])
    folder = folder if folder.is_absolute() else gold_path.parent / folder
    docs = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in (".pdf", ".txt", ".md", ".xlsx"):
            docs += ingest.to_documents(p.name, p.read_bytes())
    return docs


def evaluate(golds: list[tuple[Path, dict]], runs: int, fresh_cache: bool, out_dir: Path, stamp: str) -> dict:
    from app import extract
    from app.config import get_settings

    settings = get_settings()
    result = {"stamp": stamp, "llm_mode": settings.llm_mode, "llm_model": settings.llm_model, "runs": runs,
              "fresh_cache": fresh_cache, "patients": [g.get("patient") for _, g in golds], "rows": [], "warnings": []}
    for run in range(1, runs + 1):
        if fresh_cache:
            settings.llm_cache_dir = str(out_dir / f"cache-{stamp}-run{run}")
        for path, gold in golds:
            patient = gold.get("patient", path.stem)
            print(f"run {run}: {patient} …", file=sys.stderr, flush=True)
            report, warnings = extract.extract(documents(path, gold))
            result["rows"] += rows_for(patient, run, report, gold.get("fields", {}))
            result["warnings"].append({"patient": patient, "run": run, "produced": warnings,
                                       "expected": match_warnings(gold.get("warnings", []), warnings, report)})
    result["metrics"] = metrics(result["rows"])
    result["variance"] = run_variance(result["rows"])
    return result


# --- report ------------------------------------------------------------------------------------------------------

def _cell(v) -> str:
    if v is None:
        return "—"
    return (", ".join(map(str, v)) or "žádné") if isinstance(v, list) else str(v).replace("|", "/")


OUTCOME = {"correct": "✓", "wrong": "✗ chybně", "false_missing": "✗ chybí", "false_filled": "✗ navíc", "open": "· otevřené"}


def markdown(result: dict) -> str:
    m = result["metrics"]
    out = [
        f"# Evaluace AI NOR – {result['stamp']}",
        f"LLM: {result['llm_mode']} `{result['llm_model']}` · běhů: {result['runs']} · "
        f"{'každý běh bez cache' if result['fresh_cache'] else 'sdílená LLM cache'} · pacienti: {', '.join(result['patients'])}",
        "",
        "## Souhrn (všechny běhy dohromady)",
        "| metrika | hodnota |", "|---|---|",
        f"| přesnost hodnocených polí | {_pct(m['correct'], m['scored'])} |",
        f"| chybná hodnota | {m['wrong']} |",
        f"| falešně chybějící (gold má hodnotu, aplikace „chybí“) | {m['false_missing']} |",
        f"| falešně vyplněné (gold „chybí“, aplikace hodnotu má) | {m['false_filled']} |",
        f"| záchyt chyb (chyby, které aplikace poslala ke kontrole) | {_pct(m['errors_flagged'], m['errors'])} |",
        f"| přijato automaticky | {_pct(m['auto'], m['scored'])} |",
        f"| přesnost automaticky přijatých | {_pct(m['auto_correct'], m['auto'])} |",
        f"| polí s jinou hodnotou mezi běhy | {sum(v['kind'] == 'value' for v in result['variance'])} |",
        f"| polí se stejnou hodnotou, ale jinou jistotou / stavem | {sum(v['kind'] == 'score' for v in result['variance'])} |",
        "",
        "## Přesnost podle pásma jistoty",
        "| pásmo | polí | správně | přesnost |", "|---|---|---|---|",
        *[f"| {b['band']} | {b['n']} | {b['correct']} | {_pct(b['correct'], b['n'])} |" for b in m["bands"]],
        "",
        "## Po polích",
        "| pole | hodnoceno | správně | chybně | falešně chybí | falešně navíc | chyby ke kontrole |", "|---|---|---|---|---|---|---|",
    ]
    for path, s in m["per_field"].items():
        errs = s["wrong"] + s["false_missing"] + s["false_filled"]
        out.append(f"| {LABELS[path]} | {s['n']} | {s['correct']} | {s['wrong']} | {s['false_missing']} | {s['false_filled']} | "
                   f"{_pct(s['errors_flagged'], errs) if errs else '–'} |")
    for patient in result["patients"]:
        for run in range(1, result["runs"] + 1):
            rows = [r for r in result["rows"] if r["patient"] == patient and r["run"] == run]
            out += ["", f"## {patient} – běh {run}",
                    "| pole | gold | aplikace | jistota | stav | výsledek |", "|---|---|---|---|---|---|"]
            for r in rows:
                state = r["state"] + (" ⚠ rozpor" if r["conflict"] else "") + (" → ke kontrole" if r["flagged"] else "")
                gold = _cell(r["gold"]) + (f" ({r['gold_status']})" if r["gold_status"] not in ("explicit", None) else "")
                out.append(f"| {r['label']} | {gold} | {_cell(r['app'])} | {_cell(r['confidence'])} | {state} | {OUTCOME[r['outcome']]} |")
            w = next(x for x in result["warnings"] if x["patient"] == patient and x["run"] == run)
            out += ["", "| očekávané varování | nalezeno |", "|---|---|"]
            out += [f"| {e['desc']} | {e['found'] or '✗ ne'} |" for e in w["expected"]]
            out += ["", "Vydaná varování:"] + [f"- {x}" for x in w["produced"]] + ([] if w["produced"] else ["- (žádná)"])
    if result["variance"]:
        out += ["", "## Rozdíly mezi běhy", "| pacient | pole | hodnota po bězích | jistota a stav po bězích |", "|---|---|---|---|"]
        out += [f"| {v['patient']} | {LABELS[v['path']]} | {' / '.join(v['values'])} | {' / '.join(v['scores'])} |"
                for v in result["variance"]]
    return "\n".join(out) + "\n"


def compare(before: dict, after: dict) -> str:
    a, b = before["metrics"], after["metrics"]

    def acc(s):
        return f"{s['correct']}/{s['n']}" if s else "–"

    out = [f"# Srovnání evaluace: {before['stamp']} → {after['stamp']}", "",
           "| metrika | před | po |", "|---|---|---|",
           f"| přesnost | {_pct(a['correct'], a['scored'])} | {_pct(b['correct'], b['scored'])} |",
           f"| chybná hodnota | {a['wrong']} | {b['wrong']} |",
           f"| falešně chybějící | {a['false_missing']} | {b['false_missing']} |",
           f"| falešně vyplněné | {a['false_filled']} | {b['false_filled']} |",
           f"| záchyt chyb | {_pct(a['errors_flagged'], a['errors'])} | {_pct(b['errors_flagged'], b['errors'])} |",
           f"| přijato automaticky | {_pct(a['auto'], a['scored'])} | {_pct(b['auto'], b['scored'])} |",
           f"| přesnost automaticky přijatých | {_pct(a['auto_correct'], a['auto'])} | {_pct(b['auto_correct'], b['auto'])} |",
           "", "| pole | před (správně/hodnoceno) | po |", "|---|---|---|"]
    for path, label in FIELDS:
        pa, pb = a["per_field"].get(path), b["per_field"].get(path)
        if pa or pb:
            out.append(f"| {label} | {acc(pa)} | {acc(pb)} |")
    return "\n".join(out) + "\n"


def template(patient_dir: Path) -> dict:
    """Empty gold for a clinician to fill in (no app values, so the AI output does not anchor the reference)."""
    return {
        "patient": patient_dir.name,
        "documents_dir": str(patient_dir),
        "fields": {path: {"value": None, "status": "todo", "note": label} for path, label in FIELDS},
        "warnings": [],
    }


def main(argv: list[str] | None = None) -> None:
    from app.config import get_settings

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gold", type=Path, default=None, help="folder with gold JSON files (default EVAL_GOLD_DIR)")
    ap.add_argument("--only", nargs="*", help="patients to evaluate")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--fresh-cache", action="store_true", help="every run with its own empty LLM cache (measures variance)")
    ap.add_argument("--out", type=Path, default=None, help="output folder (default backend/var/eval)")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--template", nargs=2, type=Path, metavar=("PATIENT_DIR", "OUT_JSON"))
    ap.add_argument("--render", type=Path, metavar="RESULT_JSON", help="rebuild metrics and the report from a saved run")
    args = ap.parse_args(argv)

    if args.render:
        result = json.loads(args.render.read_text(encoding="utf-8"))
        result["metrics"], result["variance"] = metrics(result["rows"]), run_variance(result["rows"])
        args.render.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        report = markdown(result)
        args.render.with_suffix(".md").write_text(report, encoding="utf-8")
        print(report)
        return
    if args.compare:
        before, after = (json.loads(p.read_text(encoding="utf-8")) for p in args.compare)
        print(compare(before, after))
        return
    if args.template:
        args.template[1].write_text(json.dumps(template(args.template[0]), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.template[1]}")
        return

    settings = get_settings()
    gold_dir = args.gold or Path(settings.eval_gold_dir)
    golds = load_gold(gold_dir, args.only)
    if not golds:
        sys.exit(f"no gold JSON in {gold_dir}")
    out_dir = args.out or settings.data_dir / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    result = evaluate(golds, args.runs, args.fresh_cache, out_dir, stamp)
    report = markdown(result)
    (out_dir / f"eval-{stamp}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (out_dir / f"eval-{stamp}.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"saved {out_dir / f'eval-{stamp}.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
