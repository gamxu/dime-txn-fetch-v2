"""
Fetch gold transaction confirmations from Gmail (YLG and MTS).

Parses the email body (not an attachment) and returns a DataFrame
with the same schema as the stock/ETF trades.

Usage:
    python tool/gmail_gold_fetch.py             # print fetched rows
    python tool/gmail_gold_fetch.py --csv       # save to output/gold_raw.csv
"""

import imaplib
import email
import email.header
import email.message
import email.utils
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import os
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

_YLG_SENDER = "goldportplus@ylgcorporation.co.th"
_MTS_SENDER = "noreply@mtsgoldgroup.com"


# ---------- helpers ----------

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        s = data.strip()
        if s:
            self._parts.append(s)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _html_to_text(html_str: str) -> str:
    p = _TextExtractor()
    p.feed(html_str)
    return p.get_text()


def _get_body(msg: email.message.Message) -> str:
    """Return the best plain-text representation of the email body."""
    plain = html_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ct == "text/plain" and not plain:
                plain = decoded
            elif ct == "text/html" and not html_body:
                html_body = decoded
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace") if payload else ""
        if msg.get_content_type() == "text/html":
            html_body = decoded
        else:
            plain = decoded

    return plain if plain.strip() else _html_to_text(html_body)


def _decode_subject(header: str) -> str:
    parts = []
    for raw, charset in email.header.decode_header(header):
        if isinstance(raw, bytes):
            parts.append(raw.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(raw)
    return " ".join(parts)


def _clean_num(s: str) -> float:
    return float(s.replace(",", "")) if s else 0.0


def _iso_to_dmy(iso_date: str) -> str:
    """Convert 2026-06-26 → 26/06/2026."""
    y, mo, d = iso_date.split("-")
    return f"{d}/{mo}/{y}"


# ---------- parsers ----------

def _parse_ylg(body: str, subject: str) -> dict | None:
    order_m  = re.search(r"หมายเลขคำสั่ง[^:]*:\s*(DM\w+)", body)
    date_m   = re.search(r"วันที่ทำรายการ\s*:\s*(\d{2}/\d{2}/\d{4})", body)
    symbol_m = re.search(r"รหัสสินค้า\s*:\s*(\w+)", body)
    qty_m    = re.search(r"จำนวนทอง[^:]*:\s*([\d.]+)", body)
    price_m  = re.search(r"ราคาต่อหน่วย[^:]*:\s*([\d,]+\.?\d*)", body)
    amount_m = re.search(r"จำนวนเงิน\s*:\s*([\d,]+\.?\d*)\s*USD", body)

    if not all([order_m, date_m, symbol_m, qty_m, price_m, amount_m]):
        return None

    side = "SELL" if "สั่งขาย" in subject else "BUY"
    gross_usd = _clean_num(amount_m.group(1))

    return {
        "order_no":  order_m.group(1),
        "date":      date_m.group(1),
        "side":      side,
        "symbol":    symbol_m.group(1),
        "market":    "YLGGOLD",
        "qty":       _clean_num(qty_m.group(1)),
        "qty_unit":  "OZ",
        "price":     _clean_num(price_m.group(1)),
        "currency":  "USD",
        "gross_usd": gross_usd,
        "fee_usd":   0.0,
        "wht_usd":   0.0,
        "net_usd":   gross_usd,
        "gross_thb": 0.0,
        "fee_thb":   0.0,
        "wht_thb":   0.0,
        "net_thb":   0.0,
        "source":    "ylg_email",
    }


def _parse_mts(body: str, subject: str) -> dict | None:
    order_m = re.search(r"เลขที่\s*:?\s*(DM\w+)", body)
    date_m  = re.search(r"วันที่(?:ซื้อ|ขาย)\s*:?\s*(\d{4}-\d{2}-\d{2})", body)
    # Table row: GLDOZUSD  0.0007  OZ  4,044.88  2.84  USD
    row_m   = re.search(
        r"(GLD\w+)\s+([\d.]+)\s*OZ\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s*USD",
        body,
    )

    if not all([order_m, date_m, row_m]):
        return None

    side = "SELL" if "สั่งขาย" in subject else "BUY"
    gross_usd = _clean_num(row_m.group(4))

    return {
        "order_no":  order_m.group(1),
        "date":      _iso_to_dmy(date_m.group(1)),
        "side":      side,
        "symbol":    row_m.group(1),
        "market":    "MTSGOLD",
        "qty":       _clean_num(row_m.group(2)),
        "qty_unit":  "OZ",
        "price":     _clean_num(row_m.group(3)),
        "currency":  "USD",
        "gross_usd": gross_usd,
        "fee_usd":   0.0,
        "wht_usd":   0.0,
        "net_usd":   gross_usd,
        "gross_thb": 0.0,
        "fee_thb":   0.0,
        "wht_thb":   0.0,
        "net_thb":   0.0,
        "source":    "mts_email",
    }


# ---------- fetcher ----------

def _fetch_from_sender(
    imap: imaplib.IMAP4_SSL,
    sender: str,
    parser_fn,
    label: str,
    subject_filter,
) -> list[dict]:
    rows: list[dict] = []
    _, data = imap.search(None, f'(FROM "{sender}")')
    msg_ids = data[0].split()
    tqdm.write(f"  {label}: {len(msg_ids)} emails found")

    for mid in tqdm(msg_ids, desc=f"  Parsing {label}", unit="email", leave=False):
        _, hdr_data = imap.fetch(mid, "(BODY[HEADER.FIELDS (SUBJECT)])")
        hdr_msg = email.message_from_bytes(hdr_data[0][1])
        subject = _decode_subject(hdr_msg.get("Subject", ""))

        if not subject_filter(subject):
            continue

        _, raw = imap.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(raw[0][1])
        body = _get_body(msg)
        row = parser_fn(body, subject)
        if row:
            rows.append(row)
        else:
            tqdm.write(f"    skip (parse failed): {subject[:60]}")

    return rows


def fetch_gold_transactions() -> pd.DataFrame:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"]

    all_rows: list[dict] = []
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(gmail_user, gmail_pass)
        imap.select("INBOX", readonly=True)

        all_rows.extend(_fetch_from_sender(
            imap, _YLG_SENDER, _parse_ylg, "YLG Gold",
            subject_filter=lambda s: "[ YLG GOLD ]" in s and "DIME" in s,
        ))
        all_rows.extend(_fetch_from_sender(
            imap, _MTS_SENDER, _parse_mts, "MTS Gold",
            subject_filter=lambda s: "[MTS Gold]" in s and ("สั่งซื้อ" in s or "สั่งขาย" in s),
        ))

    df = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
    print(f"Gold transactions fetched: {len(df)}")
    return df


if __name__ == "__main__":
    df = fetch_gold_transactions()
    if "--csv" in sys.argv and not df.empty:
        out = PROJECT_ROOT / "output" / "gold_raw.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"Saved -> {out}")
    elif not df.empty:
        print(df.to_string())
