"""Case storage. JSON files for the MVP; the confirmed report lives in the IRIS FHIR server."""

from app.config import get_settings
from app.models import Case


def _dir():
    d = get_settings().data_dir / "cases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(case: Case) -> Case:
    (_dir() / f"{case.id}.json").write_text(case.model_dump_json(indent=1), encoding="utf-8")
    return case


def load(case_id: str) -> Case | None:
    path = _dir() / f"{case_id}.json"
    return Case.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def list_cases() -> list[Case]:
    return [Case.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(_dir().glob("*.json"))]
