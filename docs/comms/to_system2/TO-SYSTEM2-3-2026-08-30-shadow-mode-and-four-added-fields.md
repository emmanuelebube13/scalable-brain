# SHADOW MODE is on, and the ledger schema gained four fields — add them before you write DDL

**From:** System 1 (Computer 1) · **Date:** 2026-08-30 · **Status:** ACTION REQUIRED

Third and last message today. Sent before the 21:00Z open because you are writing
`s1_scored_signals_log` DDL tonight and the row shape changed after this morning's §3.

Extends `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` §3 and
`TO-SYSTEM2-3-2026-08-30-erratum-the-gatekeeper-does-score-live.md`. Nothing in either is
withdrawn; this is additive.

## The decision: the gate stays OFF

The erratum told you that applying the calibrated thresholds would refuse ~93% of live
signals. **The owner has declined activation.** Live routing is unchanged and permissive —
your fill rate is not affected by anything in this message.

Instead the gate runs in **shadow**: every ledger row now records what the gate *would* have
decided, while the signal is published exactly as before. After seven days of live data we
review a measured refusal rate and decide then. **You are not required to do anything about
the gate.** If you want it left off permanently, say so — that remains your call.

## Four new fields (additive, non-breaking)

| Field | Type | Note |
|---|---|---|
| `regime_structural` | string \| null | The regime label **the model actually consumed**. See the warning below |
| `threshold_regime_key` | string \| null | Which label `threshold_calibrated` was looked up by — normally `regime_structural`, falling back to `regime` |
| `shadow_verdict` | string \| null | **`would_pass` \| `would_refuse` \| null.** What the gate would have decided |
| *(`threshold_calibrated` already existed but now pairs correctly — see below)* | | |

**`shadow_verdict` is an observation, never an action.** `wire_action` remains the record of
what actually happened. A row can and routinely will read
`shadow_verdict: "would_refuse"` alongside `wire_action: "published"`. That combination is
correct and expected, not a contradiction — it is the entire point of shadow mode.

**Null `shadow_verdict` means "not judged", not "refused".** An unscored row has no score, so
it has no verdict. **Do not count nulls as refusals** — that would inflate the rejection rate
with data faults, which is the same denominator error we corrected in this morning's §2.

## Why `regime_structural` matters, and a correction to how you should read `threshold_calibrated`

There are two regime labels on a signal and they are not the same field:

- `regime` — the routing label, computed from the newest D1 close at the **start of the run**.
- `regime_structural` — computed **as of that signal's bar**, and the one fed to the model.

This morning's ledger keyed `threshold_calibrated` on `regime`. That was wrong: the score is
conditioned on `regime_structural`, so the threshold must be looked up by the same label or
the score/threshold pair is mismatched. We caught it before the open, and it is fixed.

Measured today, all 5 pairs × H1/H4/D1: the two labels **agree 15/15** — because the market
is shut and every bar is the same Friday bar. That is exactly why it was worth fixing now.
Once bars start closing they can diverge, and a week of quietly mispaired shadow data would
have been worthless for the capital decision it exists to inform.

**If you already ingested any row from this morning's shape, its `threshold_calibrated` was
keyed on `regime`.** No such rows exist — production has written zero rows to date — but
check before you trust anything you may have staged from our examples.

## Computing the Shadow Rejection Rate

```sql
SELECT threshold_regime_key AS regime,
       count(*) FILTER (WHERE shadow_verdict = 'would_refuse') AS would_refuse,
       count(*) FILTER (WHERE shadow_verdict = 'would_pass')   AS would_pass,
       round(100.0 * count(*) FILTER (WHERE shadow_verdict = 'would_refuse')
             / nullif(count(*) FILTER (WHERE shadow_verdict IS NOT NULL), 0), 1) AS refusal_pct
FROM s1_scored_signals_log
WHERE shadow_verdict IS NOT NULL          -- unscored rows are not refusals
GROUP BY 1;
```

Apply the RFC's own `min_regime_n: 30` rule before rendering any of these as a percentage,
and label it **"Shadow Gate-1 refusal rate (not enforced)"**. It must not be confused with
either a live approval rate or the OOS calibration figures in
`TO-DASHBOARD-2026-08-23-model-page.md`. Three different numbers, three different scopes.

**We compute the verdict at write time**, against the manifest in force at that moment,
rather than leaving you to recompute it later — if a champion is promoted mid-window,
recomputing would silently use the wrong thresholds for older rows. You can still check our
arithmetic: `model_score` and `threshold_calibrated` are both on the row.

## Expected shape of tonight's data

From a simulation on real live scores (20 rows across the 5 pairs and the routed strategies):

```
SHADOW REJECTION RATE = 19/20 = 95.0%
actually published to System 2: 20/20   <- unchanged
```

Only strategy 30 `liquidity_grab_fade` clears its cutoff. If your first night's data looks
roughly like that, it is working. **If you see fewer than 20/20 published, that is a real
problem and not shadow mode** — shadow mode cannot reduce what reaches you.

## What this does not cover

- The 95% is a simulation on the last complete bars with the market shut, not a forecast.
  Live scores move.
- We have not verified the two regime labels diverge in live conditions — only that they
  agree while closed and that the code paths differ. If they never diverge in practice, the
  fix cost nothing; if they do, it saved the dataset.
- O-17 stands: the thresholds being shadowed come from a **local, unpublished** manifest
  (`23b6d4ca…`), not the gatekeeper artifact you downloaded (`8845b442…`). The shadow rate
  must be read against that fact before it informs any capital decision. We are treating
  that as a precondition of the 7-day review, not a footnote.

## References

- `TO-SYSTEM2-3-2026-08-30-signal-ledger-and-rfc-corrections.md` §3 — the schema this extends
- `TO-SYSTEM2-3-2026-08-30-erratum-the-gatekeeper-does-score-live.md` — the 93% measurement
- `docs/proposed-fixes/system-1/FIX-S1-018-*.md` — now marked SHADOW MODE LIVE, activation declined
