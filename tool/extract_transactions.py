"""
Step 3 — Parse decrypted Dime confirmation PDFs into trade rows.

Handles two PDF formats:
  - Stock/ETF (standard Dime): matched by _ROW_RE
  - Mutual Fund (DIMEMF prefix):  matched by _MF_ROW_RE

Usage:
    python tool/extract_transactions.py          # prints preview
    python tool/extract_transactions.py --csv    # writes output/trades_raw.csv
"""

import re
import sys
from pathlib import Path
import pdfplumber
import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DECRYPTED_DIR = PROJECT_ROOT / "inbox" / "decrypted"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_NUM = r"[\d,]+(?:\.\d+)?"

# --- Stock / ETF ---
_ROW_RE = re.compile(
    r"(?P<order_no>\d{5,12})\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<side>BUY|SEL|REW|EXC|EXP)\s+"
    r"(?P<symbol>[A-Z]{1,5}(?:\.[A-Z])?)\s+"
    r"(?P<qty>[\d.]+)\s+"
    r"(?P<price>" + _NUM + r")\s+"
    r"(?P<currency>[A-Z]{3})\s+"
    r"(?P<gross_usd>" + _NUM + r")\s+"
    r"(?P<fee_usd>" + _NUM + r")\s+"
    r"(?P<wht_usd>" + _NUM + r")\s+"
    r"(?P<net_usd>" + _NUM + r")\s+"
    r"\[(?P<market>[A-Z]{3,4})\]\s+"
    r"(?P<gross_thb>" + _NUM + r")\s+"
    r"(?P<fee_thb>" + _NUM + r")\s+"
    r"(?P<wht_thb>" + _NUM + r")\s+"
    r"(?P<net_thb>" + _NUM + r")",
)

# --- Mutual Fund ---
_MF_ROW_RE = re.compile(
    r"(?P<order_no>\d{10,})\s+"
    r"(?P<txtype>SUB|RED|SWI|SWO)\s+"
    r"(?P<symbol>[A-Z0-9]+)\s+"
    r"(?P<qty>[\d.]+)\s+"
    r"(?P<price>[\d.]+)\s+"
    r"(?P<gross_thb>" + _NUM + r")\s+"
    r"(?P<fee_thb>" + _NUM + r")",
)

# --- Card section (both PDF types) ---
_ACCOUNT_NO_RE = re.compile(r"Account No\.\s+(\d+)")
_EFFECTIVE_DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+\d{2}/\d{2}/\d{4}\s+Effective Date")


def _clean_num(s: str) -> float:
    return float(s.replace(",", "")) if s else 0.0


_SIDE_MAP = {
    "SEL": "SELL",
    "REW": "REWARD",
    "EXC": "EXCALL",
    "EXP": "EXPUT",
    "SUB": "SUBSCRIB",
    "RED": "REDEMP",
    "SWI": "SWITIN",
    "SWO": "SWITOUT",
}


def _normalise_side(raw: str) -> str:
    return _SIDE_MAP.get(raw.upper(), raw.upper())


def parse_pdf(pdf_path: Path) -> list[dict]:
    full_text = ""
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            blob = re.sub(r"[ \t]+", " ", text)
            flat = blob.replace("\n", " ")
            full_text += flat + " "
            for m in _ROW_RE.finditer(flat):
                rows.append({
                    "order_no":        m.group("order_no"),
                    "settlement_date": m.group("date"),
                    "side":            _normalise_side(m.group("side")),
                    "symbol":        m.group("symbol").upper(),
                    "market":        m.group("market"),
                    "qty":           _clean_num(m.group("qty")),
                    "qty_unit":      "SHARES",
                    "price":         _clean_num(m.group("price")),
                    "currency":      m.group("currency"),
                    "gross_usd":     _clean_num(m.group("gross_usd")),
                    "fee_usd":       _clean_num(m.group("fee_usd")),
                    "wht_usd":       _clean_num(m.group("wht_usd")),
                    "net_usd":       _clean_num(m.group("net_usd")),
                    "gross_thb":     _clean_num(m.group("gross_thb")),
                    "fee_thb":       _clean_num(m.group("fee_thb")),
                    "wht_thb":       _clean_num(m.group("wht_thb")),
                    "net_thb":       _clean_num(m.group("net_thb")),
                    "source":        pdf_path.name,
                })

    acct_m = _ACCOUNT_NO_RE.search(full_text)
    eff_m = _EFFECTIVE_DATE_RE.search(full_text)
    account_no = acct_m.group(1) if acct_m else ""
    effective_date = eff_m.group(1) if eff_m else ""

    for row in rows:
        row["account_no"] = account_no
        row["effective_date"] = effective_date

    return rows


def parse_mutual_fund_pdf(pdf_path: Path) -> list[dict]:
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            blob = re.sub(r"[ \t]+", " ", text)
            full_text += blob.replace("\n", " ") + " "

    acct_m = _ACCOUNT_NO_RE.search(full_text)
    eff_m = _EFFECTIVE_DATE_RE.search(full_text)
    account_no = acct_m.group(1) if acct_m else ""
    effective_date = eff_m.group(1) if eff_m else ""

    rows: list[dict] = []
    for m in _MF_ROW_RE.finditer(full_text):
        gross_thb = _clean_num(m.group("gross_thb"))
        fee_thb = _clean_num(m.group("fee_thb"))
        rows.append({
            "order_no":        m.group("order_no"),
            "account_no":      account_no,
            "settlement_date": effective_date,
            "effective_date":  effective_date,
            "side":          _normalise_side(m.group("txtype")),
            "symbol":        m.group("symbol"),
            "market":        "MUTUALFUND",
            "qty":           _clean_num(m.group("qty")),
            "qty_unit":      "UNITS",
            "price":         _clean_num(m.group("price")),
            "currency":      "THB",
            "gross_usd":     0.0,
            "fee_usd":       0.0,
            "wht_usd":       0.0,
            "net_usd":       0.0,
            "gross_thb":     gross_thb,
            "fee_thb":       fee_thb,
            "wht_thb":       0.0,
            "net_thb":       gross_thb - fee_thb,
            "source":        pdf_path.name,
        })
    return rows


def extract_all() -> pd.DataFrame:
    pdfs = sorted(DECRYPTED_DIR.glob("*.pdf"))
    if not pdfs:
        print("No decrypted PDFs found in inbox/decrypted/")
        return pd.DataFrame()

    all_rows: list[dict] = []
    for pdf_path in tqdm(pdfs, desc="Parsing PDFs", unit="file"):
        try:
            if "DIMEMF" in pdf_path.name:
                found = parse_mutual_fund_pdf(pdf_path)
            else:
                found = parse_pdf(pdf_path)
        except Exception as exc:
            tqdm.write(f"  ERROR {pdf_path.name}: {exc}")
            continue
        tqdm.write(f"  {pdf_path.name}: {len(found)} rows")
        all_rows.extend(found)

    df = pd.DataFrame(all_rows)
    print(f"\nTotal raw rows: {len(df)}")
    return df


if __name__ == "__main__":
    df = extract_all()
    if "--csv" in sys.argv and not df.empty:
        out = OUTPUT_DIR / "trades_raw.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"Saved -> {out}")
    elif not df.empty:
        print(df.head(10).to_string())
