# src/layer0/ — legacy name, still load-bearing

Do not let the name mislead you. Layers 1, 2, 4, 5, 6, 7 were retired and archived; **this
one runs.** It holds `indicators.py`, `core_engine/backtest_engine.py`, `position_engine.py`,
and `strategies/` — the ~47-strategy research sandbox plus `v2_harness.py`.

Review strategy logic with `forex-strategist`; review anything touching time with
`leakage-hunter`.

## Look-ahead is this folder's recurring defect

Two live incidents originated here:

- `detect_swing_points` used `center=True` and contaminated the only live strategy at the
  time. **36 of 51** CSV fleet strategies were affected.
- `Range_Stochastic_Divergence` (strategy 10) uses `rolling(center=True)`, showed PF 1.92
  across four live cells, and emits **zero** signals causally. It is `INTEGRITY_DISQUALIFIED`
  and cannot be rehabilitated by reparameterisation.

Before adding or editing any strategy, grep your own diff for `center=True`, `.shift(-`,
`bfill`, and full-series `.max()` / `.min()` / `.idxmax()`. The decisive test is: **does it
produce the same trades when run causally?** If it produces none, you have found another one.

## Conventions that have silently broken behaviour

- **Column case.** `engine_adapter` writes `df["atr"]`; `StrategyBase` reads `df["ATR"]`.
  Check what is actually populated at run time rather than what the code appears to write.
- **ATR-based stops are warmup-dependent.** A stop computed on an unwarmed ATR is a different
  strategy, not a rounding difference.
- **Exits must exist.** Strategies have been published with empty exits. Every entry needs a
  defined exit, including the timeout case.

## Parameters

Every parameter traces to reasoning fixed **before** the run and committed alongside the
value. An untraceable parameter is indistinguishable from a fitted one. Adjusting parameters
after seeing output creates a **new variant** — name it and re-test it; do not edit the
original. See `docs/design/STRATEGY_EXPERIMENT_STANDARD.md`, rule 2.

## Tests

`src/layer0/strategies/research/tests/` has **2 pre-existing collection errors** (fixtures
importing strategy modules that do not exist) which abort the whole run — hence the standard
`--ignore`. `test_wave1_guards.py` pins SHA256s of files that have since changed
legitimately. Distinguish your reds from these.
