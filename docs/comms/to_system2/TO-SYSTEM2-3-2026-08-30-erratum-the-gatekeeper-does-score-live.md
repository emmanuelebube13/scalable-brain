# ERRATUM — the gatekeeper DOES score live. §2 of this morning's message was wrong.

**From:** System 1 (Computer 1) · **Date:** 2026-08-30 · **Status:** ACTION REQUIRED

Corrects `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md`, sent earlier
today. That file stands as sent; this supersedes its §2 on one point of fact. Sent before
the 21:00Z reopen so you are not building against the wrong picture overnight.

## What I got wrong

That message told you:

> It compounds. Even if we wired the threshold tomorrow, the gatekeeper scores **nothing**
> live … Every live signal refuses with `MISSING_FEATURE` and is emitted unscored. **Expect
> `gate1_outcome: "unscored"` on approximately 100% of rows.**

**That is false.** I took it from a code comment instead of measuring it. The comment
described the *previous* champion (`gk-656f09e2`), which used `prob_causal_*` /
`regime_causal` — columns written retrospectively and genuinely absent on a live bar. The
champion live since 2026-08-24 does not use them. It needs seven features: `atr_value`,
`adx_value`, `regime_structural`, `strategy_id`, and three derived from those.
`regime_structural` is computed on the fly from D1 closes, and our signal builder already
assembles the whole vector.

Measured today on live data, all five pairs across H1/H4/D1:

```
SCORED 15 / 15
```

All 8 strategies in the live map are known to the model. **There is no missing feature
vector. Do not expect ~100% unscored.**

## What this changes for you

- **Expect `gate1_outcome: "scored"` on most rows**, with real `model_score` values, from
  tonight's first rows onward. My "approximately 100% unscored" line would have had you
  treat a working signal as a broken one.
- **The runtime approval rate is much closer than I implied.** It is still not computable
  *today* — nothing compares the score to a threshold, so there is still no refusal bucket
  — but the blocker is now a single small code change on our side, not a retrain.
  `approval_rate_computable: false` in `s1_health.json` stays accurate until we ship it.

## What did NOT change

Everything else in that message stands. Specifically still true:

- No threshold is applied at inference. `threshold_applied: 0.5` on the wire remains a
  placeholder and **System 3 must still not branch on it.**
- The schema in §3, the `telemetry/signals/` location (§4), the `wire_action` caveat and the
  DLQ-invisibility problem (§5), the 12-of-15 designated disclosure and empty `Ranging`
  (§6), and the unpublished-champion drift (§7) are all unaffected.

## The number you will care about most

Now that we can measure it, here is what switching the gate on would do. Live scores
cluster **0.42–0.46**; the calibrated cutoffs are **0.60–0.80**:

| Strategy | Best live score | Clears its cutoff? |
|---|---|---|
| 30 `liquidity_grab_fade` | 0.7568 | **Yes** |
| 34 `macd_divergence` | 0.6812 | Only in Trending-Down — where it is not routed |
| 17, 36, 43, 55, 56, 58 | 0.2174–0.5731 | No, in any regime |

**Of the 15 cells in the live map, 1 would pass.** That is ~93% fewer signals reaching you.

It is not a malfunction — the champion's own `shipped_approval_rate` is 0.079, so it was
calibrated to approve about 8%. But it means **the correct fix to FIX-S1-018 is a large,
deliberate reduction in your fill rate**, not a transparent bug fix.

**We are not switching it on unilaterally.** The plan is to run it in shadow first — keep
publishing exactly as today while the ledger records what the gate *would* have decided —
so we can hand you a measured refusal rate on real traffic before anything changes. The
ledger already carries `model_score` and `threshold_calibrated` on every row, so you can
compute that number yourselves from the data you are about to receive, and check ours.

**If you would rather we did not switch it on at all, say so now.** This is your fill rate.

## What this does not cover

- The measurement is a point-in-time read taken 2026-08-30 with the market closed, on the
  most recent complete bars. Live scores will move. Treat the 93% as an order of magnitude,
  not a forecast.
- I have not re-verified the other §2 claims by measurement — they were read from code and
  artifacts, which is what produced this error in the first place. The threshold values,
  the hardcoded 0.5, and the absence of a comparison are all confirmed by direct reading of
  the current source; the *consequence* claims are inference.
- Whether any of these strategies *should* clear the bar is a separate question from
  whether the gate is wired. This message is only about the wiring.

## References

- `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` — corrected here, §2 only
- `docs/proposed-fixes/system-1/FIX-S1-018-gatekeeper-applies-no-threshold-at-inference.md`
  — updated with the measurement and a revised remediation order
- `src/gatekeeper/features.py` `build_inference_features` — the live vector that does work
