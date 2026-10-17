"""Play the hospital information system (NIS) for the demo: send synthetic reports into IRIS FHIR for AI NOR.

Each report becomes a DocumentReference tagged urn:ai-nor:inbox|nis, which is what the NIS (or an IRIS interoperability
production translating its HL7v2 MDM messages) would store. They appear in the tab Nový pacient → Zprávy z NIS.
Run (from backend/, IRIS running): .venv/Scripts/python -m scripts.nis_demo_send
Only fictional data (data/synthetic + texts below), never real patients.
"""

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path

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
