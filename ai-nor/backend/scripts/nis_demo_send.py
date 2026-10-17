"""Play the hospital information system (NIS) for the demo: send synthetic reports into IRIS for AI NOR.

Default: each report goes as an HL7v2 MDM^T02 message over MLLP to the IRIS production AINOR.Production (port 2575),
which converts it inside IRIS (HL7v2 -> SDA3 -> FHIR R4) into a DocumentReference tagged urn:ai-nor:inbox|nis.
--fhir skips the production and writes the same DocumentReferences straight into IRIS FHIR.
They appear in the tab Nový pacient → Zprávy z NIS.
Run (from backend/, IRIS running, production installed by scripts.setup_iris):
    .venv/Scripts/python -m scripts.nis_demo_send [--fhir]
Only fictional data (data/synthetic + texts below), never real patients.
"""

import base64
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.fhir import client as fhir
from app.nis import INBOX_CODE, INBOX_SYSTEM, PATIENT_SYSTEM

HISTOLOGY = (Path(__file__).resolve().parents[2] / "data" / "synthetic" / "demo_histologie.txt").read_text(encoding="utf-8")

AMBULANT = """Ambulantní zpráva – onkologická ambulance (FIKTIVNÍ DEMO, žádný reálný pacient)
Pacientka 58 let, odeslána pro nález v levém prsu.
Dg.: C50.4 ZN horního zevního kvadrantu prsu vlevo.
Klinicky cT1c cN0 cM0, bez známek vzdálených metastáz (CT hrudníku a břicha bez patologie).
Histologicky ověřeno core-cut biopsií dne 5. 3. 2026: invazivní karcinom NST, G2.
Doporučení: MDT, následně parciální mastektomie a sentinelová biopsie.
"""

MDT = """Zápis z mezioborové indikační komise (FIKTIVNÍ DEMO)
Pacient 67 let, adenokarcinom rekta, cT3 cN1 cM0, vzdálenost od anu 8 cm.
Histologie z biopsie: adenokarcinom, G2. Dg.: C20.
Doporučení: neoadjuvantní chemoradioterapie, poté restaging a operace.
"""

REPORTS = [
    ("NIS-DEMO-01", "Ambulantní zpráva", "ambulantni_zprava.txt", AMBULANT),
    ("NIS-DEMO-01", "Histologie", "histologie.txt", HISTOLOGY),
    ("NIS-DEMO-02", "Zápis z MDT", "mdt.txt", MDT),
]

# --- HL7v2 MDM^T02 over MLLP (the way a NIS sends documents) ------------------------------------------------------
MLLP_PORT = 2575  # item "NIS HL7v2 MLLP" of AINOR.Production (infra/iris/src/AINOR/Production.cls)
DOCUMENT_TYPES = {"Ambulantní zpráva": "CN", "Histologie": "SP", "Zápis z MDT": "MDT"}  # TXA-2 (HL7 table 0270 + MDT)
PATIENTS = {"NIS-DEMO-01": ("DEMO^Pacientka", "19680101", "F"), "NIS-DEMO-02": ("DEMO^Pacient", "19590101", "M")}  # fictional


def escape(text: str) -> str:
    """HL7v2 escape sequences for the delimiters (the backslash first)."""
    for char, seq in (("\\", "\\E\\"), ("|", "\\F\\"), ("^", "\\S\\"), ("&", "\\T\\"), ("~", "\\R\\")):
        text = text.replace(char, seq)
    return text


def mdm(patient: str, kind: str, title: str, text: str, number: str, now: datetime) -> str:
    """MDM^T02 (new document with content): one OBX TX segment per line of the report."""
    ts = now.strftime("%Y%m%d%H%M%S%z")
    name, birth, sex = PATIENTS[patient]
    code = DOCUMENT_TYPES[kind]
    segments = [
        f"MSH|^~\\&|NIS|FNO|AINOR|FNO|{ts}||MDM^T02^MDM_T02|{number}|P|2.5|||||CZE|UNICODE UTF-8",
        f"EVN|T02|{ts}",
        f"PID|1||{patient}^^^FNO^PI||{name}||{birth}|{sex}",
        "PV1|1|O",
        f"TXA|1|{code}|TX|{ts}||{ts}||||||{number}^NIS||||{title}|AU||AV",
    ] + [f"OBX|{i}|TX|{code}^{escape(kind)}^L||{escape(line)}||||||F" for i, line in enumerate(text.splitlines(), 1)]
    return "\r".join(segments) + "\r"


def send_mllp(messages: list[str], host: str, port: int = MLLP_PORT) -> list[str]:
    """Send the messages over one MLLP connection, as a NIS does, each in its frame and each waiting for its
    acknowledgment; returns the acknowledgment codes (MSA-1: AA / CA = accepted)."""
    codes = []
    with socket.create_connection((host, port), timeout=30) as s:
        for message in messages:
            s.sendall(b"\x0b" + message.encode("utf-8") + b"\x1c\x0d")
            ack = b""
            while not ack.endswith(b"\x1c\x0d"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                ack += chunk
            segments = ack.strip(b"\x0b\x1c\x0d").decode("utf-8", "replace").split("\r")
            msa = next((seg for seg in segments if seg.startswith("MSA|")), "")
            codes.append(msa.split("|")[1] if "|" in msa else "?")
    return codes


# --- the same reports written straight into FHIR (--fhir) ----------------------------------------------------------
def document_reference(patient: str, kind: str, title: str, text: str) -> dict:
    return {
        "resourceType": "DocumentReference",
        "meta": {"tag": [{"system": INBOX_SYSTEM, "code": INBOX_CODE, "display": "AI NOR – ke zpracování"}]},
        "status": "current",
        "type": {"text": kind},
        "subject": {"identifier": {"system": PATIENT_SYSTEM, "value": patient}},
        "date": datetime.now(timezone.utc).isoformat(),
        "description": f"{kind} z NIS (demo)",
        "content": [{"attachment": {"contentType": "text/plain; charset=utf-8", "title": title,
                                    "data": base64.b64encode(text.encode("utf-8")).decode("ascii")}}],
    }


if __name__ == "__main__":
    if "--fhir" in sys.argv:
        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {"fullUrl": f"urn:uuid:{uuid.uuid4()}", "resource": document_reference(*r), "request": {"method": "POST", "url": "DocumentReference"}}
                for r in REPORTS
            ],
        }
        result = fhir.post_transaction(bundle)
        print(f"odesláno {len(result.get('entry', []))} zpráv do IRIS FHIR (DocumentReference, tag {INBOX_SYSTEM}|{INBOX_CODE})")
    else:
        now = datetime.now().astimezone()
        # TXA-12 document number: a new run adds new reports, a report sent again with the same number would update
        messages = [mdm(p, kind, title, text, f"DEMO-{now:%Y%m%d%H%M%S}-{i}", now) for i, (p, kind, title, text) in enumerate(REPORTS, 1)]
        for (patient, kind, _, _), code in zip(REPORTS, send_mllp(messages, get_settings().iris_host)):
            print(f"{kind} ({patient}) → HL7v2 MDM^T02, potvrzení {code}")
        print(f"odesláno {len(REPORTS)} zpráv do IRIS (MLLP port {MLLP_PORT}); produkce AINOR.Production je během pár sekund "
              "převede na FHIR DocumentReference (Management Portal → Interoperability → Messages)")
