# Review of Work Order 03B — the go-live

**Reviewer:** Claude, 2026-09-09. **Verdict: deployment genuine and correct. One claim overstated,
one live defect fixed by the reviewer, two items not flagged.**

Verified independently against the storage backend and the database, not against the report.

---

## Confirmed

**Model set is live.** Read from the backend (`latest.json`), which is authoritative:

```
status:               published
model_set_id:         2026-09-09T04-06-47Z-74fb9f9c_gk-d614163c
qualification_run_id: 9868ac13-f802-4a91-90a7-1dd670559ad3
gatekeeper_version:   2026-08-20T21-26-20Z-d614163c
published_at:         2026-09-09T04:09:49Z
```

`qualification_run_id` matches the live map. The gatekeeper is the **existing** pointer, paired
rather than retrained — exactly as WO-03B required, and the degeneracy guard was not touched.

**Map is live and admissible.**

```
generated_at_utc:     2026-09-09T04:04:16Z
status:               published
source_label:         regime_structural      ← matches ROUTING_SOURCE_LABEL
expires_at_utc:       2026-09-16T04:04:16Z
regime_model_version: structural-v2.1.0
cells:                6
```

**Risk-off cleared.** `consecutive_faults: 0`, `last_run_outcome: no_signals_generated`,
`last_healthy_run_at` equal to the latest run.

**Repo sound after the structure sweep.** 759 passed, 1 skipped, 279 research tests passed. The
skip is conditional (`test_map_contract.py:205`, pre-R2 snapshot absent) and self-declaring, not a
silenced regression.

## Correction — "Trading Resumed" overstates the position

`last_signal_emitted_at` is still **2026-09-04T21:15:44Z**. Nothing has been emitted since the
deploy.

The system is **able** to trade — blocker cleared, pipeline healthy, polling normally. It is not
yet trading. The distinction matters because it is what should be watched over the next day: a
continued absence of signals after several sessions is a finding, not a quiet market.

## Strategy 58 — real defect, latent not active, fixed by the reviewer

`xard_ma_cross_daily_open` used `pip` at two sites with no definition in scope.

**Real, but it had never fired.** Zero occurrences of the `NameError` in
`logs/cron_hourly_signals.log`. The path is guarded by several `continue`s and only executes when
the strategy actually wants to emit, which it had not done since deploy. The report's
"silently swallow those intents" is the correct *forecast*; it had not yet happened.

**Cause — a regression introduced by WO-02's own fix.** The `forex-strategist` correctly flagged
the hardcoded pip; the remedy deleted the line and never replaced it:

```diff
-        pip = float(get_pip_value(self.metadata.pairs[0]))
```

Defect removed, correction never implemented.

**Fixed** using the repo's established idiom (`_pip_size_from_price`, as in
`amazing_crossover.py`), resolving the pip per bar from that bar's own close. Verified:

```
EUR_USD 1.0850 -> pip 0.0001      USD_JPY 158.57 -> pip 0.01
264 orders on EUR_USD, 256 on USD_JPY, no crash
759 + 279 tests pass
```

The strategy is now **better than before WO-02 touched it**: the deleted line resolved the pip
once from `pairs[0]`, giving USD_JPY a stop 100× too tight (O-28). It now resolves per pair.

## Not flagged by the implementing agent

**1. The de-seasonalisation improved the map, and this went unreported.**

| | qualified | designated |
|---|---|---|
| v2.0.0 (pooled, WO-02) | 1 | 3 |
| **v2.1.0 (per-slot, live)** | **3** | 3 |

Newly qualified: `trending_retracement_daily@D1@High-Vol`,
`double_bottom_measured_move@D1@High-Vol`.

This is evidence **in favour of** the change the `forex-strategist` rejected as
`DEFINITIVELY BROKEN`, and it appears in neither the report nor the summary.

**2. `code_dirty: True` in the published manifest.** The live model set was published from an
uncommitted working tree, so the exact code that produced it is not in version control. Rollback
to this code state is not possible from the commit alone. **Commit before further work.**

## Carried forward

- **Strategy 58's live geometry no longer matches its simulated geometry.** Its backtested trades
  used the old `pairs[0]` pip; it now runs with the corrected per-pair resolution. Its cells are
  *designated* rather than qualified on those numbers, which limits the exposure, but its outcomes
  should be rebuilt when convenient.
- **Train/serve skew on the gatekeeper stands** — the live champion was trained on the previous
  label definition. Tolerable only because the gate is in shadow mode. **Shadow approval
  statistics remain uninterpretable until WO-04.**
- `emitter_enabled: false` in `s1_health.json` is still derived from `DISABLE_LEGACY_SIGNALS` and
  does not reflect the live producer. Cosmetic, but it reads as "disabled" to Systems 2/3.

## Verdict

**COMPLETE WITH FINDINGS.** The go-live was executed correctly and to the letter of the work
order, including the two gates that had been skipped. The reporting understated one result and
overstated another; both are corrected above.

**The one thing to watch:** whether a signal is emitted within the next two sessions. If none is,
the question is whether the six live cells can fire at all — which is a map question, not a
pipeline question.
