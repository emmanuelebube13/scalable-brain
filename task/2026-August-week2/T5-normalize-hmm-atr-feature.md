# T5 — Fix the HMM's unit-scaling defect (normalized ATR), refit into an experimental table

**Engineer:** Gemini Pro
**Reviewer:** Claude (will verify the feature check independently before reading any regime output)
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`
**Estimated time:** 2–3 hours, most of it the refit. **Risk:** low if you follow the isolation rules — you never write to a production table.

---

## Required reading, in this order

1. `docs/design/REGIME_LABELS_EXPLAINED.md` — what the HMM label is, and the `regime_causal` vs `regime_smoothed` rule
2. `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` — rules 4, 5 and 8 apply directly here
3. `task/2026-August-week2/deliverables/T3-regime-aware/README.md` — the false result this defect produced

---

## The defect

The HMM consumes five features (`src/system1/regime/hmm_regime.py:47`). Four are dimensionless.
**`atr_14` is measured in raw price units**, and that breaks it:

```
symbol    avg price   avg H4 bar range   range as % of price
USD_JPY    134.15         0.4246              0.32%
GBP_USD      1.29         0.0039              0.30%
USD_CAD      1.34         0.0032              0.24%
EUR_USD      1.12         0.0029              0.26%
AUD_USD      0.69         0.0027              0.39%
```

USD_JPY's raw ATR is **~110–160× everyone else's**. But read the last column: in economic terms
USD_JPY is *mid-pack*, and AUD_USD is the most volatile pair. The 100× gap is a unit artifact.

`_fit_causal_model` then fits a **single pooled `StandardScaler`** across all instruments. After
standardising, `atr_14` becomes approximately "+large for USD_JPY, one identical negative constant
for everyone else" — i.e. a binary *is-this-JPY* flag, carried at weight 1.0.

The consequence is measurable in the label distribution: at H4, EUR_USD / GBP_USD / AUD_USD /
USD_CAD are 92–98% `Ranging` and have **exactly zero** `Trending-Up` bars across 28,000+ bars
each. Every H4 Trending-Up bar in the database belongs to USD_JPY. A regime-conditioned backtest
on those labels measures *which pair it is*, not the regime — which is precisely how the T3
experiment produced a significant (p = 0.043) result that was pure artifact.

---

## Hard constraints

- **Never write to `fact_market_regime_v2`.** All output goes to an experimental table. Verify at
  the end that the production table's row count is unchanged (847,151).
- **Never overwrite `models/hmm_model.joblib`.** Write the experimental model to a distinct path.
- **Never read or emit `regime_smoothed` for any downstream use.** It is a forward-backward fit
  over full history and leaks the future.
- **Do not touch attribution, vetting, or the orchestrator.** They read the production table; this
  task does not promote anything.
- **Do not change the gates.** `ACCURACY_GATE = 0.70`, `KAPPA_GATE = 0.40` stay as they are. If the
  refit fails them, that is the result — report it, do not adjust the bar to fit.
- **Do not tune `FEATURE_WEIGHTS` to improve the distribution.** Changing the ATR units and
  reweighting at the same time makes the outcome uninterpretable. One change at a time.
- No commits, no pushes, no `Co-Authored-By:` trailer.

---

## Step 1 — Add a new feature; do not mutate the old one

In `src/system1/features/definitions.py`, **add** `atr_pct_14` alongside `atr_14`:

```
atr_pct_14 = atr_14 / close
```

Same warm-up as `atr_14` (`ATR_PERIOD - 1` leading nulls). Register it in `FEATURE_COLUMNS`,
`WARMUP_BY_FEATURE` and `FEATURE_FORMULAE` exactly as the existing features are registered.

**Why add rather than redefine:** `atr_14` is referenced by the feature-store schema, the warm-up
map, the formula documentation and potentially downstream consumers. Silently changing what a
published feature name *means* is the kind of drift that takes a month to find. Adding a new name
and switching only the HMM's input list makes the change surgical and reversible by one line.

Then switch the regime input vector — and only that:

```python
# definitions.py
REGIME_FEATURE_COLUMNS = ["atr_pct_14", "adx_14", "volatility_20", "returns_1"]
```

And update the weights key in `hmm_regime.py` (`FEATURE_WEIGHTS`), renaming `atr_14` →
`atr_pct_14` and **keeping the weight at 1.0**.

## Step 2 — Bump the feature-set version

`hmm_regime.py:771` hardcodes `"feature_set_version": "1.0.0"`. Change it to `"1.1.0"`.

The feature store is versioned at `feature-store/{version}/`. Leaving this at 1.0.0 means the
stored Parquet features and the definition that produced them silently disagree, and the model
bundle claims a version that no longer describes it. Regenerate the feature store at the new
version if the pipeline requires it (`python -m src.system1.features.feature_pipeline --version 1.1.0`).

## Step 3 — **The feature check. Do this before you look at any regime output.**

This step separates "the fix worked" from "the fix changed the regime output". If normalized ATR
still differs by two orders of magnitude across pairs, nothing downstream is interpretable and you
have saved yourself a refit.

Compute, per pair, the mean and standard deviation of `atr_pct_14` at H4 over the same period.

**Pass condition:** all five pairs land in the same order of magnitude — no pair more than ~2×
any other. Given the table above, expect roughly 0.24%–0.39%, with **AUD_USD highest and USD_JPY
mid-pack**. If USD_JPY is still an outlier, stop and report; the patch did not do what it claims.

Report the actual numbers, not "it looks fine".

## Step 4 — Route the refit to an experimental table

Add an **opt-in** output target so the default behaviour is unchanged:

- a `--output-table` CLI argument defaulting to `fact_market_regime_v2`
- a `--model-path` CLI argument defaulting to `models/hmm_model.joblib`

For this run use:

```
--output-table fact_market_regime_v2_exp_atrpct
--model-path   models/hmm_model_exp_atrpct.joblib
```

Create the experimental table with the **same schema** as `fact_market_regime_v2`
(`CREATE TABLE ... (LIKE fact_market_regime_v2 INCLUDING ALL)`), so the comparison queries in
Step 5 are identical to the production ones.

Default-unchanged matters: a future run that forgets the flag must hit production behaviour, not
silently write to a stale experiment table.

## Step 5 — Run the walk-forward refit

```bash
python -m src.system1.regime.hmm_regime \
  --output-table fact_market_regime_v2_exp_atrpct \
  --model-path models/hmm_model_exp_atrpct.joblib
