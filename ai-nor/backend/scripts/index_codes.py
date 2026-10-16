"""Load MKN-10 + ICD-O-3 morphology code lists into IRIS (Nor.Code) with local embeddings.

Usage (from backend/): .venv/Scripts/python -m scripts.index_codes
"""

import time

from app.retrieval.codes import index_codes

t = time.time()
counts = index_codes()
print(f"indexed {counts} in {time.time() - t:.0f} s")
