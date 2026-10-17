"""Audit log of what people do with a case: who changed which field of the report, when, old -> new value.

Entries are stored in InterSystems IRIS, SQL table Nor.Audit in the FHIRSERVER namespace (next to the FHIR server and
Nor.Chunk / Nor.Code). When IRIS is not reachable the entries go to backend/var/audit/<case>.jsonl and are moved to
IRIS the next time it is up, so nothing is lost and editing never waits for the database.

The diff is computed here, on the server, from the stored report and the one being saved, so every way of changing
a report (review queue, form preview, relapse tab) is logged the same way.
"""

from __future__ import annotations

import json
import socket
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import unquote

from app import iris_db
from app.config import get_settings
from app.confidence import iter_fields
from app.models import Extracted, FieldStatus, NorReport, ReviewState

TABLE = "Nor.Audit"
COLUMNS = (
    "EntryId VARCHAR(36), CaseId VARCHAR(64), AtUtc VARCHAR(40), Actor VARCHAR(200), Kind VARCHAR(40), "
    "FieldPath VARCHAR(100), FieldLabel VARCHAR(200), OldValue VARCHAR(2000), NewValue VARCHAR(2000)"
)
_COLS = "EntryId, CaseId, AtUtc, Actor, Kind, FieldPath, FieldLabel, OldValue, NewValue"
UNKNOWN_ACTOR = "neuvedený uživatel"
SYSTEM_ACTOR = "AI NOR (při spuštění)"  # catching up FHIR records at startup

# Kind of entry (the frontend shows Czech labels)
FILLED = "filled"  # empty / missing field got a value
CHANGED = "changed"  # value overwritten
RESOLVED = "resolved"  # conflict between documents resolved by picking a value
CONFIRMED = "confirmed"  # value confirmed as it is
CONFIRMED_MISSING = "confirmed_missing"  # mandatory field confirmed as not documented
REJECTED = "rejected"  # value rejected
REMOVED = "removed"  # value or list item (e.g. a relapse) removed
CASE_CREATED, EXTRACTED, PATIENT, REPORT_CONFIRMED, FHIR_SUBMITTED, FHIR_FAILED, EXPORTED, NIS_IMPORTED = (
    "case_created", "extracted", "patient_changed", "report_confirmed", "fhir_submitted", "fhir_failed", "exported", "nis_imported")

LABELS = {
    "diagnosis_date": "Datum stanovení diagnózy", "diagnosis_basis": "K dg. vedla vyšetření", "laterality": "Lateralita",
    "icd10": "Dg. MKN", "topography": "Topografie", "morphology_type": "Typ morfologie", "morphology_code": "Kód morfologie",
    "grade": "Grading", "morphology_name": "Název morfologie", "tnm_clinical.t": "T", "tnm_clinical.n": "N",
    "tnm_clinical.m": "M", "tnm_pathological.t": "pT", "tnm_pathological.n": "pN", "tnm_pathological.m": "pM",
    "pn_examined": "pN vyš.", "pn_positive": "pN poz.", "sentinel_node": "sn", "metastasis_sites": "Lokalizace vzdálených metastáz",
    "clinical_stage": "Klinické stádium", "disease_extent": "Onemocnění", "patient_ref": "Pacient RČ",
    "form.zarizeni": "Zařízení (pracoviště)", "form.oddeleni": "Oddělení", "form.neznamo": "Neznámo (bezdomovec, neudaný pobyt)",
    "form.cizinec": "Cizinec", "form.zeme_puvodu": "Země původu", "form.identifikace_specifickych_dg": "Identifikace specifických diagnóz",
    "form.skupina": "Skupina", "form.rizikova_kategorie": "Riziková kategorie", "form.serove_markery": "Sérové nádorové markery",
    "form.p16": "p16 pozitivní", "form.pracoviste_hlasici_novotvar": "Pracoviště hlásící novotvar",
}
_SUB = {"status": "událost", "date": "datum", "sites": "lokalizace", "result": "výsledek", "description": "popis",
        "start": "začátek", "end": "konec", "intent": "záměr"}
