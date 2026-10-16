"""Create the FHIRSERVER namespace, an empty FHIR R4 endpoint /fhir/r4 and the app SQL tables.

Run once after `docker compose up -d` (from backend/): .venv/Scripts/python -m scripts.setup_iris
Adapted from FHIR-AI-Hackathon-Kit fhir_server_setup_native.py (MIT), see PREEXISTING.md.
"""

import iris

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


def create_tables() -> None:
    s = get_settings()
    conn = iris.connect(s.iris_host, s.iris_port, s.iris_namespace, s.iris_user, s.iris_password)
    cur = conn.cursor()
    try:
        # document chunks for vector search (citations); dimension must match EMBEDDING_MODEL
        cur.execute(
            "CREATE TABLE IF NOT EXISTS Nor.Chunk ("
            " CaseId VARCHAR(64), DocId VARCHAR(64), StartPos INTEGER, EndPos INTEGER,"
            f" Text VARCHAR(8000), Embedding VECTOR(DOUBLE, {s.embedding_dim}))"
        )
        print("table Nor.Chunk ready")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    create_fhir_server()
    create_tables()
