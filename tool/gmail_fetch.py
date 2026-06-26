"""
Step 1 — Download Dime confirmation PDFs from Gmail via IMAP.

Usage:
    python tool/gmail_fetch.py                  # download PDFs
    python tool/gmail_fetch.py --list-subjects  # print subjects only (debug)

Reads credentials from .env at project root.
Saves PDFs to inbox/raw/ with a timestamp prefix so filenames never collide.
"""

import imaplib
import email
import email.message
import email.utils
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

INBOX_RAW = PROJECT_ROOT / "inbox" / "raw"
INBOX_RAW.mkdir(parents=True, exist_ok=True)

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SENDER_FILTER = '(FROM "dime.co.th")'
CONFIRMATION_KEYWORD = "Confirmation Note"


def _decode_subject(subject_header: str) -> str:
    parts = []
    for raw, charset in email.header.decode_header(subject_header):
        if isinstance(raw, bytes):
            parts.append(raw.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(raw)
    return " ".join(parts)


def _date_prefix(msg: email.message.Message) -> str:
    try:
        ts = email.utils.parsedate_to_datetime(msg.get("Date", ""))
        return ts.strftime("%Y%m%d_%H%M%S")
    except Exception:
        return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_pdf_parts(msg: email.message.Message, prefix: str) -> list[Path]:
    saved: list[Path] = []
    for part in msg.walk():
        filename = part.get_filename() or ""
        is_pdf = part.get_content_type() == "application/pdf" or filename.lower().endswith(".pdf")
        if not is_pdf:
            continue
        safe_name = re.sub(r"[^\w.\-]", "_", filename) or "attachment.pdf"
        dest = INBOX_RAW / f"{prefix}_{safe_name}"
        if dest.exists():
            tqdm.write(f"  skip: {dest.name}")
        else:
            dest.write_bytes(part.get_payload(decode=True))
            tqdm.write(f"  saved: {dest.name}")
        saved.append(dest)
    return saved


def _connect() -> tuple[imaplib.IMAP4_SSL, list[bytes]]:
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    imap.select("INBOX", readonly=True)
    _, data = imap.search(None, SENDER_FILTER)
    msg_ids = data[0].split()
    print(f"Found {len(msg_ids)} emails from dime.co.th")
    return imap, msg_ids


def list_subjects() -> None:
    """Print every subject from dime.co.th emails — useful for debugging."""
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, SENDER_FILTER)
        msg_ids = data[0].split()
        print(f"Found {len(msg_ids)} emails from dime.co.th")
        for mid in tqdm(msg_ids, desc="Reading subjects", unit="email"):
            _, hdr_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT)])")
            hdr_msg = email.message_from_bytes(hdr_data[0][1])
            tqdm.write(_decode_subject(hdr_msg.get("Subject", "(no subject)")))


def fetch_pdfs(since_date: date | None = None) -> list[Path]:
    saved: list[Path] = []

    search = SENDER_FILTER
    if since_date:
        search = f'(FROM "dime.co.th" SINCE "{since_date.strftime("%d-%b-%Y")}")'

    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        imap.select("INBOX", readonly=True)
        _, data = imap.search(None, search)
        msg_ids = data[0].split()
        print(f"Found {len(msg_ids)} emails from dime.co.th")

        for mid in tqdm(msg_ids, desc="Scanning headers", unit="email"):
            _, hdr_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT DATE)])")
            hdr_msg = email.message_from_bytes(hdr_data[0][1])
            subject = _decode_subject(hdr_msg.get("Subject", ""))
            if CONFIRMATION_KEYWORD not in subject:
                continue
            _, raw = imap.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            saved.extend(_save_pdf_parts(msg, _date_prefix(msg)))

    print(f"\nTotal new PDFs downloaded: {len(saved)}")
    return saved


if __name__ == "__main__":
    if "--list-subjects" in sys.argv:
        list_subjects()
    else:
        fetch_pdfs()
