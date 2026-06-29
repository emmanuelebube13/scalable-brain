# FIX-S1-001 — Fix the System-1 Financial-Metrics Engine (Strategy Qualification)

**Severity:** P0 (corrupts qualification results)
**Status:** IMPLEMENTED & validated on real data — pending corrected-map promotion (sign-off)
**Author:** Claude (diagnostic + proposal + implementation)
**Date raised:** 2026-06-25 · **Implemented:** 2026-06-26
**Scope:** `src/system1/attribution/metrics.py` (+ skill contract, vetting gate calibration)

> **Implementation note (2026-06-26):** Fix applied to `metrics.py` + `attribute.py`, tests rewritten
> (62/62 System-1 tests pass), and re-run on all 134,520 trades. Result: max-drawdown now bounded
> 0–100% (was up to 118,280%), Sharpe now −3.2…+3.7 (was up to 42.5), survivor Sharpe 42 → 2.24.
> The corrected `proposed_regime_strategy_map.json` now covers **Trending-Up** (previously empty) and a
> 2nd **Ranging** cell; **High-Vol** correctly drops out (its only candidate, 27 trades, Sharpe 0.79,
> falls just below the 0.80 gate — the gate working honestly, not a bug). The live/promoted map is
> untouched; promotion awaits sign-off. See §6 validation and the register README.
**Affected pipeline:** MODEL-004 (attribution) → MODEL-005 (vetting & regime map) → MODEL-007 (bundle to Computer 2)
**Risk to live trading:** None if executed in log-only mode (no artifact promotion until re-reviewed).

---

## 1. Executive summary

The strategy-qualification result we currently ship (`regime_strategy_map.json`) selects **one strategy
(`Range_Stochastic_Divergence`, id 10) across three regimes, with `Trending-Up` empty**. The natural
question — "is the picker too strict, or are the strategies just bad?" — has a third answer that the data
supports: **the metrics feeding the gate are computed with two unit-level bugs, so neither the rejections
nor the single survivor can be trusted.** Until they are fixed we cannot tell which strategies are
genuinely profitable, and the regime→strategy map shipped to Computer 2 is built on unreliable numbers.

This document presents the evidence, the root cause, a concrete fix, and a no-risk validation/rollout plan.

---

## 2. Evidence (from the 2026-06-24 run, `qualification_run_id 0ff4142d…`)

80 strategy×regime cells evaluated; **3 qualified** (all strategy 10). Two impossible patterns appear:

**A. Rejections cite physically impossible drawdowns.** Of the 70 rejected cells that cite the MaxDD
gate, **67 report MaxDD > 100%**, the worst being **MaxDD = 118,280%**. A drawdown of an equity curve
cannot exceed 100% — you cannot lose more than your capital. These numbers are not "bad strategies," they
are a broken measurement.

| Example rejected cell | Reported metrics |
|---|---|
| `Trend_EMA_ADX_H1@H1` / Ranging | PF 0.84, Sharpe **−6.43**, MaxDD **118,280%**, WinRate 32% |
| `Trend_EMA_ADX_H1@H1` / Trending-Up | PF 0.85, Sharpe −5.77, MaxDD **51,043%** |

**B. The single survivor's numbers are impossibly good.** Strategy 10 reports **Sharpe = 42.5** and
**Recovery = 18.7**. A real annualized Sharpe above ~3 is world-class; 42 is not attainable. So the
qualifier rejected the field for impossible reasons and promoted the winner on an inflated number.

Conclusion: the gate thresholds (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo) are
**reasonable**; the **inputs** to the gate are wrong. This is a measurement bug, not a strictness problem.

---

## 3. Root cause

All metrics are computed in `src/system1/attribution/metrics.py` from per-trade **R-multiples**
(`r_multiple` in `fact_trade_outcomes`). There is **no capital base and no per-trade duration** in the
data. Two functions misuse the R-multiple series:

