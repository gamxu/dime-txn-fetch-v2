# dime-txn-fetch

## Project Overview

Automated pipeline that collects trade data from three sources — Dime stock/ETF PDFs, Dime mutual fund PDFs, and gold transaction emails (YLG Gold + MTS Gold) — deduplicates everything, and upserts the final result to a Supabase table (`dime-txn`).

Designed to run as a scheduled job on Railway (or any cloud platform with ephemeral storage). Supabase is the only persistent output — local files are scratch space that disappears after each run.

---

## Prerequisites

| What | Notes |
|------|-------|
| Python 3.12+ | [python.org](https://python.org) |
| Gmail account | Must have Dime confirmation emails in inbox |
| Gmail 2-Step Verification | Required to generate an App Password |
| Dime PDF password | Set when you opened your Dime account |
| Supabase project | Free tier is sufficient |

---

## Local Setup (first time)

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in all values in .env
```

---

## Pipeline Steps

```
Gmail (IMAP)
  ↓  Step 1:   gmail_fetch.py          → inbox/raw/            (password-locked PDFs from Dime)
  ↓  Step 1b:  gmail_gold_fetch.py     → output/gold_raw.csv   (gold txns from YLG + MTS email bodies)
  ↓  Step 2:   decrypt_pdfs.py         → inbox/decrypted/      (unlocked PDFs)
  ↓  Step 3:   extract_transactions.py → output/trades_raw.csv (stock/ETF + mutual fund PDFs + gold rows)
  ↓  Step 4:   deduplicate.py          → output/trades.csv     (dedup by order_no+side+symbol)
  ↓  Step 4.5: forex_convert.py        → output/trades.csv     (fill missing USD/THB via Yahoo Finance)
  ↓  Step 5:   supabase_upload.py      → Supabase              (upsert into dime-txn table)
```

**Full run:**
```bash
python tool/run_pipeline.py
```

**Flags:**
- `--no-fetch` — skip Gmail steps, use existing PDFs in `inbox/raw/` and cached `output/gold_raw.csv`
- `--no-upload` — skip Supabase upload (offline mode)

**Run individual steps:**
```bash
python tool/gmail_fetch.py                      # Step 1 only (PDF download)
python tool/gmail_fetch.py --list-subjects      # debug: print all Dime email subjects
python tool/gmail_gold_fetch.py                 # Step 1b only (gold email body preview)
python tool/gmail_gold_fetch.py --csv           # Step 1b only (save output/gold_raw.csv)
python tool/decrypt_pdfs.py                     # Step 2 only
python tool/extract_transactions.py             # Step 3 only (preview)
python tool/extract_transactions.py --csv       # Step 3 only (save CSV)
python tool/deduplicate.py                      # Step 4 only
python tool/forex_convert.py                    # Step 4.5 only (fill missing USD/THB)
python tool/forex_convert.py --dry-run          # Step 4.5 dry run (preview changes)
python tool/supabase_upload.py                  # Step 5 only
python tool/supabase_upload.py --dry-run        # Step 5 dry run (no upload)
```

---

## Project Structure

```
tool/
  run_pipeline.py         # Orchestrator — runs all steps in sequence
  gmail_fetch.py          # Step 1:  IMAP download of Dime PDFs from Gmail
  gmail_gold_fetch.py     # Step 1b: Parse YLG + MTS gold transaction emails
  decrypt_pdfs.py         # Step 2:  pikepdf decryption
  extract_transactions.py # Step 3:  pdfplumber + regex (stock/ETF and mutual fund PDFs)
  deduplicate.py          # Step 4:   dedup by (order_no, side, symbol)
  forex_convert.py        # Step 4.5: fill missing USD/THB using Yahoo Finance USDTHB=X
  supabase_upload.py      # Step 5:   Supabase upsert

inbox/raw/                # Git-ignored — downloaded encrypted PDFs
inbox/decrypted/          # Git-ignored — decrypted PDFs
output/                   # Git-ignored — intermediate CSVs (gold_raw.csv, trades_raw.csv, trades.csv)

.env                      # Git-ignored — all secrets
.env.example              # Template for .env
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values.

```
GMAIL_USER=
GMAIL_APP_PASSWORD=
PDF_PASSWORD=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_TABLE=dime-txn
```

---

## Credentials Setup

### 1. Gmail App Password (`GMAIL_USER` + `GMAIL_APP_PASSWORD`)

Used by Step 1 to connect to Gmail via IMAP and download PDFs.

1. Your Gmail account must have **2-Step Verification** enabled.
   Go to: [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Under "Select app" choose **Mail**, under "Select device" choose **Other** → name it `dime-txn-fetch`
4. Click **Generate** — copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)
5. Set in `.env`:
   ```
   GMAIL_USER=your_gmail@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```

---

### 2. Dime PDF Password (`PDF_PASSWORD`)

Used by Step 2 to decrypt the password-protected confirmation PDFs that Dime sends.

This is the **security code / PDF password** you set when you opened your Dime account.
Check your Dime account settings or the welcome email if you've forgotten it.

Set in `.env`:
```
PDF_PASSWORD=your_dime_pdf_password
```

---

### 3. Supabase Credentials (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`)

Used by Step 5 to upsert rows into the `dime-txn` table.

1. Go to your Supabase project dashboard
2. **Project Settings → API**
3. Copy **Project URL** → `SUPABASE_URL`
4. Copy **service_role** key (not the anon key) → `SUPABASE_SERVICE_KEY`

Set in `.env`:
```
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key_here
SUPABASE_TABLE=dime-txn
```

#### Create the table

Run this SQL in the Supabase SQL editor once:

```sql
create table "dime-txn" (
  order_no   text,
  date       date,
  side       text,
  symbol     text,
  market     text,
  qty        numeric,
  qty_unit   text,
  price      numeric,
  currency   text,
  gross_usd  numeric,
  fee_usd    numeric,
  wht_usd    numeric,
  net_usd    numeric,
  gross_thb  numeric,
  fee_thb    numeric,
  wht_thb    numeric,
  net_thb    numeric,
  constraint "dime-txn_pkey" unique (order_no, side, symbol)
);
```

---

## Output Schema

Final `trades.csv` and Supabase `dime-txn` table columns:

| Column | Description |
|--------|-------------|
| `order_no` | Order ID |
| `date` | Settlement date (YYYY-MM-DD) |
| `side` | Transaction type (see table below) |
| `symbol` | Ticker / fund code / gold product code |
| `market` | Exchange or source identifier |
| `qty` | Quantity |
| `qty_unit` | Unit of quantity (SHARES, UNITS, OZ) |
| `price` | Unit price |
| `currency` | Currency code |
| `gross_usd` | Gross amount in USD |
| `fee_usd` | Fee in USD |
| `wht_usd` | Withholding tax in USD |
| `net_usd` | Net amount in USD |
| `gross_thb` | Gross amount in THB |
| `fee_thb` | Fee in THB |
| `wht_thb` | Withholding tax in THB |
| `net_thb` | Net amount in THB |

---

## Transaction Types (`side` column)

### Stock / ETF

| Code | Meaning |
|------|---------|
| BUY | ซื้อหลักทรัพย์ |
| SELL | ขายหลักทรัพย์ |
| REWARD | ได้รับหลักทรัพย์เป็นรางวัล |
| EXCALL | ใช้สิทธิ์ซื้อหลักทรัพย์ (Exercise Call Options) |
| EXPUT | ใช้สิทธิ์ขายหลักทรัพย์ (Exercise Put Options) |

### Mutual Fund

| Code | Meaning |
|------|---------|
| SUBSCRIB | ซื้อหน่วยลงทุน (Subscription) |
| REDEMP | ขายหน่วยลงทุน (Redemption) |
| SWITIN | สับเปลี่ยนหน่วยลงทุนเข้า (Switch in) |
| SWITOUT | สับเปลี่ยนหน่วยลงทุนออก (Switch out) |

### Gold

| Code | Meaning |
|------|---------|
| BUY | ซื้อทองคำ |
| SELL | ขายทองคำ |

---

## Data Sources & Field Mapping

| Source | `market` | `currency` | `qty_unit` | USD fields | THB fields |
|--------|----------|------------|------------|------------|------------|
| Stock / ETF PDF | exchange code (e.g. XNAS) | USD | SHARES | filled | filled |
| Mutual Fund PDF (DIMEMF) | MUTUALFUND | THB | UNITS | 0 | filled |
| YLG Gold email | YLGGOLD | USD | OZ | filled | 0 |
| MTS Gold email | MTSGOLD | USD | OZ | filled | 0 |

Gold emails are filtered by sender and subject:
- YLG: sender `goldportplus@ylgcorporation.co.th`, subject contains `[ YLG GOLD ]` and `DIME`
- MTS: sender `noreply@mtsgoldgroup.com`, subject contains `[MTS Gold]` and `สั่งซื้อ` or `สั่งขาย`

BUY/SELL for gold is determined by the email subject:
- `สั่งขาย` in subject → SELL; otherwise → BUY

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Total new PDFs downloaded: 0` | Run `--list-subjects` to check the subject keyword. Default filter is `"Confirmation Note"` |
| `No PDFs found in inbox/raw/` | Run Step 1 first, or place PDFs in `inbox/raw/` manually |
| `ERROR wrong password` | Check `PDF_PASSWORD` in `.env` |
| `No rows extracted` from stock PDF | Check pdfplumber raw text — the regex may need adjusting for a new PDF format |
| `0 rows` from mutual fund PDF | Confirm the PDF filename contains `DIMEMF` and the table row format matches |
| Gold rows not fetched (0 rows) | Confirm sender addresses match exactly and the subject contains the expected Thai keywords |
| `UnicodeEncodeError` on Windows | Run with `python -X utf8 tool/run_pipeline.py` or set `PYTHONIOENCODING=utf-8` |
| Supabase auth error | Check `SUPABASE_SERVICE_KEY` — must be the `service_role` key, not `anon` |
| Supabase upsert error | Confirm the `dime-txn` table exists with the unique constraint on `(order_no, side, symbol)` |

---

## Known Limitations

- Windows console may show Unicode errors — run with: `python -X utf8 tool/run_pipeline.py`
- Dime sends PDFs as `application/octet-stream` (not standard `application/pdf`) — the fetcher detects by filename extension
- Gold emails carry no THB equivalent — `gross_thb`, `fee_thb`, `wht_thb`, `net_thb` are stored as 0
- Mutual fund rows carry no USD equivalent — `gross_usd`, `fee_usd`, `wht_usd`, `net_usd` are stored as 0
