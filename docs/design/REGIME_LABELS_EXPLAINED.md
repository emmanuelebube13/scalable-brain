# The two regime labels: what they are and where they come from

**Read this before working on anything regime-related.** Two different things in this repo are
both called "the regime". They are not interchangeable, and confusing them has already produced
one false result.

| | HMM label | D1 trend |
|---|---|---|
| what it is | 4 states inferred by a fitted model | 2 states from a fixed rule |
| states | Trending-Up, Trending-Down, Ranging, High-Vol | Trending-Up, Trending-Down (+ UNKNOWN) |
| fitted to history? | **yes** | **no** |
| varies on all pairs? | **no** — near-constant on 4 of 5 | yes |
| where the values live | `fact_market_regime_v2.regime_causal` | computed on the fly from D1 prices |
| code | `src/regime/hmm_regime.py` | `src/regime_aware/context.py::build_trend_labels` |

---

## 1. The HMM label

**What it is.** A 4-state Gaussian Hidden Markov Model is fitted to engineered features of the
price series (returns, volatility, trend measures — see `src/features/definitions.py`).
The model assigns each bar to one of four hidden states, which are then given the human names
*Trending-Up, Trending-Down, Ranging, High-Vol* by `regime/mapping.py`. If the fit fails a
≥0.70 accuracy gate, the code falls back to K-Means.

**It is a learned, unsupervised label.** Nobody defined "Ranging" — the model found four clusters
in feature space and the clusters were named afterwards. That naming step is where the
2026-08-14 relabelling bug lived (labels had been assigned by rank order rather than by trend).

**Causal vs smoothed — this distinction matters more than anything else here.** The table holds
two columns:

- **`regime_causal`** — refitted walk-forward, forward-only. The label on bar *t* uses only bars
  up to *t*. **This is the only column any strategy or backtest may read.**
- `regime_smoothed` — a forward-backward fit over the full history. The label on bar *t* is
  partly computed from bars *after* *t*. It is for reporting/charts only. Feeding it to a
  strategy manufactures look-ahead — the same defect that disqualified
  `Range_Stochastic_Divergence` (see `FIX-S1-014`).

**Its critical weakness.** The label barely varies for most of the book:

```
H4          Ranging  Trend-Up  Trend-Dn  High-Vol
EUR_USD       95.6      0.0       1.0        3.4
GBP_USD       92.6      0.0       3.1        4.3
AUD_USD       92.4      0.0       3.1        4.5
USD_CAD       97.6      0.0       1.0        1.4
USD_JPY        7.6     36.7      16.2       39.5
```

Those zeros are literal — four pairs have **exactly zero** Trending-Up bars across 28,000+ H4
bars each. Every Trending-Up H4 bar in the database belongs to USD_JPY.

Consequence: conditioning a strategy on the HMM label silently becomes conditioning on *which
pair it is*. That is exactly what happened in the T3 experiment — an apparent improvement, and
even a significant p-value, that was entirely pair selection.

**Where to look:**
- values — `fact_market_regime_v2` (columns `regime_causal`, `regime_smoothed`, `granularity`)
- code — `src/regime/hmm_regime.py`, `src/regime/mapping.py`
- model artifact — `models/hmm_model.joblib`
- coverage query — `task/2026-August-week2/deliverables/T3-regime-aware/README.md`

---

## 2. The D1 trend label

**What it is.** A deterministic rule on daily closes:

```
EMA(50) > EMA(200)  →  Trending-Up
EMA(50) < EMA(200)  →  Trending-Down
first 200 bars      →  UNKNOWN (EMA warm-up, no opinion)
```

then shifted one bar forward, then joined backward onto the intraday frame. So an H4 bar carries
a daily verdict computed from days strictly before the current daily bar.

**Nothing is fitted.** There is no model, no training, no retraining, no scaler, no version to
publish. Two EMAs and a comparison. That is its main advantage: there is no way for it to
overfit, and nothing to ship to System 2 beyond four lines of code.

**Its coverage is healthy on every pair:**

```
             Trend-Up   Trend-Dn   UNKNOWN
EUR_USD        48.4       43.8       7.8
GBP_USD        55.9       36.3       7.8
USD_JPY        58.8       33.5       7.8
AUD_USD        37.2       55.0       7.8
USD_CAD        52.6       39.6       7.8
```

Because it varies everywhere, a result conditioned on it can actually be interpreted.

**It emits a subset of the HMM vocabulary on purpose.** `Trending-Up`, `Trending-Down` and
`UNKNOWN` are all valid HMM labels too, so both sources drop into the same `RegimeParams`
contract with no code changes. Under the D1-trend context, the `Ranging` and `High-Vol` blocks
simply never fire.

**Where to look:**
- code — `src/regime_aware/context.py::build_trend_labels`
- earlier standalone version — `task/2026-August-week2/mtf-experiment/run_mtf_experiment.py`

---

## 3. Which to use

Neither has demonstrated an edge. Against baseline, the D1-trend arm produced +0.025 R,
**p = 0.39** — not significant. The HMM arm produced p = 0.043, but that was the pair-selection
artifact described above.

For **testing**, use D1 trend: it is the only one of the two whose result can be interpreted on
more than one pair. Report both when the framework offers both.

For **production**, neither is promotable today.

Full evidence: `task/2026-August-week2/deliverables/T3-regime-aware/README.md`.
Rules for evaluating any of this: `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`.
