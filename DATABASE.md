# dime-txn — Database Reference

## Table: `dime-txn`

Supabase table storing all trade transactions from three sources: Dime stock/ETF PDFs, Dime mutual fund PDFs, and gold transaction emails (YLG Gold + MTS Gold).

---

## DDL

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

**Primary key / deduplication key:** `(order_no, side, symbol)`

---

## Column Reference

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `order_no` | text | No | Order ID from the source document or email |
| `date` | date | No | Settlement date in `YYYY-MM-DD` format |
| `side` | text | No | Transaction type — see [Transaction Types](#transaction-types) |
| `symbol` | text | No | Ticker symbol, mutual fund code, or gold product code |
| `market` | text | No | Exchange or data source identifier — see [Market Values](#market-values) |
| `qty` | numeric | No | Quantity of units transacted |
| `qty_unit` | text | No | Unit of quantity — `SHARES`, `UNITS`, or `OZ` |
| `price` | numeric | No | Unit price in the transaction currency |
| `currency` | text | No | Currency code — `USD` or `THB` |
| `gross_usd` | numeric | No | Gross transaction amount in USD (0 if source is THB-only) |
| `fee_usd` | numeric | No | Broker/commission fee in USD (0 if source is THB-only) |
| `wht_usd` | numeric | No | Withholding tax in USD (0 if source is THB-only) |
| `net_usd` | numeric | No | Net amount in USD after fees and WHT (0 if source is THB-only) |
| `gross_thb` | numeric | No | Gross transaction amount in THB (0 if source is USD-only) |
| `fee_thb` | numeric | No | Broker/commission fee in THB (0 if source is USD-only) |
| `wht_thb` | numeric | No | Withholding tax in THB (0 if source is USD-only) |
| `net_thb` | numeric | No | Net amount in THB after fees and WHT (0 if source is USD-only) |

---

## Transaction Types (`side`)

### Stock / ETF

| `side` | Meaning |
|--------|---------|
| `BUY` | Buy securities (ซื้อหลักทรัพย์) |
| `SELL` | Sell securities (ขายหลักทรัพย์) |
| `REWARD` | Received securities as reward (ได้รับหลักทรัพย์เป็นรางวัล) |
| `EXCALL` | Exercise call options (ใช้สิทธิ์ซื้อหลักทรัพย์) |
| `EXPUT` | Exercise put options (ใช้สิทธิ์ขายหลักทรัพย์) |

### Mutual Fund

| `side` | Meaning |
|--------|---------|
| `SUBSCRIB` | Subscription / buy units (ซื้อหน่วยลงทุน) |
| `REDEMP` | Redemption / sell units (ขายหน่วยลงทุน) |
| `SWITIN` | Switch-in (สับเปลี่ยนหน่วยลงทุนเข้า) |
| `SWITOUT` | Switch-out (สับเปลี่ยนหน่วยลงทุนออก) |

### Gold

| `side` | Meaning |
|--------|---------|
| `BUY` | Buy gold (ซื้อทองคำ) |
| `SELL` | Sell gold (ขายทองคำ) |

---

## Market Values (`market`)

| `market` | Source | Asset class |
|----------|--------|-------------|
| Exchange code (e.g. `XNAS`, `XNYS`) | Dime stock/ETF PDF | Stock / ETF |
| `MUTUALFUND` | Dime mutual fund PDF | Mutual Fund |
| `YLGGOLD` | YLG Gold email body | Gold |
| `MTSGOLD` | MTS Gold email body | Gold |

---

## Currency & Amount Fields by Source

Different sources only carry amounts in one currency — the other currency fields are stored as `0`.

| `market` | `currency` | `qty_unit` | USD fields | THB fields |
|----------|------------|------------|------------|------------|
| Exchange code (stock/ETF) | `USD` | `SHARES` | Filled | `0` |
| `MUTUALFUND` | `THB` | `UNITS` | `0` | Filled |
| `YLGGOLD` | `USD` | `OZ` | Filled | `0` |
| `MTSGOLD` | `USD` | `OZ` | Filled | `0` |

**UI implication:** When displaying amounts, check `currency` (or `market`) to decide which column pair to show. Never sum `gross_usd` and `gross_thb` together without currency conversion.

---

## Key Relationships & Constraints

- **Unique constraint:** `(order_no, side, symbol)` — the pipeline upserts on this key, so re-running never creates duplicates.
- **No foreign keys** — this is a flat denormalized table; all source context is embedded in `market` and `currency`.
- **No auto-increment ID** — `order_no` comes from the source document. Use the composite key `(order_no, side, symbol)` as the logical row identity.

---

## Filtering Patterns for UI

| Use case | Filter |
|----------|--------|
| Show only stock/ETF trades | `market NOT IN ('MUTUALFUND', 'YLGGOLD', 'MTSGOLD')` |
| Show only mutual fund trades | `market = 'MUTUALFUND'` |
| Show only gold trades | `market IN ('YLGGOLD', 'MTSGOLD')` |
| Show only buys | `side = 'BUY' OR side = 'SUBSCRIB' OR side = 'SWITIN' OR side = 'EXCALL'` |
| Show only sells | `side = 'SELL' OR side = 'REDEMP' OR side = 'SWITOUT' OR side = 'EXPUT'` |
| Date range | `date >= '2024-01-01' AND date <= '2024-12-31'` |
| Single symbol | `symbol = 'AAPL'` |

---

## Example Rows

### Stock / ETF (USD)

| order_no | date | side | symbol | market | qty | qty_unit | price | currency | gross_usd | fee_usd | wht_usd | net_usd | gross_thb | fee_thb | wht_thb | net_thb |
|----------|------|------|--------|--------|-----|----------|-------|----------|-----------|---------|---------|---------|-----------|---------|---------|---------|
| ORD-001 | 2024-03-15 | BUY | AAPL | XNAS | 10 | SHARES | 172.50 | USD | 1725.00 | 1.99 | 0 | 1726.99 | 0 | 0 | 0 | 0 |
| ORD-002 | 2024-03-20 | SELL | MSFT | XNAS | 5 | SHARES | 415.00 | USD | 2075.00 | 1.99 | 0 | 2073.01 | 0 | 0 | 0 | 0 |

### Mutual Fund (THB)

| order_no | date | side | symbol | market | qty | qty_unit | price | currency | gross_usd | fee_usd | wht_usd | net_usd | gross_thb | fee_thb | wht_thb | net_thb |
|----------|------|------|--------|--------|-----|----------|-------|----------|-----------|---------|---------|---------|-----------|---------|---------|---------|
| MF-003 | 2024-04-01 | SUBSCRIB | KMASTER | MUTUALFUND | 1000 | UNITS | 10.50 | THB | 0 | 0 | 0 | 0 | 10500.00 | 0 | 0 | 10500.00 |

### Gold (USD)

| order_no | date | side | symbol | market | qty | qty_unit | price | currency | gross_usd | fee_usd | wht_usd | net_usd | gross_thb | fee_thb | wht_thb | net_thb |
|----------|------|------|--------|--------|-----|----------|-------|----------|-----------|---------|---------|---------|-----------|---------|---------|---------|
| GLD-004 | 2024-05-10 | BUY | GOLD | YLGGOLD | 1 | OZ | 2320.00 | USD | 2320.00 | 5.00 | 0 | 2325.00 | 0 | 0 | 0 | 0 |
