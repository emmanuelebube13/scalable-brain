# FIX-XC-004 — Granularity contract gaps across the handoff (H1 signals missing; D1 regime produced-but-unconsumed)

**Severity:** P2 (correctness-adjacent: silent zero-output runs + produced-but-dead data; no impossible numbers)
**Status:** Proposed
**Author:** Claude (cross-cutting auditor)
**Date raised:** 2026-06-26
**System:** Cross-cutting (granularity alignment across Layers 1/2/3/4)

---

## 1. Executive summary

Three layers disagree about which granularities actually flow end-to-end. `fact_signals` contains **only
H4** rows, yet Layer-4 **defaults to `--granularity H1`** and the canonical run order / CLAUDE.md present
H1 as the primary path — so the default live run finds zero signals and exits 0 (looks healthy, does
nothing). Conversely, the HMM regime engine's **documented "primary" granularity is D1** and it writes
29,108 D1 regime rows, but Layer-3 and Layer-4 hard-restrict to `{H1, H4}`, so the D1 regime is
**produced but never consumed**. These are quiet contract mismatches that waste compute and mask "the
pipeline isn't actually running on what you think."

---

## 2. Evidence

Granularity coverage in the live handoff tables:

```
fact_market_prices   : M15 2,553,691 | M30 1,280,826 | H1 648,195 | H4 164,563 | D1 29,243 | W1 5,340
fact_market_regime_v2: H1 648,060 | H4 164,428 | D1 29,108
fact_signals         : H4 21,616            <-- NO H1 rows at all
fact_trade_outcomes  : H1 115,754 | H4 18,766
```

**Gap A — H1 signals do not exist, but H1 is the default execution path.**
`src/layer4_executor/live_pipeline.py` documents and defaults the H1 run (`:28` `python live_pipeline.py
--granularity H1`; `:487` `hours_back = lookback_bars if granularity == "H1" else lookback_bars * 4`), and
CLAUDE.md's canonical commands lead with `--granularity H1`. With `fact_signals` H4-only, the H1 path hits
"No signals found … returns exit code 0 (valid operational state)" — a green run that trades nothing. The
mismatch is invisible unless someone queries the table.

**Gap B — D1 regime is produced but unconsumable.**
`src/system1/regime/hmm_regime.py:50` `REGIME_GRANULARITIES = ["D1", "H4", "H1"]` and its docstring calls
**D1 the primary** regime granularity; it writes 29,108 D1 rows. But Layer-3
(`src/layer3_ml/train_ml_gatekeeper.py:20` and `training/train_ml_gatekeeper.py:81`) and Layer-4
(`live_pipeline.py:472`) hard-restrict to `SUPPORTED_GATEKEEPER_GRANULARITIES = {"H1","H4"}` and filter it
out (`build_query_with_contract:341` `fmr.<gran> IN ('H1','H4')`). So the engine's "primary" output is
dead weight downstream.

**Gap C — H1 trade outcomes exist but cannot train.**
`fact_trade_outcomes` has 115,754 **H1** outcomes, but Layer-3 training joins `fmr=fs=fto` on equal
granularity (`training/train_ml_gatekeeper.py:329-331`); with `fact_signals` H4-only, the H1 outcomes can
never join a signal → the majority of labelled outcomes are unreachable for the gatekeeper.

---

## 3. Root cause

Each layer encodes its own granularity assumption (Layer-4 default H1, HMM "primary" D1, Layer-3 `{H1,H4}`)
with no single shared manifest of "granularities that are actually populated end-to-end," and no startup
assertion that the requested granularity has upstream rows. Defaults and docs were written for an H1 world
that the data no longer reflects (signals are H4-only in the current state).

---

## 4. Proposed fix

1. **Fail loud, not silent.** At Layer-4 (and Layer-3) startup, assert the requested granularity has rows
   in every upstream table it will join; if not, exit non-zero with a clear "no upstream H1 signals"
   message instead of a green no-op. Distinguish "0 eligible after gating" (valid) from "0 because the
   granularity is unpopulated" (misconfiguration).
2. **Align the default to the data** (or document the H4-only reality): make Layer-4's default granularity
   match what `fact_signals` actually contains, or generate H1 signals if H1 is intended.
3. **Reconcile D1.** Either extend the supported set to consume D1 regime where it adds value, or stop the
   HMM engine from writing a granularity no downstream layer reads (and fix the "D1 primary" docstring).
4. **Publish one granularity manifest** (single source of truth) that all layers import, instead of three
   independent literals.

---

## 5. Validation plan

- Startup assertion test: a Layer-4 H1 run against the current DB exits non-zero with "no H1 signals," not 0.
- Coverage query in CI: for each `(producer, consumer)` edge, the intersection of populated granularities is
  non-empty for the configured run granularity.
- After alignment, a default Layer-4 run reaches the gating stage with a non-empty signal set.

---

## 6. Rollout / risk

- **Rollout:** purely additive guards + config/doc alignment; no schema or trade-logic change. Low risk.
- **Risk if not fixed:** operators believe the live pipeline is running (exit 0) while it silently trades
  nothing; expensive D1 regime fits are wasted; 115k H1 outcomes sit unusable for training.

---

## 7. One-paragraph summary

The handoff tables disagree on granularity: `fact_signals` is **H4-only**, yet Layer-4 defaults to and
CLAUDE.md leads with `--granularity H1`, so the default live run finds no signals and exits 0 (a healthy-
looking no-op). Meanwhile the HMM engine calls **D1 its primary** regime and writes 29,108 D1 rows that
Layer-3/4's `{H1,H4}` restriction silently drops, and 115,754 **H1** trade outcomes can never join the
H4-only signals for training. None of this throws — it just quietly does nothing or wastes compute. Fix:
assert upstream granularity coverage at startup (fail loud), align the Layer-4 default to the data, reconcile
or stop producing D1, and publish one shared granularity manifest instead of three independent literals.
