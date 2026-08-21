# INGEST-MBA — agent brief (resumable)

**You are working in `/home/emmanuel/Documents/Scalable_Brain/scalable-brain` (System 1, "The Brain").**

This brief is self-contained. It is written to be **stopped and resumed** — if you hit a rate
limit, context limit, or any interruption, the next agent (or you, later) re-reads this file plus
`STATE.md` in the same folder and continues from the first unchecked step.

---

## 0. RESUME PROTOCOL — DO THIS FIRST, EVERY TIME

1. Read `task/2026-August-week3/ingest-mba/STATE.md`.
   - If it does not exist, create it by copying the checklist in §6 of this file, all unchecked.
2. Find the first unchecked `[ ]` item. That is your starting point. Everything above it is done.
3. Before starting work, append a line to STATE.md's `## Log` section:
   `- <UTC timestamp> — starting S<n> — <agent name>`
4. **After completing each step**, immediately:
   - tick the box in STATE.md,
   - append a Log line recording what changed and any surprise,
   - `git add -A && git commit` with message `INGEST-MBA S<n>: <what>`.
   Commit after *every* step. A step that is committed is a step that survives an interruption.
5. Never re-run a ticked step. The DB writes are idempotent but the backfills are slow.

**Do not batch steps.** One step, one verification, one commit.

---

## 1. BACKGROUND — what is wrong

`fact_market_prices` has mid columns (`"Open"`, `high`, `low`, `"Close"`) and bid/ask columns
(`bid_open…bid_close`, `ask_open…ask_close`). Two different writers populate this table:

| Writer | Path | price param | Behaviour |
|---|---|---|---|
| Legacy (layer0) | `src/layer0/ingest_data/ingest_oanda_prices.py` | `CONFIG.OANDA_PRICE = "BA"` | **Correct.** `transform_candles()` extracts bid and ask, computes mid as their arithmetic mean, writes all three. |
| System-1 (MODEL-001) | `src/ingestion/multi_timeframe_ingest.py` | reuses the same fetcher, so also `"BA"` | **Broken.** See below. |

### Bug 1 — bid prices are being stored as mid (correctness, silent)

`multi_timeframe_ingest._normalize_candle()` (~line 71) does:

```python
prices = c.get("mid") or c.get("bid") or c.get("ask") or {}
```

Because the request sends `price=BA`, the OANDA response contains `bid` and `ask` keys and **no
`mid` key**. So this falls through to `c.get("bid")` and writes **bid OHLC** into the mid columns.
Every row written by this path is biased low by roughly half the spread (~0.9–1.5 pips).

### Bug 2 — bid/ask are never written by this path

`upsert_bars_with_lineage()` (~line 92) inserts 12 columns and none of them are `bid_*`/`ask_*`.
Its `ON CONFLICT … DO UPDATE` does not touch them either — so pre-existing values survive
(good) but new rows land NULL (bad).

### Bug 3 — H1 is not in the System-1 ingest's granularity list

`DEFAULT_GRANULARITIES = ["D1", "H4", "W1"]` (~line 48). H1 is the primary modelling frame for
almost every strategy. Confirmed by query: for all of 2026, H1 rows have `ingest_run_id` populated
on **zero** rows — this writer has never touched H1.

### Observed damage (measured 2026-08-21, re-verify before you act)

| Granularity | rows | bid/ask populated | note |
|---|---|---|---|
| H1 | 653,250 | 647,850 (99.2%) | gap 2026-05-03 → 2026-07-03 |
| H4 | 165,828 | 164,478 (99.2%) | same window |
| D1 | 29,638 | 29,413 (99.2%) | same window |
| M15 | 2,553,691 | 100% | stale, ends 2026-05-01 |
| M30 | 1,280,826 | 100% | stale, ends 2026-05-01 |
| **W1** | **5,375** | **0** | 100% written by the broken path — mid is actually bid |

---

## 2. GOAL

One ingest path that requests `price=MBA` and persists true mid **and** bid **and** ask, covering
H1/H4/D1/W1, with DQ checks that would have caught all three bugs, plus repair of the damaged rows.

### SCOPE FENCE — do not cross it

This task touches **only the 5 instruments already in `dim_asset`**: EUR_USD, GBP_USD, USD_JPY,
AUD_USD, USD_CAD. Nothing else.

Explicitly **out of scope**. Do not start any of these, do not "while I'm here" them, and do not
add them to the checklist:

- **Adding instruments.** The account exposes 68 tradeable FX pairs plus metals and CFDs. Widening
  the universe is a deliberate future decision the owner has deferred. Do not seed `dim_asset`,
  do not ingest a 6th pair, do not backfill history for anything new.
