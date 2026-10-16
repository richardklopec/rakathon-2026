"""The only place that talks to the IRIS FHIR server."""

import httpx

from app.config import get_settings


def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        base_url=s.fhir_base_url,
        auth=(s.iris_user, s.iris_password),
        headers={"Accept": "application/fhir+json", "Content-Type": "application/fhir+json"},
        timeout=30,
    )


def is_up() -> bool:
    try:
        with _client() as c:
            return c.get("metadata").status_code == 200
    except httpx.HTTPError:
        return False


def post_transaction(bundle: dict) -> dict:
    """POST a transaction Bundle. Raises with the OperationOutcome text on 4xx/5xx."""
    with _client() as c:
        res = c.post("", json=bundle)
        if res.status_code >= 400:
            raise RuntimeError(f"FHIR {res.status_code}: {res.text}")
        return res.json()


def search(resource: str, **params) -> dict:
    with _client() as c:
        res = c.get(resource, params=params)
        res.raise_for_status()
        return res.json()
