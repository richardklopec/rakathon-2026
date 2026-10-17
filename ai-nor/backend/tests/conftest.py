"""Tests never write into a running IRIS: cases are kept in memory, FHIR writes are recorded, the audit log goes local."""

import pytest

from app import audit, store
from app.fhir import client


class FakeFhir:
    """Records transaction bundles and answers like the IRIS FHIR server (absolute location, version in the etag)."""

    def __init__(self):
        self.bundles: list[dict] = []
        self.versions: dict[str, int] = {}
        self.down = False

    def post_transaction(self, bundle: dict) -> dict:
        if self.down:
            raise RuntimeError("Connection refused")
        self.bundles.append(bundle)
        out = []
        for e in bundle["entry"]:
            url, method = e["request"]["url"], e["request"]["method"]
            if method == "DELETE":
                self.versions.pop(url, None)
                out.append({"response": {"status": "204"}})
                continue
            url = url.split("?")[0] + "/p1" if "?" in url else url
            self.versions[url] = self.versions.get(url, 0) + 1
            out.append({"response": {"status": "200", "location": f"http://localhost:52773/fhir/r4/{url}",
                                     "etag": f'W/"{self.versions[url]}"'}})
        return {"resourceType": "Bundle", "type": "transaction-response", "entry": out}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(store, "backend", store.Memory())
    monkeypatch.setattr(audit, "_iris_up", lambda: False)
    fake = FakeFhir()
    monkeypatch.setattr(client, "post_transaction", fake.post_transaction)
    return fake


@pytest.fixture
def fhir(isolated) -> FakeFhir:
    return isolated
