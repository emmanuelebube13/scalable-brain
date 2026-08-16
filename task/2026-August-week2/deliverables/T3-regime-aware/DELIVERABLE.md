# T3 — Regime-aware strategies (model 1): build + first result

**Built:** 2026-08-15 · **Strategy tested:** `Trend_Donchian_VCP` · **Status:** experiment complete, decision required

**Headline:** the framework works and the equivalence test passes, but for this strategy the
regime-aware arm's improvement is **a pair-selection effect, not a regime effect**. On the one
currency pair where the regime label actually varies, regime awareness changed the profit factor
by 0.00.

---

## 1. What was built

`src/regime_aware/` — a self-contained package implementing model 1: the regime label is a
first-class input to the strategy, which decides for itself how to behave under each condition.

| file | role |
|---|---|
| `context.py` | regime labels → frame column; read-only DB connection |
| `contract.py` | `ParamBlock` / `RegimeParams` — one parameter set per regime |
| `strategies/donchian_vcp.py` | the port: `Trend_Donchian_VCP` with regime as input |
| `runner.py` | A/B evaluation, production gates imported not copied |
| `tests/` | 15 tests: equivalence, causality, isolation |

**Nothing outside `src/regime_aware/` was modified.** Production tables are unchanged
(`fact_trade_outcomes` 55,756 rows, attribution 1,360 rows — same as before the build). Full
suite: **596 passing, 0 failing.**

### Isolation is enforced, not promised

The connection opens with `SET default_transaction_read_only = on`, so PostgreSQL itself refuses
a write. `test_database_itself_refuses_a_write` proves it against the live database, and a source
scan forbids write verbs anywhere in the package. All output lands in `results/regime_aware/`.

### The equivalence test is the reason to trust any of this

`RegimeAwareDonchianVCP` with identical parameters in every regime reproduces production
`Trend_Donchian_VCP` **trade for trade** — entry time, direction, entry price, stop, target, exit
reason and r-multiple all identical. Without that, an A/B built on this port would be measuring
the port rather than the regime.

### Where the per-regime parameters came from

