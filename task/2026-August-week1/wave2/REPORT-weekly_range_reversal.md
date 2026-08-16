# REPORT — weekly_range_reversal

**Spec:** `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-weekly_range_reversal.md`
(row 27 of `forex_swing_strategies.csv`) · **Batch:** 3 · **Written:** 2026-08-16

## Implemented

Single-frame H1, exactly as §2 declares — the "two-week range" is a trailing 336-bar
window on the decision frame, so no context granularity is involved.

- **§3 levels** — `hi2w`/`lo2w` as 336-bar rolling extrema; `rng`, `zone_lo` (12.5%),
  `zone_hi` (87.5%) and `mid` (50%) derived from them.
- **§4.3/§5.3 cross** — CCI(2000) closing back up through 10 (long) or down through 90
  (short), compared against the previous bar's value.
- **§4.4/§5.4 arming** — the touch of 5 / 95 measured over `CCI[t-24 … t-1]`, built as
  `cci.shift(1).rolling(24)` so the arming bar can never be the cross bar (§10 #9).
- **§4.5 throttle** — one emitted intent per FX week per pair, shared across directions
  (§10 #7), consumed only by an intent that is actually emitted. The FX week opens Sunday
  21:00 UTC.
- **§4.6/§5.6 floor** — a hard gate: a setup whose 50%-of-range target does not pay at
  least 2× the distance to the zone-edge stop is dropped, never re-targeted (§10 #4).
- **§6 stop** — 1.0 pip beyond the 2-week extreme, static, no breakeven, no trail.
- **§7 exit** — a single `take_profit` leg at `lo2w + 0.50 × rng`, fraction 1.0. No time
  leg (§10 #6): an open trade outlives its week.
- `RSI(1)` is not implemented (§10 #8), and no swing/pivot construct is used anywhere —
  §10 #1 replaced the discretionary CCI trendline with the pseudocode's cross.

## Deviations

1. **The 1-pip stop buffer infers its quote convention from the decision bar's close.**
   §6 says `pip = get_pip_value(pair)`, but a v2 strategy is never told which pair it is
   running on. The pip *magnitudes* still come from the inventory; only the JPY-vs-major
   convention is inferred, from one completed bar. This is the same interface gap
   `amazing_crossover` and `ema_cross_h4_filter_bot` record, and the same fix.
2. **`pairs` declares the five live instruments.** GBP_USD is the only one of the author's
   two headline pairs that exists; GBP_CAD does not, and the nine "ranging minor"
   candidates of §2 are Wave-1 pending.

## Uncertainties

- **DECISION — §11's frequency estimate is wrong by an order of magnitude, and I did not
  change anything to chase it.** §11 predicts 10–35 trades per pair per year on the
  reasoning that "on a 2000-period CCI, 5/10/90/95 sit near the zero line, so touches and
  crosses are common". The measurement says otherwise: **45 OOS trades across five pairs
  over ~7 OOS years**, i.e. roughly one per pair per year. CCI(2000) spends very little
  time in the 5–10 band, so the arming-then-crossing sequence inside a single day is rare.
  A reviewer should decide whether that invalidates the spec's translation of §4.3/§4.4;
  I implemented the inequalities as written and did not widen the touch window or the
  thresholds to produce trades (§6.3, §7).
- **DECISION — the 24-bar arming window is the spec's own invention** (§10 #9): the source
  says only "CCI has touched the 5 level". Shrinking or widening it changes the trade
  count directly, and it is the single most consequential undocumented parameter here.
- The pooled result is thin: 45 trades over five cells means 8–11 trades per cell, which
  is below any sensible confidence threshold even though the harness did not flag
  `low_confidence` on the pooled row.

## Coverage

- **Declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD.
- **Wanted by the spec but absent:** GBP_CAD (the author's headline pair — the DATA-GAP
  file records it) plus the nine Wave-1 "ranging minors" (EUR_GBP, EUR_AUD, AUD_NZD,
  EUR_CAD, USD_CHF, GBP_JPY, EUR_JPY, NZD_USD). The strategy is explicitly a range-fader
  and the five live pairs are the trendiest of the requested set, so the available
  universe is biased against it.
- **Skipped by the harness:** none.

## Verdict

Harness run 2026-08-16T07:18:43Z — **FAIL**.

| metric | pooled |
|---|--:|
| OOS trades | 45 |
| profit factor | 0.41 |
| Sharpe | −0.88 |
| max drawdown | 24.88% |
| win rate | 8.9% |
| recovery factor | −0.90 |
| OOS months | 83.9 |
| cells passed | 0 of 5 |

What limited it is the win rate: 8.9%, i.e. four winners in 45 trades. That is the direct
consequence of §6/§10 #5's stop — one pip beyond a 2-week extreme that price is currently
touching — combined with F5, which awards the stop when a bar contains both levels. The
1:2 floor is supposed to make a low hit-rate survivable, but at 8.9% it needs better than
10:1 realised payoff and gets 0.41 in profit factor. AUD_USD produced **zero** winning
trades in 11 (PF 0.00, Sharpe −260.6 — see the batch review: that Sharpe is a metrics
artefact of a near-constant loss series, not a meaningful number). GBP_USD, the author's
one available headline pair, is the best cell at PF 2.07 on 8 trades — far too few to mean
anything. Run once; no code changed after the result.