```

Multi-minute on H1. Capture the full log to `logs/hmm_refit_atrpct_<date>.log`.

**Preserve the walk-forward discipline.** The scaler must continue to be fit train-only per fold
(`_fit_causal_model`). Do not introduce any normalization that uses full-sample statistics — a
per-pair z-score over all history would reintroduce look-ahead through the back door. Dividing by
the contemporaneous close is causal; a full-sample mean is not.

---

## Step 6 — The two validation gates

### Gate A — stability

Report **accuracy and Cohen's kappa** for D1, H4 and H1. Both gates must clear:
`accuracy ≥ 0.70`, `kappa ≥ 0.40`.

**Do not assume a drop is acceptable.** Kappa is chance-corrected (`mapping.py:161`), and chance
correction interacts with class balance: a labelling dominated by one class has *high* chance
agreement, which *suppresses* kappa. The current labels are 75–95% `Ranging`. If the fix
redistributes them, chance agreement falls and kappa can just as easily **rise**. There is no
principled reason to expect a fall. Report the number against the previous 0.83+ and treat a large
move in **either** direction as something to explain, not something to wave through.

### Gate B — distribution

Run the coverage report against the experimental table, per pair, for D1 and H4:

```sql
select a.symbol, r.granularity,
  round(100.0*count(*) filter (where regime_causal='Ranging')/count(*),1)       ranging,
  round(100.0*count(*) filter (where regime_causal='Trending-Up')/count(*),1)   trend_up,
  round(100.0*count(*) filter (where regime_causal='Trending-Down')/count(*),1) trend_dn,
  round(100.0*count(*) filter (where regime_causal='High-Vol')/count(*),1)      high_vol
from fact_market_regime_v2_exp_atrpct r join dim_asset a using(asset_id)
where regime_causal is not null and r.granularity in ('D1','H4')
group by 1,2 order by 2,1;
```

**Pass condition:** EUR_USD, GBP_USD, AUD_USD and USD_CAD each register a **non-zero, non-trivial**
share of `Trending-Up` and `Trending-Down`. The exact balance is not prescribed — the fatal
symptom is a zero, or a pair still sitting above ~90% in a single state.

Print the before/after side by side, using the current production numbers as the baseline.

---

## Step 7 — Which of the four outcomes did you get?

State plainly which one. Do not blend them.

| | Gate A (kappa) | Gate B (distribution) | meaning |
|---|---|---|---|
| **1** | pass | pass | fix worked; HMM is a candidate for T4. **Stop here and report** — promotion is a separate task |
| **2** | pass | **still zeros** | unit scaling was only half the problem. Stop; the remaining cause is the label-assignment step (`mapping.py`, `LABEL_ORDER`, the tau/order rank mechanism). **Audit but do not change it** — report your reading |
| **3** | **fail** | pass | genuine tradeoff: balanced labels, less stable ones. **Not yours to resolve.** Report both numbers and stop |
| **4** | fail | fail | the change did not help. Report; the experimental table and model stay for inspection |

In outcomes 2–4 the production system is untouched and nothing needs undoing.

---

## Done when

- `atr_pct_14` exists as a new feature; `atr_14` is unchanged in meaning
- `REGIME_FEATURE_COLUMNS` and `FEATURE_WEIGHTS` reference `atr_pct_14`; weight still 1.0
- `feature_set_version` is `1.1.0`
- Step 3's per-pair feature check is reported with actual numbers
- `fact_market_regime_v2_exp_atrpct` is populated; `models/hmm_model_exp_atrpct.joblib` written
- **`fact_market_regime_v2` still has 847,151 rows and `models/hmm_model.joblib` is unmodified**
- `python -m pytest src/system1 src/layer0 src/regime_aware -q` — **612 or more passing, zero failing**
- One of the four outcomes named explicitly

## Report back with

1. Step 3's per-pair `atr_pct_14` table — the numbers, and whether USD_JPY is still an outlier
2. Accuracy and kappa per granularity, against the 0.70 / 0.40 gates and the previous 0.83+
3. The before/after coverage table, per pair, D1 and H4
4. Which of the four outcomes, stated in one sentence
5. Proof production is untouched: `fact_market_regime_v2` row count and the mtime of `models/hmm_model.joblib`
6. Test suite result
7. Anything you noticed and deliberately did not touch

**Expected outcome, stated in advance so you are not tempted to produce a better one:** the most
likely result is outcome 1 or 2. Outcome 2 — the scaling fix landing correctly but the zeros
persisting — would be a genuinely useful finding, because it narrows the remaining cause to the
label-assignment step by elimination. A clean, well-evidenced negative is worth more here than a
positive that does not survive review.