_LIST = {"progression": "Relaps", "treatments": "Léčba", "biomarkers": "Biomarker"}
_LATERALITY = {"right": "vpravo", "left": "vlevo", "bilateral": "oboustranně", "midline": "střed",
               "not_applicable": "odpadá", "unknown": "neznámo"}
_PROGRESSION = {"recurrence": "recidiva", "progression": "progrese", "remission": "remise", "stable": "stabilní"}


@dataclass
class Entry:
    id: str
    case_id: str
    at: str  # ISO 8601 UTC
    actor: str
    kind: str
    path: str | None = None
    label: str | None = None
    old: str | None = None
    new: str | None = None
    storage: str = "local"  # iris | local (where the entry is now)


def actor_from_header(value: str | None) -> str:
    """X-Actor header: URL-encoded so names with diacritics survive HTTP headers."""
    name = unquote(value or "").strip()
    return name[:200] or UNKNOWN_ACTOR


def label(path: str) -> str:
    if path in LABELS:
        return LABELS[path]
    if "[" in path:  # progression[0].date -> Relaps 1: datum
        head, rest = path.split("[", 1)
        index, sub = rest.split("].", 1)
        return f"{_LIST.get(head, head)} {int(index) + 1}: {_SUB.get(sub, sub)}"
    return path


def show(value, path: str = "") -> str | None:
    """Human-readable value as the form shows it."""
    if value is None:
        return None
    if isinstance(value, dict) and "year" in value:
        return ". ".join(str(x) for x in (value.get("day"), value.get("month"), value["year"]) if x)
    if isinstance(value, list):
        return " + ".join(str(v) for v in value) if value else "žádné"
    if path == "laterality":
        return _LATERALITY.get(str(value), str(value))
    if path.endswith("].status") and path.startswith("progression"):
        return _PROGRESSION.get(str(value), str(value))
    return str(value)


def _value(f: Extracted):
    """Plain JSON value (dates as dicts, enums as their values); None when the field is missing."""
    return None if f.status == FieldStatus.missing else f.model_dump(mode="json")["value"]


def diff(old: NorReport, new: NorReport) -> list[tuple[str, str, str | None, str | None]]:
    """What the person changed: [(kind, path, old shown, new shown)]. Confidence / AI bookkeeping is ignored."""
    before, after = dict(iter_fields(old)), dict(iter_fields(new))
    out = []
    for path, f in after.items():
        o = before.get(path, Extracted())
        ov, nv = _value(o), _value(f)
        state, was = f.review.state, o.review.state
        if state == ReviewState.rejected and was != ReviewState.rejected:
            kind = REJECTED
        elif ov != nv:
            kind = REMOVED if nv is None else FILLED if ov is None else RESOLVED if o.status == FieldStatus.conflict else CHANGED
        elif o.status == FieldStatus.conflict and f.status != FieldStatus.conflict:
            kind = RESOLVED
        elif state == ReviewState.confirmed and was != ReviewState.confirmed:
            kind = CONFIRMED_MISSING if f.status == FieldStatus.missing else CONFIRMED
        else:
            continue
        same = kind in (CONFIRMED, CONFIRMED_MISSING)  # nothing changed hands: only the confirmed value is shown
        out.append((kind, path, None if same else show(ov, path), show(nv, path)))
    for path in sorted(before.keys() - after.keys()):  # list items removed (a relapse deleted)
        if (ov := _value(before[path])) is not None:
            out.append((REMOVED, path, show(ov, path), None))
    return out


# ---------- storage ----------

_down_until = 0.0  # don't retry IRIS before this time (a refused connection takes ~4 s on Windows)
_table_ready = False


def _iris_up() -> bool:
    global _down_until
    if time.monotonic() < _down_until:
        return False
    s = get_settings()
    try:
        with socket.create_connection((s.iris_host, s.iris_port), timeout=0.3):
            return True
    except OSError:
        _down_until = time.monotonic() + 30
        return False


