"""
Step 5 — Upload final trades.csv to Supabase.

Upserts rows using (order_no, side, symbol) as the conflict key,
matching the deduplication logic in deduplicate.py.

Usage:
    python tool/supabase_upload.py             # upload output/trades.csv
    python tool/supabase_upload.py --dry-run   # print rows without uploading
"""

import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import os

from supabase import create_client, Client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_CSV = PROJECT_ROOT / "output" / "trades.csv"


def _get_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def upload_to_supabase(df: pd.DataFrame) -> None:
    table = os.environ.get("SUPABASE_TABLE", "dime-txn")
    client = _get_client()

    df = df.copy()
    df.drop(columns=["source"], errors="ignore", inplace=True)
    # Convert DD/MM/YYYY -> YYYY-MM-DD for proper SQL date type
    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")

    # NaN -> None so Supabase stores SQL NULL instead of the string "nan"
    records = df.where(pd.notna(df), None).to_dict(orient="records")

    client.table(table).upsert(records, on_conflict="order_no,side,symbol").execute()
    print(f"Upserted {len(records)} rows to Supabase table '{table}'.")


def run(csv_path: Path = DEFAULT_CSV, dry_run: bool = False) -> None:
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return

    df = pd.read_csv(csv_path)

    if dry_run:
        print(f"[dry-run] Would upload {len(df)} rows from {csv_path}")
        print(df.head())
        return

    upload_to_supabase(df)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
