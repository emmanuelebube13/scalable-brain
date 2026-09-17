# FIX-S1-019 — risk-off measured staleness in wall-clock hours, refusing every Sunday open → Monday D1 close

**Status:** FIXED 2026-09-14 · **Severity:** high (weekly, deterministic loss of ~20% of the trading week) · **Author:** Claude (Fable 5), at owner request ("the system is not trading — put it in motion")

---

## Summary

`src/monitoring/risk_off.py` (R4.2) measured the staleness of every decision-path input in
**wall-clock hours**. Its `_reference_time` helper handled the market being shut *at the
moment of measurement* (Saturday reads were referenced to the Friday close), but not the
market having been shut *during part of the measured interval*. On Sunday evening and all of
Monday the market is open, so staleness was measured against `now` — and the newest closed
D1 bar necessarily opened the previous **Thursday 21:00 UTC** (it is Friday's bar), putting
it 72–96 wall-clock hours behind a 54h limit no matter how healthy the labeller is.

Consequence: **the producer refused to emit from every Sunday open (21:00 UTC) until the
Monday D1 bar closed (Monday 21:00 UTC) — roughly a fifth of the trading week, every week,
by construction.** The Sunday-evening runs additionally breached the H4 (14h), H1 (8h) and
prices (4h) contracts until each granularity's first post-open bar closed.

## Evidence

- `results/state/signal_emitter_state.json` on 2026-09-14 15:15Z: `last_run_outcome:
  "risk_off"`, `consecutive_faults: 19`, `last_healthy_run_at: 2026-09-13T20:15:54Z` — the
  last run before the Sunday 21:00 open. Every hourly run after the open refused.
- `logs/cron_hourly_signals.log`, 2026-09-14 15:15Z run:
  `RISK-OFF — refusing to emit ... fact_regime_structural: newest row
  2026-09-10T21:00:00+00:00 is 90.3h behind now, over the 54h limit` — while the same run's
  `build_structural --incremental` step reported **0 rows to write** for D1/H4 (labels fully
  current with prices) and the heartbeat's market-calendar-aware `regimes` check read OK
  ("covers through 2026-09-11 20:00Z, the last market close").
- The refusal was a false positive: prices, structural labels and the map were all as fresh
  as the market calendar permits. Nothing was stalled.

## Fix (landed 2026-09-14)

Staleness of a decision-path input is now **market-open time elapsed without the input
advancing** — closed-market time cannot make data staler, because no bar existed to be missed.

- `src/monitoring/freshness.py`: new pure helper `open_hours_between(start, end)` — hours in
  the interval minus every overlapping weekend closure `[Friday 21:00, Sunday 21:00)`.
  Clamps to 0 when `end <= start`.
- `src/monitoring/risk_off.py`: `_evaluate_table` computes
  `age = open_hours_between(latest, now)` against the unchanged
  `max_staleness_hours + bar_hours` limits. `_reference_time` deleted — the market-closed-now
  case falls out of the open-hours arithmetic (no open hours accrue on Saturday). Breach
  messages now say "N open-market hours behind". Contract thresholds, blocking flags, the
  flag-file OR, and the map's own wall-clock 7-day contract are all unchanged.

**This is not a loosening.** A genuinely stalled labeller still accrues open hours and
breaches within the next session (a D1 stall on Monday breaches by Wednesday under the same
54h budget as before, midweek behaviour identical). What stopped counting against the limit
is time the market did not exist. The fail-closed postures — missing table, empty table, DB
error, unreadable flag — are untouched and still covered by tests.

## Verification

- `src/monitoring/tests/test_freshness.py::test_open_hours_between` — 6 cases including the
  incident interval (Thu 21:00 → Mon 15:15 = 42.25 open hours vs 90.25 wall-clock).
- `src/monitoring/tests/test_risk_off.py` — the exact 2026-09-14 incident replayed (must not
  breach), a Friday-close-fresh row on Saturday (must not breach), and a week-long stall read
  on Tuesday (must breach). The old `_reference_time` test replaced by these.
- Full suite: 813 passed, 1 skipped (2026-09-14). `black` clean.
- Live: `risk_off.refuse_reasons()` at 2026-09-14 15:4xZ returned **clear** (two remaining
  alerts are the non-blocking `fact_regime_structural_live` observer table, which only
  advances when signals route and heals on resumption). `python -m src.signals.run --once`
  then built, scored and published 1 signal (`a60b7f0c…`, EUR_USD H4 long, Trending-Up,
  shadow `would_refuse`), `consecutive_faults` reset 19 → 0, `signals_published_total`
  65 → 66, no new row in the local queue log (`QUEUE_PROVIDER=pubsub` confirmed from `.env`).

## Not checked / follow-ups

- Whether the same wall-clock arithmetic exists in any other consumer of freshness limits
  (`signals/watcher.py` LATENCY_THRESHOLDS use deliberately wide values — D1 108h — that
  already absorb the weekend; not audited beyond that).
- Prior weeks: risk_off landed ~2026-09-05 (R4.2), so Monday 2026-09-07 most likely refused
  the same way; not reconstructed from logs.
- The non-blocking `fact_regime_structural_live` contract alerts on every quiet stretch by
  the same logic inverted (it goes stale *because* nothing emits); acceptable while
  non-blocking, but its limits assume emission cadence, not market cadence.
