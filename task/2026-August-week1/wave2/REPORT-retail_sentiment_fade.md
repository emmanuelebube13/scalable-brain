# REPORT — retail_sentiment_fade

**Spec:** `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-retail_sentiment_fade.md`
(row 51 of `forex_swing_strategies.csv`) · **Batch:** 3 · **Written:** 2026-08-16

## Implemented

The complete rule, against the sentiment schema §3 and §9 specify:

- **§9 rule S1** — `eligible_sentiment()`, a public pure function: an observation is usable
  at decision bar *t* only when `published_at <= close(t) - 24h`, and the most recent such
  observation is attached to each bar by `merge_asof`. For D1 (bars stamped at their open,
  closing one day later) that reduces exactly to `published_at <= index[t]`; the 24h
  constant is kept explicit so a different primary granularity keeps the intended buffer.
- **§4/§5 entries** — `short_ratio_pct >= 60` with `SMA20 < SMA50` (long);
  `long_ratio_pct >= 60` with `SMA20 > SMA50` (short). Threshold inclusive (§10 #8).
- **§6 stop / §7 target** — `Close[t] ∓ 1.5 × ATR14[t]` and `Close[t] ± 3.0 × ATR14[t]`,
  both anchored to the decision close; one take-profit leg, fraction 1.0; no breakeven,
  no trail, no time exit.
- **§8 / §10 #6** — `max_concurrent_positions = 1`; the strategy re-emits on every
  qualifying bar (§10 #7) because it cannot observe its own positions, and the engine caps
  admission.

The sentiment series is a constructor argument: `RetailSentimentFade(sentiment=<frame>)`.
The golden fixture supplies a hand-written four-observation series with explicit
`published_at` stamps and pins the entire trade plan, including the 24h lag boundary to
the second.

## Deviations

1. **SMA 20/50 are reconstructed** (§3, §10 #1). The source says only "fast and slow SMA".
   The spec chose 20/50 and I implemented that; it is the single most consequential
   invented parameter in this strategy.

## Uncertainties

- **DECISION — this id cannot be measured, and no substitute was invented.** The retail
  positioning feed does not exist in this repo, for any pair. Handed no sentiment, the
  §4.1/§5.1 gate is unsatisfiable and the strategy emits zero orders. It does **not** fall
  back to trading the SMA alignment alone: that would be a different strategy with a
  different hypothesis, and it would produce a number a reader could easily mistake for a
  verdict on this one.
- **The audit cannot express this state.** `audit_wave2.py` step 8 runs
  `assert_no_lookahead_v2` against real data, which rejects any strategy that emits no
  orders anywhere — correctly, in general, because that is how centred-window look-ahead
  once reached production. Here the same rule fires on a strategy that is behaving exactly
  as specified. `--quick` (steps 1–7) passes: **PASS retail_sentiment_fade**. The full run
  reports `REALDATA` failure with `LookAheadError: emits no orders anywhere in 2594 bars`.
  Recorded in the batch review as a harness-level gap, not fixed here — `audit_wave2.py`
  is a shared file and rule 2 forbids editing it. A `BLOCKED-FEED` verdict alongside
  `BLOCKED-OK` would close it.
- **DECISION — the 24h publication lag is the spec's assumption, not the vendor's.** §9
  admits Ziwox's cadence and revision policy are undocumented. If the real feed publishes
  with a shorter lag the strategy trades earlier and every result changes; if it silently
  restates values, no lag makes the backtest honest.
- §11's own estimate — 150–900 trades over 10 years × 3 pairs — is unverifiable until the
  feed exists, and the feed will need 12–24 months of forward accumulation before a
  walk-forward fold contains a meaningful sample.

## Coverage

- **Declared:** EUR_USD, GBP_USD, USD_JPY — all three named pairs are live in price data.
- **Wanted by the spec but absent:** nothing at the pair level. The gap is the **feed**:
  `fact_sentiment` does not exist for any pair (`DATA-GAP-retail_sentiment_fade.md`).
- **Skipped by the harness:** all three cells — the run does not reach cell evaluation.

## Verdict

**UNMEASURABLE.** The harness cannot produce a verdict:

```
python -m src.layer0.strategies.v2_harness retail_sentiment_fade
LookAheadError: retail_sentiment_fade: emits no orders anywhere in 2594 bars —
look-ahead freedom cannot be demonstrated, so it must not qualify.
```

That message is the correct outcome for a strategy whose only non-price input does not
exist. What the missing feed costs, stated plainly: the behavioural claim at the centre of
this strategy — that a ≥60% retail skew predicts reversion — is **untested and untestable
here**, and no part of the measured fleet speaks to it. The technical half (an SMA-cross
alignment filter) is not a partial answer; on its own it is a different, unremarkable
strategy that several other ids in this fleet already measure.

The code is complete and pinned by its fixture, so the day `fact_sentiment` lands the only
work left is to load it and pass it to the constructor.
