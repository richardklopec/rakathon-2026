"""Parse the MKN-10 PDF Tabelární část into rule entries and load them into IRIS (Nor.Rule) with local embeddings.

Usage (from backend/): .venv/Scripts/python -m scripts.index_rules
Needs the Nor.Rule table: .venv/Scripts/python -m scripts.setup_iris (creates missing tables, no --reset needed).
"""

import time

from app.retrieval.rules import index_rules

t = time.time()
print(f"indexed {index_rules()} in {time.time() - t:.0f} s")