- **Order-book / position-book ingest.** Separate task, separate table, separate brief.
- **Changing the backtest engine's cost model** (spread, slippage, commission, financing). The
  data this task lands will eventually feed that change; making it is not this task.
- Anything under `src/system2`/`system3` references or `archieved/`.

The deliverable is *correctness on the existing 5 pairs*, not coverage. If you find yourself
fetching an instrument not in `dim_asset`, stop — you have left the task.

---

## 3. REPO RULES YOU MUST FOLLOW

Read `CLAUDE.md` in full before the first code change. The load-bearing ones here:

- **DB access only via `src/common/db.py` `get_engine()`.** Never build a connection string.
- **Column case:** only `"Open"` and `"Close"` are mixed-case and must be double-quoted.
  `"timestamp"` is reserved and must be quoted. Everything else is lowercase.
- **Idempotent writes only:** `INSERT … ON CONFLICT (<pk>) DO UPDATE`. The natural key is
  `("timestamp", asset_id, granularity)`.
- **Parameterized SQL only.** No f-string interpolation of values.
- Type hints everywhere; `black src/ && mypy src/` must pass before you commit.
- Never commit `.env`, anything under `secrets/`, or log an API key.
- Pair behaviour changes with doc updates in the same commit.
- Python: `/home/emmanuel/Documents/Scalable_Brain/.venv/bin/python`

**Credentials:** `.env` has `OANDA_API_KEY`, `OANDA_ACCOUNT_ID`, `OANDA_URL`
(practice: `https://api-fxpractice.oanda.com`). Note `python-dotenv`'s `load_dotenv()` resolves
relative to the *calling file*, so from a script outside the repo root you must pass the explicit
path. Ingest modules run as `python -m src.…` from the repo root, where the default works.

---

## 4. SAFETY — READ BEFORE ANY WRITE

- **Snapshot before any repair step.** `CREATE TABLE fact_market_prices_bak_<YYYYMMDD> AS
  SELECT * FROM fact_market_prices;` — this table is ~4.7M rows, the copy is cheap, and
  `task/OPEN.md` records that a previous rebuild without a snapshot was a near-miss.
- **`--dry-run` first, always.** `multi_timeframe_ingest` already supports it.
- Do **not** DELETE rows. Every repair in this task is an UPDATE or an upsert.
- If a verification query disagrees with this brief, **trust the query** and record the
  discrepancy in STATE.md. This brief was written 2026-08-21 and the data moves.

---

## 5. RATE LIMITS

OANDA practice allows roughly 100 requests/second per account but throttles aggressively on
sustained load; `fetch_candles_with_retry` already implements backoff — reuse it, do not write a
new HTTP client.

If **your own** LLM/agent rate limit interrupts you mid-backfill: the ingest resumes from a DB
cursor (`get_resume_timestamp`), so simply re-running the same command continues where it stopped.
Record in STATE.md which command was mid-flight so the next agent re-runs exactly that.

---

## 6. THE WORK — checklist

Copy this into `STATE.md` on first run.

### S1 — Reproduce and quantify (no writes)
- [ ] Confirm bug 1 empirically: fetch one H1 candle with `price=MBA` for EUR_USD, compare its
      `mid.c` against the `"Close"` stored in `fact_market_prices` for the same timestamp, and
      against `bid.c`. Record which one the DB matches, for a row written by each writer.
- [ ] Count rows affected by bug 1. Rows written by the System-1 path are identifiable by
      `ingest_run_id IS NOT NULL`. Also flag W1 entirely.
- [ ] Write findings into `FINDINGS.md` in this folder. If bug 1 does **not** reproduce, stop and
      report — do not proceed to repair.

### S2 — Fix the fetcher to request MBA
- [ ] In `src/layer0/ingest_data/ingest_oanda_prices.py`, `CONFIG.OANDA_PRICE` is `"BA"`. Change
      the *System-1* path to request `"MBA"` without breaking the legacy path — prefer adding an
      explicit `price` argument to `fetch_candles_window` defaulting to `CONFIG.OANDA_PRICE`, so
      the legacy caller is untouched and `multi_timeframe_ingest` passes `"MBA"`.
- [ ] Its stale docstring says "Mid candles only (price=M)" — correct it.
- [ ] Unit test: the params dict carries the price the caller asked for.

### S3 — Fix `_normalize_candle`
- [ ] Parse `mid`, `bid`, `ask` as three separate blocks. Mid comes from `c["mid"]`.
- [ ] **Fail loudly, do not fall back.** If `mid` is absent, return `None` and log an error. The
      silent `or` chain is what caused bug 1; do not preserve that shape.
