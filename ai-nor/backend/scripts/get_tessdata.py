"""Download Tesseract language data (Czech + English, 'fast' models) for OCR of scans into backend/var/tessdata.

Run once (from backend/): .venv/Scripts/python -m scripts.get_tessdata
Source: the official tesseract-ocr/tessdata_fast repository (Apache-2.0). PyMuPDF has the OCR engine built in.
"""

import urllib.request

from app.ingest.formats import tessdata_dir

URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{lang}.traineddata"

if __name__ == "__main__":
    folder = tessdata_dir()
    folder.mkdir(parents=True, exist_ok=True)
    for lang in ("ces", "eng"):
        target = folder / f"{lang}.traineddata"
        if target.exists():
            print(f"{target} already there")
            continue
        urllib.request.urlretrieve(URL.format(lang=lang), target)
        print(f"downloaded {target} ({target.stat().st_size // 1024} kB)")
