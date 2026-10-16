"""Create the FHIRSERVER namespace, an empty FHIR R4 endpoint /fhir/r4 and the app SQL tables.

Run once after `docker compose up -d` (from backend/): .venv/Scripts/python -m scripts.setup_iris [--reset]
--reset drops and recreates the app tables (needed after changing EMBEDDING_DIM).
Adapted from FHIR-AI-Hackathon-Kit fhir_server_setup_native.py (MIT), see PREEXISTING.md.
"""

import sys

import iris

from app import iris_db
from app.config import get_settings

ENDPOINT = "/fhir/r4"


def connect(namespace: str):
    s = get_settings()
    conn = iris.createConnection(s.iris_host, s.iris_port, namespace, s.iris_user, s.iris_password)
    return conn, iris.createIRIS(conn)


def create_fhir_server() -> None:
    ns = get_settings().iris_namespace
    conn, irispy = connect("HSLIB")
    try:
        if not irispy.classMethodBoolean("%SYS.Namespace", "Exists", ns):
            print(f"creating namespace {ns} (takes a minute)")
            irispy.classMethodVoid("HS.Util.Installer.Foundation", "Install", ns)
    finally:
        conn.close()

    conn, irispy = connect(ns)
    try:
        if irispy.classMethodBoolean("HS.FHIRServer.ServiceInstance", "ExistsByUrl", ENDPOINT):
            print(f"FHIR server {ENDPOINT} already exists")
            return
        print(f"creating FHIR R4 server {ENDPOINT}")
        irispy.classMethodVoid("HS.FHIRServer.Installer", "InstallNamespace")
        irispy.classMethodVoid(
            "HS.FHIRServer.Installer",
            "InstallInstance",
            ENDPOINT,
            "HS.FHIRServer.Storage.JsonAdvSQL.InteractionsStrategy",
            "hl7.fhir.r4.core@4.0.1",
        )
    finally:
        conn.close()


TABLES = {
    # document chunks for vector search (citations); offsets point into Document.text
    "Nor.Chunk": "CaseId VARCHAR(64), DocId VARCHAR(64), StartPos INTEGER, EndPos INTEGER, Text VARCHAR(8000)",
    # code lists (MKN-10, ICD-O-3 morphology) for semantic code lookup, see app/retrieval/codes.py
    "Nor.Code": "System VARCHAR(20), Code VARCHAR(20), Name VARCHAR(500)",
    # MKN-10 coding rules from the PDF Tabelární část (categories + notes), see app/retrieval/rules.py
    "Nor.Rule": "Kind VARCHAR(20), Code VARCHAR(20), Title VARCHAR(500), Text VARCHAR(8000), Page INTEGER",
}


def create_tables(reset: bool = False) -> None:
    """Create app tables. Vector dimension = EMBEDDING_DIM; after changing the model run with --reset."""
    dim = get_settings().embedding_dim
    with iris_db.cursor() as cur:
        for table, cols in TABLES.items():
            if reset:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols}, Embedding VECTOR(DOUBLE, {dim}))")
            print(f"table {table} ready (VECTOR {dim})")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    create_fhir_server()
    create_tables(reset=reset)