- [ ] `dq.Bar` is `Dict[str, object]` (`src/ingestion/dq.py` line 20) so it needs no type change,
      but add the 8 new keys: `bid_open/high/low/close`, `ask_open/high/low/close`.

### S4 — Fix the upsert
- [ ] Add the 8 bid/ask columns to the INSERT column list, the row tuple, and the
      `ON CONFLICT DO UPDATE SET` clause in `upsert_bars_with_lineage`.
- [ ] Keep the existing natural key and the `RETURNING (xmax = 0) AS inserted` pattern.
- [ ] Mirror the change in the quarantine writer (`fact_market_prices_quarantine`) if that table
      has the columns; if it does not, leave it and note why.

### S5 — DQ gates that would have caught this
- [ ] In `src/ingestion/dq.py` add per-bar checks: `bid_close <= close <= ask_close`;
      `ask_close - bid_close >= 0`; spread below a per-instrument sanity ceiling (measured H1
      averages: EUR_USD 1.81, USD_JPY 1.96, AUD_USD 2.07, GBP_USD 2.85, USD_CAD 2.91 pips;
      observed maxima reach 40–50 pips at weekend gaps, so the ceiling must not be tight).
- [ ] A bar failing these goes to quarantine, not to the fact table.
- [ ] Tests in `src/ingestion/tests/test_dq.py` covering: mid outside bid/ask, negative spread,
      absurd spread, missing mid block.

### S6 — Add H1
- [ ] `DEFAULT_GRANULARITIES = ["D1", "H4", "H1", "W1"]`.
- [ ] Confirm `CONFIG.CHUNK_DAYS` has an H1 entry (it does: 7) and `--granularity` choices already
      include H1 (they do).

### S7 — Verify on a dry run
- [ ] `python -m src.ingestion.multi_timeframe_ingest --symbol EUR_USD --granularity H1 --dry-run`
- [ ] `pytest src/ingestion -v` and `pytest src/layer0/tests/ -v` both green.
- [ ] `black src/ && mypy src/` clean.

### S8 — Live run, one instrument
- [ ] Snapshot the table (§4) if not already done this session.
- [ ] Run for EUR_USD H1 only. Then verify: newly written rows have non-NULL bid/ask, and
      `"Close"` now equals `mid.c` from the API rather than `bid.c`.

### S9 — Repair the damaged rows
- [ ] **W1 (5,375 rows):** all mid columns hold bid prices and bid/ask are NULL. Re-ingest W1 for
      all 5 instruments; the upsert overwrites in place.
- [ ] **The 2026-05-03 → 2026-07-03 NULL-bid window** on D1/H1/H4 (~7,000 rows): re-ingest that
      date range.
- [ ] Any other rows S1 identified as bid-as-mid.
- [ ] Re-run the S1 verification queries and record before/after in `FINDINGS.md`.

### S10 — Reconcile the two writers
- [ ] Two paths writing one table is the root cause. Decide and **document** which is canonical.
      Recommended: System-1 `multi_timeframe_ingest` is canonical; the layer0 loader becomes
      import-only for its helpers. Do not delete the layer0 module — `multi_timeframe_ingest`
      imports `fetch_candles_with_retry`, `normalize_granularity`, `get_interval_delta` and others
      from it.
- [ ] Check `shell/cron_oanda_ingest_saturday.sh` — confirm which module the Saturday cron invokes
      and make it the canonical one.
- [ ] Update `CLAUDE.md` (the MODEL-001 row and the Scheduled operation section) and add a
      `docs/proposed-fixes/system-1/FIX-S1-015-mid-price-and-bidask-ingest.md` following the format
      of the existing FIX-S1-0xx docs.

### S11 — Report
- [ ] Write `DELIVERABLE.md` in this folder: what was broken, rows repaired, tests added, what a
      reviewer should re-run to confirm. State plainly anything left undone.

---

## 7. DEFINITION OF DONE

- `price=MBA` requested; true mid stored in `"Open"/high/low/"Close"`; bid/ask stored alongside.
- No silent fallback remains in `_normalize_candle`.
- H1 covered by the System-1 ingest.
- DQ rejects mid-outside-bid/ask and absurd spreads, with tests.
- W1 and the May–July window repaired and verified by query.
- `pytest src/ingestion src/layer0/tests -v` green; `black`/`mypy` clean.
- Canonical writer documented; `CLAUDE.md` and a FIX doc updated.
- Every step committed individually and ticked in STATE.md.

## 8. IF YOU GET STUCK

Record the blocker in STATE.md under `## Blockers` with the exact command and error, tick nothing,
and stop. Do not improvise around a failing verification — a wrong repair on 4.7M rows is far more
expensive than a paused task.