### Finding 1 — Sharpe is annualized by *bar* frequency, not *trade* frequency  (P0)
```python
ppy = PERIODS_PER_YEAR.get(granularity, 252)   # H1 = 6048, H4 = 1512
return (np.mean(r) / std) * np.sqrt(ppy)
```
`r` is one value **per trade**, but it is scaled as if one trade occurs **every H1 bar** (6048/yr). The
survivor made 167 trades over ~120 months ≈ **17 trades/yr**, not 6048. Correct scale is `√17 ≈ 4.1`, not
`√6048 ≈ 77.8` — an **~19× overstatement**. `42.5 / 19 ≈ 2.2`, a believable real Sharpe. This inflation
is why the winner "won," and the same mis-scale produces the absurdly negative Sharpes on the losers.

### Finding 2 — Max-drawdown is an unbounded R-ratio, not a percent of capital  (P0)
```python
equity = np.cumsum(r) + 1.0      # cumulative R, offset by 1
dd = (peak - equity) / peak      # blows up when equity goes negative
```
For a losing strategy, `cumsum(r)` goes deeply negative, `equity` crosses zero, and
`(peak − equity)/peak` explodes into the thousands of percent. A drawdown that should live in `[0, 1]` is
unbounded. The MaxDD≤25% gate is therefore meaningless against this input. (`recovery_factor` is R/R so it
is internally consistent, but it is built on the same fragile cumulative-R curve.)

### Finding 3 — "OOS≥60 months" is measured on in-sample span, not true out-of-sample  (P1, flag-only)
`attribute.py` derives `oos_months` from the calendar span of each cell's trades and comments that the
backtests are full-history, not walk-forward. So the OOS gate that MODEL-005 advertises is currently a
**coverage proxy, not real out-of-sample validation.** This does not produce impossible numbers, but it
**overstates confidence** and should be named honestly and fixed separately (see §7 Non-goals).

---

## 4. Proposed solution

Two principles: (a) make every metric **unit-correct and bounded**, and (b) introduce an explicit,
documented **capital model** so "drawdown %" means what the gate thinks it means.

### 4.1 Adopt a fixed-fractional capital model (new, documented assumption)
Convert the R-multiple series into a real equity curve by risking a fixed fraction `f` of equity per trade
(compounding):
```
equity_0 = 1.0
equity_i = equity_{i-1} * (1 + f * r_i)        # r_i in R-multiples
```
- `f = risk_per_trade_fraction`, default **0.01 (1%)**, aligned with the system's existing
  "Quarter-Kelly, 2% risk cap" execution philosophy (Layer 7). Configurable.
- This is bounded by construction: a −1R stop is a −1% equity move, so `equity` stays positive and
  drawdown stays in `[0, 1)`. It also makes the numbers translate directly to real account behavior.
- Profit Factor and Win Rate are trade-level and **unchanged**. Sharpe is a ratio, so `f` cancels and does
  **not** affect Sharpe — only the annualization (Finding 1) does.

### 4.2 Fix the metric definitions
| Metric | New definition |
|---|---|
| **Sharpe (annualized)** | `(mean(r)/std(r)) * sqrt(trades_per_year)`, where `trades_per_year = trade_count / years_spanned` (from entry timestamps). Stop annualizing by bar frequency. |
| **Max Drawdown** | Peak-to-trough of the **fixed-fractional equity curve** (§4.1); returns a fraction in `[0, 1]`. Assert the bound in tests. |
| **Recovery Factor** | `total_return_pct / max_drawdown_pct` on the same equity curve (both in % terms), instead of raw R/R. |
| **Profit Factor / Win Rate / Expectancy / Avg-R** | Unchanged (already correct). |

### 4.3 Update the contract + propagate
- Update the `financial-metrics` skill doc so the canonical formulas match (it currently prescribes the
  buggy bar-frequency Sharpe and an unbounded MaxDD — the code faithfully implemented a wrong spec).
