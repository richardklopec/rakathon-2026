"""Create the FHIRSERVER namespace, an empty FHIR R4 endpoint /fhir/r4, the app SQL tables and the HL7v2 -> FHIR production.

Run once after `docker compose up -d` (from backend/): .venv/Scripts/python -m scripts.setup_iris [--reset]
--reset drops and recreates the app tables (needed after changing EMBEDDING_DIM).
Running it again is safe; it reloads the production classes from infra/iris/src and restarts the production.
Adapted from FHIR-AI-Hackathon-Kit fhir_server_setup_native.py (MIT), see PREEXISTING.md.
"""

import sys

import iris

from app import audit, iris_db, store
from app.config import REPO_ROOT, get_settings

ENDPOINT = "/fhir/r4"
SRC = REPO_ROOT / "infra" / "iris" / "src"  # ObjectScript classes of the production (UDL .cls files)
PRODUCTION = "AINOR.Production"
# HL7 table 0270 document type (TXA-2) -> what the AI NOR inbox shows; Ens lookup table, editable in the portal
DOCUMENT_TYPES = {
    "CN": "Ambulantní zpráva", "DS": "Propouštěcí zpráva", "SP": "Histologie", "OP": "Operační protokol",
    "DI": "Zobrazovací vyšetření", "PN": "Zpráva o výkonu", "HP": "Vstupní vyšetření", "TS": "Překladová zpráva",
    "PR": "Průběžná zpráva", "MDT": "Zápis z MDT",
}


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
        # cases (app/store) and the audit log of the clinicians' changes (app/audit.py); kept on --reset, they are
        # records, not derived data
        for table, cols in ((store.TABLE, store.COLUMNS), (audit.TABLE, audit.COLUMNS)):
            cur.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")
            print(f"table {table} ready")


def _ok(status, what: str) -> None:
    """%Status from the native API: "1" or an error text."""
    if str(status) != "1":
        raise RuntimeError(f"{what}: {status}")


def install_production() -> None:
    """Load the classes from infra/iris/src, fill the document type table and (re)start the production."""
    ns = get_settings().iris_namespace
    conn, irispy = connect(ns)
    try:
        names = []
        for path in sorted(SRC.rglob("*.cls")):
            name = ".".join(path.relative_to(SRC).with_suffix("").parts)
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")  # UDL lines end in CRLF
            _ok(irispy.classMethodValue("%Compiler.UDL.TextServices", "SetTextFromString", ns, name, text), f"load {name}")
            names.append(name)
        _ok(irispy.classMethodValue("%SYSTEM.OBJ", "Compile", ",".join(names), "ck-d"), "compile")
        print(f"classes {', '.join(names)} compiled")
        for code, label in DOCUMENT_TYPES.items():
            irispy.set(label, "^Ens.LookupTable", "AINOR.DocumentType", code)
        print(f"lookup table AINOR.DocumentType ready ({len(DOCUMENT_TYPES)} document types)")
        if irispy.classMethodValue("Ens.Director", "GetActiveProductionName"):
            _ok(irispy.classMethodValue("Ens.Director", "StopProduction", 10, 1), "stop production")
        _ok(irispy.classMethodValue("Ens.Director", "StartProduction", PRODUCTION), "start production")
        _ok(irispy.classMethodValue("Ens.Director", "SetAutoStart", PRODUCTION), "auto start")
        print(f"production {PRODUCTION} running (HL7v2 MLLP on port 2575, starts with IRIS)")
    finally:
        conn.close()


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    create_fhir_server()
    create_tables(reset=reset)
    install_production()
