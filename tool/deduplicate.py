"""
Step 4 — Deduplicate raw rows and write final output/trades.csv.

Dedup key: (order_no, side, symbol) — keeps the record with the earliest source timestamp.

Usage:
    python tool/deduplicate.py
    python tool/deduplicate.py --input output/trades_raw.csv
"""

import sys
import re
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DEDUP_KEY = ["order_no", "side", "symbol"]
DEFAULT_INPUT = OUTPUT_DIR / "trades_raw.csv"
DEFAULT_OUTPUT = OUTPUT_DIR / "trades.csv"

_TS_RE = re.compile(r"^(\d{8}_\d{6})")


def _source_ts(source_name: str) -> str:
    m = _TS_RE.match(source_name)
    return m.group(1) if m else "00000000_000000"


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_ts"] = df["source"].apply(_source_ts)
    df.sort_values("_ts", inplace=True)

    before = len(df)
    df.drop_duplicates(subset=DEDUP_KEY, keep="first", inplace=True)
    after = len(df)

    df.drop(columns=["_ts"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    print(f"Rows before dedup: {before}  ->  after: {after}  (removed {before - after})")
    return df


def run(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return pd.DataFrame()

    df = pd.read_csv(input_path)
    df = deduplicate(df)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved -> {output_path}  ({len(df)} rows)")
    return df


if __name__ == "__main__":
    inp = DEFAULT_INPUT
    if "--input" in sys.argv:
        idx = sys.argv.index("--input")
        inp = Path(sys.argv[idx + 1])
    run(inp)
