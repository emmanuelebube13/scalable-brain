# REPORT — weekly_gap_fade

**Spec:** `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-weekly_gap_fade.md`
(row 3 of `forex_swing_strategies.csv`) · **Batch:** 4 (multi-timeframe) ·
**Written:** 2026-08-16

## Implemented

One decision per week, at the close of the week's opening H1 bar:

- **§4/§5 gap test** — `week_open` (the Open of the week's first H1 bar) against
  `prior_week_close` (the Close of the last H1 bar of the previous week), converted to pips.
  A gap of at least 5.0 pips is faded: down-gap → long, up-gap → short.
- **§6 stop** — `W0_close ∓ 5.0 × ATR(14, D1)`, anchored to the decision close, static, no
  breakeven, no trail. The D1 ATR is joined with the mandated one-interval forward shift and
  `allow_exact_matches=False`, so the newest daily bar that can inform a Sunday decision is
  the Thursday-stamped one that closed at Friday 21:00 UTC.
- **§7 exit** — one `ExitLeg(kind="time", fraction=1.0)` whose bar count is computed from the
  calendar: the hours from the fill bar to the coming Friday 19:00 UTC. 117 in a standard
  21:00-open week; the count is derived, never hard-coded (a 22:00-open week gets 116).
- **§4** — market entry, `expires_after_bars=1`, `max_concurrent_positions = 1`.

## Deviations

1. **The week-boundary check is structural, not a literal stamp match** (§4 step 1). §4
   describes the opening bar as "stamped Sunday 21:00 UTC" with a "Friday 20:00 UTC"
   predecessor. In this feed those stamps move an hour with DST — I measured 68 of the last
   108 week openings at 21:00 and **40 at 22:00** — so the literal test would silently veto
   every winter week, about 37% of the sample, and the strategy would report a plausible
   but half-blind result. The implemented check asserts the pattern the spec is describing:
   a session break (predecessor more than one H1 bar behind), the bar falls on a Sunday, and
   the predecessor falls on the preceding Friday. Holiday-shortened weeks and data holes
   still fail it, which is §10 #7's intended veto.
2. **The pip size is inferred from the decision close**, since `calculate_pips(…, asset=…)`
   needs a pair the v2 contract never passes. This matters more here than elsewhere — the
   entry threshold *is* a pip count, and USD_JPY is in the declared set — so the inference
   is what keeps the 5-pip test meaning 5 pips on a JPY pair rather than 0.05.
3. **`pairs` declares the five live instruments.** GBP_JPY — the author's preferred and only
   documented pair — is not in this database, and neither is EUR_JPY.

## Uncertainties

- **DECISION — the exit hour is fixed at 19:00 UTC year-round** (§7, §10 #4). The author
  exits five minutes before the weekly session close. In summer that close is 21:00 UTC and
  the 19:00 bar (closing 20:00) is the last one before it; in winter the close is 22:00 UTC,
  so the same rule exits three hours early. Making the exit hour follow the session would be
  the more faithful reading; §7 states a fixed hour and I implemented that.
- **DECISION — the 5.0-pip threshold is looser than the strategy the author traded** (§8,
  §10 #5). His GBP/JPY spreads were 2–4 pips, implying a 10–20 pip filter. With no spread
  series in the database the F10 cost model's 1.0 pip is the only defensible constant, but
  the consequence is that this measurement trades many more, much smaller gaps than the
  documented sample — 944 OOS trades where §11 predicted 400–700 per pair over 20 years.
  A reviewer who wants the author's strategy should re-run with a 10-pip threshold; that is
  a parameter change and I did not make it after seeing the result.
- **The r-multiple scale is not comparable to other strategies in this fleet** (§6, §10 #1).
  A 5×ATR catastrophic stop makes the risk denominator 3–5× wider than an ATR-harness
  strategy's, so |r| values here are compressed toward zero by construction. PF and win rate
  are unaffected; Sharpe and recovery factor are not comparable across ids without it.
- No stop-loss existed in the source at all. The stop is an invention of the spec, forced by
  `OrderIntent` requiring one.

## Coverage

- **Declared:** USD_JPY, EUR_USD, GBP_USD, AUD_USD, USD_CAD.
- **Wanted by the spec but absent:** GBP_JPY (the author's preferred pair, and the only one
  his +1,612-pip claim covers), EUR_JPY, NZD_USD, USD_CHF. Also absent: the per-pair average
  spread series the entry threshold is supposed to be built from.
- **Skipped by the harness:** none. All five cells produced trades.

## Verdict

Harness run 2026-08-16T07:32:18Z — **FAIL**.

| metric | pooled |
|---|--:|
| OOS trades | 944 |
| profit factor | 0.96 |
| Sharpe | −0.18 |
| max drawdown | 11.91% |
| win rate | 48.2% |
| recovery factor | −0.40 |
| OOS months | 83.9 |
| cells passed | 0 of 5 |

Three gates fail; win rate (48.2%) and drawdown (11.9%) both pass. This is the most
*coherent* failure in the batch: a nearly-even coin with a profit factor just under 1, on
the largest sample any strategy in this fleet produced. The gap is faded correctly about
half the time and the average win does not cover the average loss after the F10 cost model —
which is exactly what §11 warned would happen once the threshold was loosened to 5 pips.
Dispersion is tight and uniformly negative: the best cell is USD_JPY at PF 1.005 (201
trades), the worst AUD_USD at 0.893 (177), so this is not a one-pair artefact but a
consistent small negative edge across all five. Run once; no code changed after the result.
