"""
Step 4.5 — Fill missing USD/THB values using historical forex rates.

Mutual fund rows have THB values but no USD equivalents (gross_usd = 0).
Gold rows have USD values but no THB equivalents (gross_thb = 0).

This step fetches the USD/THB closing rate from Yahoo Finance for each
transaction date and fills in the missing side.

Usage:
    python tool/forex_convert.py             # reads/updates output/trades.csv
    python tool/forex_convert.py --dry-run   # prints what would change
"""

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = PROJECT_ROOT / "output" / "trades.csv"

_USD_FIELDS = ["gross_usd", "fee_usd", "wht_usd", "net_usd"]
_THB_FIELDS = ["gross_thb", "fee_thb", "wht_thb", "net_thb"]

# Markets whose USD fields need to be derived from THB
_NEEDS_USD = {"MUTUALFUND"}
# Markets whose THB fields need to be derived from USD
_NEEDS_THB = {"YLGGOLD", "MTSGOLD"}


def _fetch_rate_series(min_date: pd.Timestamp, max_date: pd.Timestamp) -> pd.Series:
    """Download USDTHB=X closing prices, tz-naive index, forward-filled."""
    raw = yf.download(
        "USDTHB=X",
        start=min_date - timedelta(days=7),
        end=max_date + timedelta(days=2),
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        return pd.Series(dtype=float)

    close = raw["Close"]
    # yfinance >= 0.2.38 returns MultiIndex columns for a single ticker
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    # Normalize to tz-naive dates
    if close.index.tz is not None:
        close.index = close.index.tz_convert(None)

    return close.sort_index().ffill()


def _rate_for_date(series: pd.Series, dt: pd.Timestamp) -> float | None:
    """Return the most recent available rate on or before dt."""
    candidates = series[series.index <= dt]
    if candidates.empty:
        return None
    return float(candidates.iloc[-1])


def forex_convert(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    needs_usd = df["market"].isin(_NEEDS_USD)
    needs_thb = df["market"].isin(_NEEDS_THB)
    affected = needs_usd | needs_thb

    if not affected.any():
        print("  No rows need forex conversion.")
        return df

    all_dates = pd.to_datetime(df.loc[affected, "settlement_date"], format="%d/%m/%Y", errors="coerce")
    valid_dates = all_dates.dropna()
    if valid_dates.empty:
        print("  Warning: no valid settlement dates on forex rows — skipping conversion.")
        return df

    print(
        f"  Fetching USD/THB rates for {affected.sum()} row(s) "
        f"across {valid_dates.nunique()} unique date(s)..."
    )

    try:
        series = _fetch_rate_series(valid_dates.min(), valid_dates.max())
    except Exception as e:
        print(f"  Warning: forex rate fetch failed ({e}) — skipping conversion.")
        return df

    if series.empty:
        print("  Warning: could not fetch USD/THB rates — skipping conversion.")
        return df

    converted = 0
    for i in df[affected].index:
        dt = pd.to_datetime(df.at[i, "settlement_date"], format="%d/%m/%Y", errors="coerce")
        rate = _rate_for_date(series, dt) if pd.notna(dt) else None
        if rate is None:
            print(f"  Warning: no rate available for {df.at[i, 'settlement_date']} — skipping row.")
            continue

        if needs_usd.loc[i]:
            for thb_col, usd_col in zip(_THB_FIELDS, _USD_FIELDS):
                df.at[i, usd_col] = round(df.at[i, thb_col] / rate, 6)
        else:
            for usd_col, thb_col in zip(_USD_FIELDS, _THB_FIELDS):
                df.at[i, thb_col] = round(df.at[i, usd_col] * rate, 6)

        converted += 1

    print(f"  Converted {converted} row(s) (rate source: Yahoo Finance USDTHB=X).")
    return df


def run(csv_path: Path = DEFAULT_CSV, dry_run: bool = False) -> pd.DataFrame:
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    df_out = forex_convert(df)

    if dry_run:
        changed = df.index[
            (df_out[_USD_FIELDS + _THB_FIELDS] != df[_USD_FIELDS + _THB_FIELDS]).any(axis=1)
        ]
        print(f"\n[dry-run] Would update {len(changed)} row(s):")
        cols = ["settlement_date", "market", "symbol"] + _USD_FIELDS + _THB_FIELDS
        print(df_out.loc[changed, cols].to_string(index=False))
        return df_out

    df_out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"Saved -> {csv_path}")
    return df_out


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
