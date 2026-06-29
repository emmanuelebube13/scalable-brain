# FIX-S2-003 — Live pipeline can never act on existing data (H1 default vs H4-only signals; 60-min freshness vs H4 cadence)

**Severity:** P1 (the pipeline no-ops on every scheduled run; a guard/window that is never satisfiable)
**Status:** Proposed
**Author:** Claude (System-2 audit)
**Date raised:** 2026-06-26
**Scope:** `src/layer4_executor/live_pipeline.py` (`DEFAULT_GRANULARITY`, freshness window) + `shell/cron_layer4_pipeline.sh`
**Affected pipeline:** Layer 2 (signal producer) → Layer 4 Stage 1 (signal load)
**Risk to live trading:** None directly (it under-acts), but the live executor is effectively dead.

---

## 1. Executive summary

The live executor and the cron job both default to **granularity H1**, but Layer 2 has only ever
produced **H4** signals. So the hourly production run queries H1, finds zero rows, and exits
"no eligible signals" every time. Even if pointed at H4, the default **60-minute freshness
window** is mismatched to the H4 bar cadence (240 minutes) and the data is multi-day stale, so it
would still load nothing. The pipeline is structurally inert against the data that actually
exists.

---

## 2. Evidence (real data + code)

Signals present in `fact_signals` (live DB):
```
granularity | count
H4          | 21616      -- and ZERO H1
signal_value: -1 → 11013, +1 → 10603
time range: 2006-01-04 … 2026-06-23   (staleness vs now ≈ 3 days 6h)
```
Regime coverage exists for H1 (648,060 rows), H4 (164,428), D1 (29,108) — so the H1 *regime* is
populated, which makes the H1 default look plausible while no H1 *signals* exist.

Consumer defaults (`live_pipeline.py:117`): `DEFAULT_GRANULARITY = "H1"`.
Cron (`shell/cron_layer4_pipeline.sh`): `GRANULARITY="H1"` → `ARGS="--granularity $GRANULARITY"`.
Stage-1 loader filters `s.Granularity = :granularity` (`live_pipeline.py:479`) → H1 → 0 rows →
`run()` logs "No signals to process" and returns `[]` (`live_pipeline.py:1782-1784`).

Freshness window (`live_pipeline.py:1746,1882-1886`): default `lookback_minutes = 60`. For H4,
bars close every 240 min, so a 60-min window catches at most ~25% of bars even with fresh data;
with the newest signal 3+ days old, the window matches **nothing**. (`--lookback-bars` converts
bars→hours as `bars*4` for H4 at `live_pipeline.py:487`, but the cron path never sets it.)

---

## 3. Root cause

A granularity contract was assumed (H1) that the upstream producer never satisfied (H4 only),
and the freshness window was sized for an H1 cadence and a continuously-fed table — neither of
which holds. Because an empty result is (correctly) treated as a valid operational state
(exit 0), the mismatch produces no error and is invisible in cron logs.

---

## 4. Proposed fix

1. Make granularity **explicit and validated against available data**: on startup, if the chosen
   granularity has zero recent signals but another granularity does, log a loud WARNING naming
   the populated granularity. Set the cron `GRANULARITY` to the one Layer 2 actually emits (H4),
   or run both.
2. Size the freshness window to the bar cadence: default `lookback_minutes` ≥ one bar
   (H1→≥60, H4→≥240) — ideally derive it from granularity rather than a fixed 60.
3. Add a no-op guard that distinguishes "no fresh signals (normal quiet market)" from "wrong
   granularity / stale producer" by also counting rows ignoring the freshness filter and warning
   when the only rows are far outside the window.

---

## 5. Validation plan

1. With `--granularity H4` and an appropriate window, assert Stage 1 returns >0 rows on the
   current DB; with H1 assert it returns 0 and emits the new WARNING naming H4.
2. Unit-test the freshness window derivation: H4 → ≥240 min.

---

## 6. Rollout / risk

Config/log change plus a window default; no schema impact; reversible. Pair with FIX-S2-001/002
before any live run, otherwise switching to H4 will start routing signals through the broken ML
gate and broker logging.

---

## 7. One-paragraph summary

`fact_signals` contains only H4 signals (21,616 rows; zero H1), yet both `DEFAULT_GRANULARITY`
and the cron job run with `--granularity H1`, so every scheduled execution loads zero signals
and exits. Even targeting H4, the default 60-minute freshness window is far shorter than the
240-minute H4 bar cadence and the newest signal is ~3 days old, so nothing matches. The live
executor is therefore inert against real data. Fix by aligning the cron/default granularity to
what Layer 2 emits, deriving the freshness window from the bar cadence, and warning loudly when
the chosen granularity has data only outside the window.