Chosen **a priori, before any regime-aware backtest was run**, from the strategy's economics:
sit out `Ranging` (a breakout system's classic failure mode), widen the stop to 1.5×ATR in
`High-Vol` (a 1.0×ATR stop is noise-stopped there), relax ADX to 20 in the trending regimes
(redundant gating inside an already-classified trend), no trade on `UNKNOWN`. They were not
tuned and were not adjusted after seeing output.

---

## 2. The result

Both arms: 10 years, H4, 5 pairs, same engine, same folds, same production gates.

```
cell                       n     PF  Sharpe   win%  maxDD%  OOSmo
blind · ALL              997   0.85   -0.81   19.0    86.2   83.2
regime_aware · ALL       211   1.24    0.52   29.9    14.3   76.0
```

Profit factor 0.85 → 1.24, Sharpe −0.81 → 0.52, max drawdown 86% → 14%. On its face, a large win.

**It isn't. Here is the per-pair breakdown:**

```
blind · AUD_USD          201   0.76   -0.61          blind · USD_JPY    209   1.27   0.53
blind · EUR_USD          198   0.74   -0.65          regime_aware ·
blind · GBP_USD          200   0.73   -0.67            USD_JPY          189   1.27   0.55
blind · USD_CAD          189   0.74   -0.62
regime_aware · AUD_USD    10   0.88            regime_aware · EUR_USD     5   1.76
regime_aware · GBP_USD     6   0.75            regime_aware · USD_CAD     1   0.00
```

**189 of the regime-aware arm's 211 trades are USD_JPY.** The other four pairs contribute 22
trades between them.

The cause is in the regime coverage:

```
EUR_USD   Ranging 95.6%   High-Vol 3.4%   Trending-Down 1.0%
GBP_USD   Ranging 92.6%   High-Vol 4.3%   Trending-Down 3.1%
AUD_USD   Ranging 92.4%   High-Vol 4.5%   Trending-Down 3.1%
USD_CAD   Ranging 97.6%   High-Vol 1.4%   Trending-Down 1.0%
USD_JPY   High-Vol 39.5%  Trending-Up 36.7%  Trending-Down 16.2%  Ranging 7.6%
```

For four of five pairs the HMM label is ~95% `Ranging`. Disabling `Ranging` therefore disables
those pairs almost entirely. The regime label acted as **a proxy for "is this USD_JPY"**.

### The control is already in the table

`blind · USD_JPY` = PF **1.27**, Sharpe 0.53, n=209.
`regime_aware · ALL` = PF **1.24**, Sharpe 0.52, n=211.

The regime-aware arm reproduces "trade the blind strategy on USD_JPY only." You get the same
result by not trading VCP on EUR/GBP/AUD/CAD — no regime model required.

### What regime awareness actually contributed

Comparing like with like, inside the only pair where the label varies:

| | blind · USD_JPY | regime_aware · USD_JPY |
|---|---|---|
| profit factor | 1.27 | **1.27** |
| Sharpe | 0.53 | 0.55 |
| max drawdown | 21.9% | **14.5%** |
| trades | 209 | 189 |

Profit factor unchanged. Sharpe +0.02. **Max drawdown improved 7.4 points** — that is real, and
it comes from the wider High-Vol stop, exactly as the a-priori reasoning predicted. A modest risk
improvement, and nothing else.

---

## 2b. Second context source — D1 trend (added after the finding above)

The confound above is a property of the *labels*, not of model 1. So a second context provider
was added — `build_trend_labels()`, D1 EMA-50/200 alignment, shifted one bar — emitting a subset
of the same vocabulary so every strategy, block and test carries over unchanged. Its coverage is
non-degenerate on every pair, which is the whole point:

```
              Trending-Up   Trending-Down   UNKNOWN
EUR_USD           48.4%         43.8%         7.8%
GBP_USD           55.9%         36.3%         7.8%
USD_JPY           58.8%         33.5%         7.8%
AUD_USD           37.2%         55.0%         7.8%
USD_CAD           52.6%         39.6%         7.8%
```

The `ParamBlock` gained `allowed_directions`, so "in an uptrend take only longs" is expressed as
a property of the regime rather than an external filter. Blocks again chosen a priori.

### Three-arm result

```
cell                    n     PF  Sharpe   win%  maxDD%
blind · ALL           997   0.85   -0.81   19.0    86.2
hmm_aware · ALL       211   1.24    0.52   29.9    14.3     (= USD_JPY only, confounded)
trend_aware · ALL     455   0.89   -0.39   18.9    59.3
```

Per pair, blind → trend_aware:

| pair | blind PF | trend_aware PF | |
|---|---|---|---|
| USD_JPY | 1.27 | **1.48** | +0.21 |
| EUR_USD | 0.74 | 0.84 | +0.10 |
| GBP_USD | 0.73 | 0.78 | +0.05 |
| USD_CAD | 0.74 | 0.77 | +0.03 |
| AUD_USD | 0.76 | 0.59 | −0.17 |

Four of five pairs improve, and unlike the HMM arm this one **trades all five** (77–105 trades
each), so the improvement is not pair selection. USD_JPY reaches PF 1.48 / Sharpe 0.65 — the best
honest cell produced so far, and still under both gates.

### The selection-effect lesson

The MTF experiment reported PF **1.96** for this strategy in High-Vol. Applied uniformly across
all pairs, with parameters fixed in advance, the same idea yields PF **0.89** overall and 1.48 at
best. The 1.96 was one cell out of 36, chosen after looking. **That gap — 1.96 down to 0.89 — is
the cost of selection, measured directly.** Treat it as the calibration for every promising cell
found by inspection from here on.

## 3. What this settles, and what it does not

**Settles:** for `Trend_Donchian_VCP` with the current HMM labels, model 1 delivers no
regime-specific edge on entry selection. The headline improvement is pair selection.

**Does not settle:** whether model 1 works with a context variable that varies for every pair.
The D1 macro-trend filter tested earlier (`task/2026-August-week2/mtf-experiment/`) took the same
strategy from PF 1.31 to 1.96 in High-Vol, and it varies on all five pairs. That remains
untested inside this framework.

**Generalises to the other strategies.** The ~95%-Ranging coverage is a property of the labels at
H4, not of VCP. Any strategy that disables `Ranging` will collapse to USD_JPY the same way. That
is why the remaining ports have not been run — the confound would repeat, and the framework is
already built to run them in minutes once the context variable question is decided.

---

## 4. Decision required

1. **Swap the context variable** — feed D1 trend alignment through the same framework. Small
   change, `context.py` only, and the confound disappears because it varies per pair.
2. **Port the remaining strategies** on the HMM labels anyway, accepting that the result will
   most likely be "USD_JPY again" for each.
3. **Archive** — `zip -r archieved/regime_aware_20260815.zip src/regime_aware/ results/regime_aware/`,
   sha256, delete tree.

## 5. Reproduce

```bash
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
python -m pytest src/regime_aware/tests/ -q          # 15 tests
python -m src.regime_aware.runner --lookback-years 10
```

Report JSON: `results/regime_aware/donchian_vcp_ab_20260815T111706Z.json`
