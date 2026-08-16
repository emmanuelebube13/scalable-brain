# T3 — Regime-aware strategies: summary, commands, and what it changed

**Date:** 2026-08-15 · **Author:** Claude · **Reviewers:** owner + team
**Companion docs:** `DELIVERABLE.md` (full detail) · `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` (the standard this produced)

---

## The one-paragraph version

We built model 1 — the regime label as a first-class input to the strategy — as an isolated,
archivable package, and tested it on `Trend_Donchian_VCP`. The framework works and is guarded by
an equivalence test. The results do not support regime conditioning as an edge. The arm that
looked best (profit factor 0.85 → 1.24) turned out to be **pair selection wearing a regime
costume**, and once confidence intervals were added, **every attractive cell in the entire study
has a profit-factor interval that straddles 1.0**. The single statistically solid finding is a
negative one: this strategy reliably loses money in Ranging markets. The lasting value of the
work is the measurement apparatus, now written up as a standard.

---

## Commands — run any of this yourself

```bash
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
```

| what | command | time |
|---|---|---|
| The guarantees (equivalence, causality, isolation) | `python -m pytest src/regime_aware/tests/ -q` | ~1 s |
| **The experiment** — 3 arms, CIs, significance | `python -m src.regime_aware.runner --lookback-years 10` | ~1 min |
| Prove production is untouched | `python -m pytest src/system1 src/layer0 src/regime_aware -q` | ~12 s |
| The earlier MTF experiment (for comparison) | `python task/2026-August-week2/mtf-experiment/run_mtf_experiment.py --mtf` | ~2 min |
| Current production scoreboard | `python -m src.system1.vetting.vet` | ~3 s |

Reports land in `results/regime_aware/`. **Nothing writes to the database** — the connection
opens with `SET default_transaction_read_only = on`, so PostgreSQL refuses writes outright.

To see why a production cell failed:

```bash
jq -r '.rejection_detail[] | [.variant, .regime, (.failed_gates|join(" · "))] | @tsv' \
  "$(ls -t results/reports/vetting_report_*.json | head -1)" | column -t -s$'\t'
```

---

## What was built

`src/regime_aware/` — 6 modules, 17 tests, zero edits outside the folder.

| file | role |
|---|---|
| `context.py` | two context sources → a `regime` column; read-only DB connection |
| `contract.py` | `ParamBlock` / `RegimeParams` — one parameter set per regime |
| `strategies/donchian_vcp.py` | the port + three parameter sets (blind / HMM / D1-trend) |
| `runner.py` | 3-arm A/B, bootstrap CIs, permutation test, per-pair decomposition |
| `tests/` | equivalence, causality, isolation |

Production gates and the walk-forward folds are **imported** from `src/system1/`, not copied, so
the bar is identical to production's. The permutation test reuses the gatekeeper's
`oos_uplift_test` for the same reason.

**Full suite: 612 passing.** Production tables unchanged (`fact_trade_outcomes` 55,756 rows).

---

## Results

```
arm                   n     PF     PF 95% CI    Sharpe   maxDD%
blind · ALL         997   0.85   [0.72, 0.99]   -0.81     86.2
hmm_aware · ALL     211   1.24   [0.88, 1.66]    0.52     14.3
trend_aware · ALL   455   0.89   [0.69, 1.12]   -0.39     59.3

permutation test vs blind:
  hmm_aware     +0.2047 R   p=0.0428   SIGNIFICANT
  trend_aware   +0.0254 R   p=0.3879   not significant
```

### Three findings, in order of importance

**1. The HMM arm's win is a confound — and it is statistically significant anyway.**
189 of its 211 trades are USD_JPY, because the HMM labels EUR/GBP/AUD/CAD ~95% `Ranging` and the
design sits Ranging out. The control sits in the same table: `blind · USD_JPY` = PF 1.27 over 209
trades, against `hmm_aware · ALL` = PF 1.24 over 211. The regime label was acting as a proxy for
the pair name. Inside USD_JPY — the only pair where the label varies — regime awareness moved
profit factor by **0.00** (1.27 → 1.27), though max drawdown improved 21.9% → 14.5% from the
wider High-Vol stop.

This one is worth dwelling on: **p = 0.0428 on an artifact.** Significance measured that the two
trade populations differ. They do — one excludes four losing pairs. It does not measure that the
regime taught the strategy anything.

**2. With a context variable that isn't degenerate, the effect largely disappears.**
D1 trend alignment varies on every pair (~50/40/8). Applied uniformly with a-priori parameters:
overall PF 0.85 → 0.89, uplift +0.025 R, **p = 0.39**. Four of five pairs improve, AUD_USD gets
worse. USD_JPY reaches PF 1.48 — the best honest cell the system has produced — and its interval
is [0.95, 2.22].

**3. Confidence intervals invalidate every attractive cell in the study.**

| cell | PF | 95% CI | verdict |
|---|---|---|---|
| trend_aware · USD_JPY | 1.48 | [0.95, 2.22] | straddles 1.0 |
| hmm_aware · High-Vol | 1.33 | [0.86, 1.98] | straddles 1.0 |
| blind · USD_JPY | 1.27 | [0.91, 1.75] | straddles 1.0 |
| hmm_aware · EUR_USD | 1.76 | [0.00, 10.55] | n=5, meaningless |
| **blind · Ranging** | **0.76** | **[0.62, 0.91]** | **excludes 1.0 — reliably loses** |
| **blind · ALL** | **0.85** | **[0.72, 0.99]** | **excludes 1.0 — reliably loses** |

**Every cell in this study that clears statistical noise is a losing one.** Not a single
profitable cell — under any arm, any context variable, any regime — has an interval that
excludes 1.0. The study can prove this strategy loses money; it cannot prove any version of it
makes money.

### The selection discount, measured

The MTF experiment reported **PF 1.96** for this strategy. The same idea, applied uniformly with
parameters fixed in advance, yields **0.89** overall and **1.48** at best — with an interval that
includes 1.0. The 1.96 was one cell of 36, chosen after looking.

**1.96 → 0.89 is the cost of selection, measured on our own data.** When the 51 arrive and one
shows a beautiful cell, that is the discount to apply before believing it.

---

## What this changes

- **Model 1 is not rejected — it is unproven, and now testable.** The framework stands; the
  regime labels are the weak half.
- **No promotion, no production change.** Live map still `{}`, 0 qualifiers.
- **The standard is the real deliverable.** See `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`.

## Decision required

1. **Adopt the standard** and apply it to the 51 (recommended — it is cheap now, expensive later).
2. **Port the remaining strategies** into this framework — mechanical, good Gemini work.
3. **Archive:** `zip -r archieved/regime_aware_20260815.zip src/regime_aware/ results/regime_aware/`
   then sha256 and delete the tree.
