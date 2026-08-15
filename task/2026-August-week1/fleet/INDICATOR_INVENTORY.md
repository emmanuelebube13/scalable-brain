# Indicator inventory — `src/layer0/data_access/indicators.py`

Prefer these over writing your own. They are already used by the live path, so a strategy
built on them is comparable to everything else in the system.

## Available and safe (causal)

| Function | Signature | Returns |
|---|---|---|
| `ema` | `(series, period)` | Series |
| `sma` | `(series, period)` | Series |
| `atr` | `(high, low, close, period=14)` | Series |
| `adx` | `(high, low, close, period=14)` | Series |
| `bollinger_bands` | `(close, period=20, std_dev=2.0)` | (upper, mid, lower) |
| `rsi` | `(close, period=14)` | Series |
| `stochastic` | `(high, low, close, ...)` | (%K, %D) |
| `donchian_channel` | `(high, low, period=20)` | (upper, mid, lower) |
| `macd` | `(close, fast=12, slow=26, signal=9)` | (macd, signal, hist) |
| `zscore` | `(series, period=20)` | Series — **rolling**, not whole-frame |
| `vwap` | `(high, low, close, volume)` | Series |
| `williams_r` | `(high, low, close, period=14)` | Series |
| `cci` | `(high, low, close, period=20)` | Series |
| `keltner_channel` | `(high, low, close, ...)` | (upper, mid, lower) |
| `chandelier_exit` | `(high, low, close, ...)` | Series |
| `supertrend` | `(high, low, close, ...)` | Series |
| `volatility_contraction_index` | `(high, low, close, ...)` | Series |
| `volume_profile_levels` | `(high, low, close, ...)` | levels |
| `calculate_pips` | `(price_change, asset="EUR_USD")` | float |
| `get_pip_value` | `(asset="EUR_USD")` | float |

## 🚨 BANNED

### `detect_swing_points(high, low, period=5)`

**Do not import this function.** `indicators.py:463-469`:

```python
swing_highs = (high == high.rolling(window=period*2+1, center=True).max()) & ...
```

`center=True` means the window at bar *t* spans `[t-period … t+period]` — it reads
`period` bars into the future. This is not a theoretical concern: it is the mechanism that
contaminated `Range_Stochastic_Divergence`, the only strategy in production. Computed
honestly, every one of that strategy's signals becomes zero
(`task/2026-August-week1/lookahead-audit/FINDINGS.md`, 2026-08-02).

**36 of the 51 source strategies reference swing highs, ZigZag, pivots, or fractals.** Assume
yours is one of them until you have checked.

**Use instead:** `causal_structure.confirmed_swing_points`, `zigzag_swings`,
`last_n_confirmed_highs` (built in Wave 1).

The semantic difference, which your spec must respect:

> A swing high **occurs** at bar *k* but is only **knowable** at bar *k + period*.
> You may act on it from *k + period* onward, using the level recorded at *k*.
> Knowing at bar *k* that bar *k* was a swing high is look-ahead.

That is also what a real trader experiences — they cannot know a high was *the* high until
price has failed to exceed it for several bars. The causal version is not a handicap; it is
the truth.

## If you need something not listed

State it precisely in your spec (Wave 0) or your report (Wave 2): the formula, the window,
and why an existing indicator will not do. **Do not add it to `indicators.py`** — that file
is shared with the live path and is off-limits. Define it privately in your own module.

## Cost model — for reference, do not reimplement

Spread **1.0 pip**, slippage **0.5 pip on entry only**, commission **0**. These match the
live model that produced the 134,520 `fact_trade_outcomes` rows. The position engine applies
them; strategies must not.
