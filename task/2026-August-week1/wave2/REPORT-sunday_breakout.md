# REPORT — sunday_breakout

**Spec:** `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-sunday_breakout.md`
(row 4 of `forex_swing_strategies.csv`) · **Batch:** 4 (multi-timeframe) ·
**Written:** 2026-08-16

## Implemented

One decision per trading week, at the close of the week's opening H4 bar:

- **§9 the Sunday candle** — identified structurally as the first H4 bar of an FX week
  (bar *i* whose FX week differs from bar *i-1*'s), not by a literal
  "Sunday and hour == 21" test, which the 21:00/22:00 DST shift would break. Adding 3h to
  the open stamp puts each session on its own calendar day; the ISO week of that day is
  the FX week.
- **§4/§5 entries** — a `buy_stop` at `sun_high + 10 pip` and a `sell_stop` at
  `sun_low - 10 pip`, emitted together at the same decision bar and independent
  thereafter. Both are provably not through the market at emission.
- **§6 stop** — the opposite end of the Sunday candle;
  `R = (sun_high - sun_low) + 10 pip`, identical for both directions and measured from
  the declared entry level (the only price knowable at emission).
- **§7 exits** — `BE_2R` (fraction 0.01) at ±2R, whose fill triggers the breakeven move,
  and `TP` (fraction 0.99) at ±0.5 × weekly ATR(14). Fractions sum to exactly 1.0.
- **§3 weekly ATR** — computed on the W1 frame, index shifted forward one full weekly
  interval, `merge_asof(direction="backward", allow_exact_matches=False)`, so only
  completed weeks can enter. The fixture makes this testable: its last weekly bar has a
  1000-pip range, and if it leaked into the second decision the target distance would be
  0.01533 instead of 0.01000.
- **§4.6 expiry** — `expires_after_bars = 29`, the count from Monday 01:00 to Friday 17:00
  inclusive, so an unfilled order dies at the Friday close.
- **§8 (F12)** — `max_concurrent_positions = 1`.

## Deviations

1. **The 10-pip offset infers its quote convention from the decision close** — the pair is
   never passed to a v2 strategy. Only GBP_USD is declared, so the inference is
   exercised on a non-JPY pair here; the magnitudes still come from `get_pip_value`.
2. **The strict-inequality merge costs one extra week of ATR freshness** at exactly the
   Sunday-candle bar: the week that ended at that bar's open is excluded rather than used.
   §3 mandates those mechanics, and the direction (a staler, not fresher, ATR) is the
   conservative one.

## Uncertainties

- **DECISION — §10 #8's residual second-fill risk is real and visible in the result.** With
  no OCO in contract v2, nothing cancels the surviving pending when its sibling fills; F12
  only prevents them being open at the same time. The measurement shows **344 OOS trades
  on one pair over ~7 OOS years ≈ 49 per year**, against §11's estimate of 15–35 filled
  trades per year under the intended one-per-week rule. The extra volume is the sibling
  fills the CSV forbids. The spec chose to keep the faithful 29-bar expiry and report this
  rather than truncate the setup horizon; the fix, if a reviewer wants one, is a contract
  extension (cancel-on-fill / OCO group), not a strategy-level hack.
- **DECISION — EUR_JPY was never measured.** §10 #7 records that the author ran a
  "slightly different set of rules" for it which the CSV does not reproduce. The pair is
  absent from this database anyway, so both the pair and the variant remain untested.
- The `BE_2R` trigger is a 1%-size take-profit, not a zero-size marker (§10 #3). It banks a
  hundredth of the position at +2R that the live rule would not, and per F8 the stop moves
  at that bar's close rather than intrabar. Both effects are small and pessimistic.
- §10 #6's Friday close-out is not implemented: `ExitLeg(kind="time")` counts from an
  unknowable fill time, so a calendar exit is inexpressible. Positions carry across
  weekends and eat gap risk (F6) the author would have avoided.

## Coverage

- **Declared:** GBP_USD — the author's primary pair and the only requested one that exists.
- **Wanted by the spec but absent:** EUR_JPY (Wave-1 addition that never landed).
- **Skipped by the harness:** none. The single declared cell produced trades.

## Verdict

Harness run 2026-08-16T07:27:51Z — **FAIL**.

| metric | pooled |
|---|--:|
| OOS trades | 344 |
| profit factor | 0.90 |
| Sharpe | −0.28 |
| max drawdown | 40.1% |
| win rate | 31.7% |
| recovery factor | −0.60 |
| OOS months | 83.9 |
| cells passed | 0 of 1 |

All five gates fail, drawdown worst at 40.1% against a 25% limit. A 31.7% win rate is
normal for a breakout system — the author said himself it "depends on the few big winners
to offset the large number of small losers" — but the winners are not big enough: PF 0.90
means the tail did not pay. Two structural features work against it here, both documented
in advance: the target is capped at half a weekly ATR while the stop is the full Sunday
range plus 10 pips, and the missing OCO adds roughly 40% more trades than the rule intends,
concentrated in exactly the whipsaw weeks where a stop-out precedes an opposite break. This
is a single-cell verdict — one pair, no dispersion to check it against. Run once; no code
changed after the result.