- Add `risk_per_trade_fraction` to the run config + record it in `regime_strategy_map.json` lineage so the
  map is reproducible and the assumption is auditable.
- No schema change required (`fact_strategy_regime_attribution` columns are reused with corrected values).

---

## 5. Expected impact (hypotheses to confirm, not promises)

- Survivor Sharpe drops from ~42 to **~2** (plausible, still strong).
- Impossible 1,000–118,000% drawdowns collapse into the **0–100%** range; the MaxDD≤25% gate becomes
  meaningful and starts discriminating on real risk.
- **Several currently-rejected variants likely move into qualifying range** once judged on correct
  drawdowns — directly addressing "why is there only one strategy?" without weakening any gate.
- The regime map may go from 1 strategy → a small ranked set per regime, reducing concentration risk
  (and possibly filling `Trending-Up`).

---

## 6. Validation plan (how the judge confirms it works)

1. **Unit / property tests** (new): MaxDD ∈ [0,1] for any input incl. all-losing series; Sharpe scales
   with `√trades_per_year`; a known hand-computed series matches expected Sharpe/MaxDD/Recovery; `f`
   does not change Sharpe; PF/WinRate unchanged vs. today.
2. **Sanity bounds gate:** add a self-check in attribution that *fails the run* if any emitted MaxDD > 1.0
   or |Sharpe| > 10 — so this class of bug can never silently ship again.
3. **Log-only re-run** of MODEL-004→005 producing `proposed_*` artifacts **without promotion**; diff the
   before/after metric distributions and attach to the review.
4. **Cross-check** one strategy's corrected Sharpe/MaxDD by an independent offline computation.

---

## 7. Rollout, risk, and non-goals

- **Rollout:** log-only first (MODEL-005 already supports a log-only mode). Artifacts are versioned; the
  current `regime_strategy_map.json` stays authoritative until the corrected map is reviewed and promoted.
- **Live-trading risk:** none during this work — System 2/3 keep consuming the existing promoted map until
  we explicitly re-promote.
- **Reversibility:** pure functions in one file + a doc; trivially revertible. No DB migration.
- **Non-goals (this proposal):** (1) Finding 3 — replacing in-sample span with true walk-forward OOS is a
  larger, separate task; here we only **rename/flag** it honestly. (2) Re-calibrating gate thresholds —
  do that **after** we can see correct numbers, not before. (3) Adding new strategies — premature until
  the existing ~20 variants can be judged fairly.

---

## 8. Open decisions for the reviewer

1. **`risk_per_trade_fraction` default** — 1% (proposed) vs 2% (matches the stated risk cap). Affects only
   MaxDD/Recovery magnitude, not ranking order much.
2. **Sharpe annualization basis** — annualize by realized trades/year (proposed, simple) vs. resampling
   R to a fixed calendar grid (more rigorous, more work). Proposal picks the former.
3. **Fix Finding 3 now or defer** — proposal defers (flag-only) to keep this change small and low-risk.
4. **Re-promotion** — after log-only review, do we auto-promote the corrected map or require a second
   human/judge sign-off? Proposal recommends explicit sign-off.

---

## 9. One-paragraph summary for a fast reviewer

The qualifier isn't too strict and the strategies aren't proven bad — the **metrics are mis-computed**.
Sharpe is annualized as if every trade were an hourly bar (~19× too high), and max-drawdown is an
unbounded R-ratio that returns impossible values like 118,280%. The fix: introduce a documented
fixed-fractional capital model so drawdown is a real bounded percentage, annualize Sharpe by actual
trade frequency, and add a guard that fails any run emitting MaxDD>100% or Sharpe>10. Run it log-only,
diff old vs new, and only then re-promote the regime→strategy map. Expected outcome: the single survivor's
Sharpe falls to ~2, impossible drawdowns disappear, and several currently-rejected strategies likely
qualify — giving a fuller, trustworthy regime map with no gate weakened and zero live-trading risk.
