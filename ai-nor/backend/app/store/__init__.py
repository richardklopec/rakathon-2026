"""Case storage in InterSystems IRIS: SQL table Nor.CaseRecord in the FHIRSERVER namespace, one row per case.

The row holds the whole Case as JSON (documents, report with evidence and review state, FHIR record). The clinical
record of the case lives next to it in the IRIS FHIR server (app/fhir/sync.py). Case files from the earlier JSON
storage (backend/var/cases) are moved into IRIS once, at startup (migrate_files).
"""

import shutil

from app import iris_db
from app.config import get_settings
from app.models import Case

TABLE = "Nor.CaseRecord"
COLUMNS = "CaseId VARCHAR(64) NOT NULL PRIMARY KEY, PatientRef VARCHAR(200), UpdatedAt VARCHAR(40), Data LONGVARCHAR"
COMPUTED = {"ai_confidence", "document_rc"}  # derived on output, not stored


class Unavailable(RuntimeError):
    """IRIS is not reachable: cases can be neither read nor saved."""


class _Iris:
    ready = False

    def _run(self, sql: str, params: list | None = None, fetch: bool = False):
        try:
            with iris_db.cursor() as cur:
                if not self.ready:
                    cur.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} ({COLUMNS})")
                    type(self).ready = True
                cur.execute(sql, params or [])
                return cur.fetchall() if fetch else None
        except Exception as e:  # noqa: BLE001 - connection refused, timeout, SQL error
            raise Unavailable(f"IRIS neodpovídá ({e})") from e

    def put(self, case: Case) -> None:
        self._run(f"INSERT OR UPDATE INTO {TABLE} (CaseId, PatientRef, UpdatedAt, Data) VALUES (?, ?, ?, ?)",
                  [case.id, case.patient_ref, case.updated_at.isoformat(), case.model_dump_json(exclude=COMPUTED)])

    def get(self, case_id: str) -> str | None:
        rows = self._run(f"SELECT Data FROM {TABLE} WHERE CaseId = ?", [case_id], fetch=True)
        return rows[0][0] if rows else None

    def all(self) -> list[str]:
        return [r[0] for r in self._run(f"SELECT Data FROM {TABLE} ORDER BY UpdatedAt DESC", fetch=True)]


class Memory(dict):
    """In-process storage for tests (no IRIS)."""

    def put(self, case: Case) -> None:
        self[case.id] = case.model_dump_json(exclude=COMPUTED)

    def get(self, case_id: str) -> str | None:  # type: ignore[override]
        return dict.get(self, case_id)

    def all(self) -> list[str]:
        return list(self.values())


backend: _Iris | Memory = _Iris()


def save(case: Case) -> Case:
    backend.put(case)
    return case


def load(case_id: str) -> Case | None:
    data = backend.get(case_id)
    return Case.model_validate_json(data) if data else None


def list_cases() -> list[Case]:
    return [Case.model_validate_json(d) for d in backend.all()]


def migrate_files() -> int:
    """Move cases saved as JSON files (backend/var/cases, before IRIS) into IRIS; the folder is kept as a backup."""
    folder = get_settings().data_dir / "cases"
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    moved = 0
    for path in files:
        case = Case.model_validate_json(path.read_text(encoding="utf-8"))
        if backend.get(case.id) is None:  # a case already in IRIS is newer than its old file
            save(case)
            moved += 1
    if files:
        backup = folder.with_name("cases-presunuto-do-iris")
        while backup.exists():
            backup = backup.with_name(backup.name + "-")
        shutil.move(str(folder), str(backup))
    return moved
