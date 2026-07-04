"""
Full pipeline — runs all 5 steps in sequence.

Usage:
    python tool/run_pipeline.py               # fetch + decrypt + extract + dedup + upload
    python tool/run_pipeline.py --no-fetch    # skip Gmail, use existing inbox/raw/ and output/gold_raw.csv
    python tool/run_pipeline.py --no-upload   # skip Supabase upload
"""

import sys
import time
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

# Allow imports from tool/ regardless of working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gmail_fetch import fetch_pdfs
from gmail_gold_fetch import fetch_gold_transactions
from decrypt_pdfs import decrypt_all
from extract_transactions import extract_all
from deduplicate import deduplicate
from forex_convert import forex_convert
from supabase_upload import is_table_empty, upload_to_supabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "output" / "trades_raw.csv"
GOLD_CSV = PROJECT_ROOT / "output" / "gold_raw.csv"
FINAL_CSV = PROJECT_ROOT / "output" / "trades.csv"


def main():
    skip_fetch = "--no-fetch" in sys.argv
    skip_upload = "--no-upload" in sys.argv

    if not skip_fetch:
        print("=" * 50)
        print("Checking Supabase table...")
        print("=" * 50)
        if is_table_empty():
            since_date = None
            print("Table is empty — fetching all data from the beginning.")
        else:
            since_date = date.today() - timedelta(days=7)
            print(f"Table has data — fetching last 7 days (since {since_date}).")

        print("\n" + "=" * 50)
        print("Step 1: Fetching PDFs from Gmail")
        print("=" * 50)
        fetch_pdfs(since_date=since_date)

        print("\n" + "=" * 50)
        print("Step 1b: Fetching gold transactions from Gmail")
        print("=" * 50)
        df_gold = fetch_gold_transactions(since_date=since_date)
        if not df_gold.empty:
            GOLD_CSV.parent.mkdir(parents=True, exist_ok=True)
            df_gold.to_csv(GOLD_CSV, index=False, encoding="utf-8-sig")
            print(f"Gold rows saved -> {GOLD_CSV}")
    else:
        print("Step 1 / 1b: skipped (--no-fetch)")
        df_gold = pd.read_csv(GOLD_CSV) if GOLD_CSV.exists() else pd.DataFrame()
        if not df_gold.empty:
            print(f"Loaded {len(df_gold)} gold rows from cache")

    print("\n" + "=" * 50)
    print("Step 2: Decrypting PDFs")
    print("=" * 50)
    decrypt_all()

    print("\n" + "=" * 50)
    print("Step 3: Extracting transactions")
    print("=" * 50)
    df_raw = extract_all()
    if df_raw.empty and df_gold.empty:
        print("No rows extracted -- aborting.")
        return

    # Combine PDF rows with gold email rows
    if not df_gold.empty:
        df_raw = pd.concat([df_raw, df_gold], ignore_index=True)
        print(f"Combined rows (PDFs + gold): {len(df_raw)}")

    df_raw.to_csv(RAW_CSV, index=False, encoding="utf-8-sig")
    print(f"Raw rows saved -> {RAW_CSV}")

    print("\n" + "=" * 50)
    print("Step 4: Deduplicating")
    print("=" * 50)
    df_final = deduplicate(df_raw)

    print("\n" + "=" * 50)
    print("Step 4.5: Forex conversion (fill missing USD/THB values)")
    print("=" * 50)
    df_final = forex_convert(df_final)

    df_final.to_csv(FINAL_CSV, index=False, encoding="utf-8-sig")
    print(f"Final output -> {FINAL_CSV}  ({len(df_final)} trades)")

    if not skip_upload:
        print("\n" + "=" * 50)
        print("Step 5: Uploading to Supabase")
        print("=" * 50)
        upload_to_supabase(df_final)
    else:
        print("\nStep 5: skipped (--no-upload)")

    print("\nDone.")


if __name__ == "__main__":
    ATTEMPTS = 3
    DELAY_SECONDS = 60
    for attempt in range(1, ATTEMPTS + 1):
        try:
            main()
            break
        except Exception as e:
            if attempt == ATTEMPTS:
                raise
            print(f"\nRun failed ({e}) — retry {attempt}/{ATTEMPTS - 1} in {DELAY_SECONDS}s\n")
            time.sleep(DELAY_SECONDS)