def _mark_down() -> None:
    global _down_until
    _down_until = time.monotonic() + 30


def _ensure_table(cur) -> None:
    global _table_ready
    if not _table_ready:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} ({COLUMNS})")
        _table_ready = True


def _local_path(case_id: str):
    d = get_settings().data_dir / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{case_id}.jsonl"


def _local_read(case_id: str) -> list[Entry]:
    path = _local_path(case_id)
    if not path.exists():
        return []
    return [Entry(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _row(e: Entry) -> list:
    return [e.id, e.case_id, e.at, e.actor, e.kind, e.path, e.label, e.old, e.new]


def _iris_insert(entries: list[Entry]) -> None:
    with iris_db.cursor() as cur:
        _ensure_table(cur)
        cur.executemany(f"INSERT INTO {TABLE} ({_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [_row(e) for e in entries])


def _flush_local(case_id: str) -> None:
    """Move entries written while IRIS was down into IRIS."""
    backlog = _local_read(case_id)
    if backlog:
        _iris_insert(backlog)
        _local_path(case_id).unlink()


def write(entries: list[Entry]) -> str:
    """Store entries; returns where they went (iris | local). Never raises: the edit itself must not fail on the log."""
    if not entries:
        return "none"
    if _iris_up():
        try:
            _flush_local(entries[0].case_id)
            _iris_insert(entries)
            return "iris"
        except Exception:  # noqa: BLE001 - any DB error falls back to the local file
            _mark_down()
    with _local_path(entries[0].case_id).open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    return "local"


def read(case_id: str) -> tuple[list[Entry], bool]:
    """All entries of a case, oldest first, and whether IRIS was reachable."""
    entries: list[Entry] = []
    up = _iris_up()
    if up:
        try:
            _flush_local(case_id)
            with iris_db.cursor() as cur:
                _ensure_table(cur)
                cur.execute(f"SELECT {_COLS} FROM {TABLE} WHERE CaseId = ?", [case_id])
                entries = [Entry(*row, storage="iris") for row in cur.fetchall()]
        except Exception:  # noqa: BLE001
            _mark_down()
            up = False
    entries += [Entry(**{**asdict(e), "storage": "local"}) for e in _local_read(case_id)]
    return sorted(entries, key=lambda e: e.at), up


def latest(kind: str) -> dict[str, Entry]:
    """Newest entry of one kind per case (e.g. the last export of every report), from IRIS and the local backup."""
    found: list[Entry] = []
    if _iris_up():
        try:
            with iris_db.cursor() as cur:
                _ensure_table(cur)
                cur.execute(f"SELECT {_COLS} FROM {TABLE} WHERE Kind = ?", [kind])
                found = [Entry(*row, storage="iris") for row in cur.fetchall()]
        except Exception:  # noqa: BLE001
            _mark_down()
    folder = get_settings().data_dir / "audit"
    for path in folder.glob("*.jsonl") if folder.exists() else []:
        found += [e for e in _local_read(path.stem) if e.kind == kind]
    out: dict[str, Entry] = {}
    for e in sorted(found, key=lambda e: e.at):
        out[e.case_id] = e
    return out


def log(case_id: str, actor: str, kind: str, path: str | None = None, old: str | None = None, new: str | None = None) -> str:
    return write([entry(case_id, actor, kind, path, old, new)])


def entry(case_id: str, actor: str, kind: str, path: str | None = None, old: str | None = None, new: str | None = None) -> Entry:
    return Entry(id=str(uuid.uuid4()), case_id=case_id, at=datetime.now(timezone.utc).isoformat(), actor=actor, kind=kind,
                 path=path, label=label(path) if path else None, old=old, new=new)


def log_report_changes(case_id: str, actor: str, old: NorReport, new: NorReport) -> str:
    return write([entry(case_id, actor, kind, path, o, n) for kind, path, o, n in diff(old, new)])
