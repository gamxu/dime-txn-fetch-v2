"""
Step 2 — Unlock password-protected Dime PDFs with pikepdf.

Usage:
    python tool/decrypt_pdfs.py

Reads PDF_PASSWORD from .env at project root.
Input:  inbox/raw/*.pdf
Output: inbox/decrypted/*.pdf
"""

import os
from pathlib import Path
import pikepdf
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

PDF_PASSWORD = os.environ["PDF_PASSWORD"]

INBOX_RAW = PROJECT_ROOT / "inbox" / "raw"
INBOX_DECRYPTED = PROJECT_ROOT / "inbox" / "decrypted"
INBOX_DECRYPTED.mkdir(parents=True, exist_ok=True)


def decrypt_all() -> list[Path]:
    pdfs = sorted(INBOX_RAW.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found in inbox/raw/")
        return []

    done: list[Path] = []
    for src in tqdm(pdfs, desc="Decrypting PDFs", unit="file"):
        dest = INBOX_DECRYPTED / src.name
        if dest.exists():
            tqdm.write(f"  skip: {src.name}")
            done.append(dest)
            continue
        try:
            with pikepdf.open(src, password=PDF_PASSWORD) as pdf:
                pdf.save(dest)
            tqdm.write(f"  decrypted: {src.name}")
            done.append(dest)
        except pikepdf.PasswordError:
            tqdm.write(f"  ERROR wrong password: {src.name}")
        except Exception as exc:
            tqdm.write(f"  ERROR {src.name}: {exc}")

    print(f"\nDecrypted: {len(done)} / {len(pdfs)}")
    return done


if __name__ == "__main__":
    decrypt_all()
