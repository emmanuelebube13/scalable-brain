# Engine Validation, pass 2 — deliverables

Spec: `docs/proposed-fixes/system-1/EngineValidation2.md`.
Start with **`report.md`**; everything here is its evidence.

## How to regenerate

All four scripts are read-only — no production table, artifact or config is written.

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

python src/audit/engine_validation2_replay.py --lookback-years 10   # ~9 min  -> replay_trades.parquet
python src/audit/engine_validation2_v2_levels.py                    # ~3 min  -> v2_declared_levels.parquet
python src/audit/engine_validation2_analysis.py                     # ~1 min  -> Q1-Q7, Q10
python src/audit/engine_validation2_q4_v2.py                        # ~1 min  -> corrected Q4 for v2
python src/audit/engine_validation2_b3_fill.py                      # ~2 min  -> B3
python src/audit/engine_validation2_tests.py --which t1             # ~11 min -> Q8 inputs
python src/audit/engine_validation2_tests.py --which t2 --reps 200  # ~90 min -> Q9 input
python src/audit/engine_validation2_q8q9.py                         # ~1 min  -> Q8, Q9
```

`--lookback-years 10` matches what `src/outcomes/persist_all.py` actually used; a different
value shifts the walk-forward fold boundaries and the replay stops matching the DB.

## The two intermediate datasets

| file | why it exists |
|---|---|
| `replay_trades.parquet` | `fact_trade_outcomes` stores **no prices** (`atr_sl_multiplier`/`atr_tp_multiplier` are 100% NULL), so stop distance, slippage and intrabar levels cannot be measured from the DB. This re-runs both engines through the exact `persist_all` dispatch and keeps the price columns it discards. |
| `v2_declared_levels.parquet` | The v2 engine's **own** resolved exit levels, captured by subclassing `PositionEngine._open_position`. Needed because `exit_price` is a fraction-weighted average across all exit fills, so reconstructing a take-profit level from it is wrong for multi-leg trades. |

## Files by question

| question | files |
|---|---|
| Q0 replay fidelity | `q0_replay_fidelity.csv` |
| Q1 common-mode vs localised `[GATE]` | `q1_strategy_distribution.csv`, `q1_distribution_summary.csv` |
| Q2 measured cost floor `[GATE]` | `q2_measured_cost_floor.csv`, `q2_cost_floor_by_engine_granularity.csv`, `q2_corrected_e0.csv` |
| Q3 engine separation `[GATE]` | `q3_engine_split.csv`, `q3_same_strategy_both_engines.csv`, `q3_stop_regime_by_engine.csv` |
| Q4 intrabar ambiguity | `q4_zero_bar_by_exit_reason.csv`, `q4_ambiguity_count*.csv`, `q4_counterfactual_R*.csv`, `q4_m15_resolution*.csv` |
| Q5 USD_JPY H4 | `q5_usdjpy_h4_by_strategy.csv`, `q5_stop_geometry_h4.csv`, `q5_pip_idiom_by_strategy.csv`, `q5_usdjpy_h4_by_year.csv` |
| Q6 direction asymmetry | `q6_drift_vs_asymmetry.csv`, `q6_drift_correlation.csv`, `q6_direction_crosstab.csv`, `q6_slippage_symmetry.csv` |
| Q7 time localisation | `q7_mean_R_by_year.csv` |
| Q8 inversion | `q8_inversion_v2.csv`, `q8_inversion_summary.csv`, `q8_matched_pair_sums.csv`, `q8_matched_pair_summary.csv`, `q8_mirror_failures.csv` |
| Q9 random-entry floor | `q9_floor_distribution_v2.csv`, `q9_floor_summary.csv`, `q9_cells_vs_measured_floor.csv`, `q9_generator_validity.md`, `q9_generator_validity.csv`, `t2_geometry.json` |
| Q10 corrected diagnostics | `d2_per_instrument_R.csv`, `d5_direction_split.csv` |
| B3 fill timing | `b3_fill_timing_by_granularity.csv`, `b3_fill_timing_by_strategy.csv` |
| — | `replay_failures.csv` — the 15 strategy/symbol combinations the replay could not produce |

## Two things to know before reading a CSV

**`status` column on the Q4 files.** The v2 rows of `q4_ambiguity_count.csv`,
`q4_counterfactual_R.csv` and `q4_m15_resolution.csv` are tagged **`SUPERSEDED`**. They
reconstructed the v2 take-profit from a winner-conditional R:R proxy, which is wrong for
fractional-leg trades. The authoritative v2 numbers are in the `*_v2_measured.csv` files,
built from the engine's own resolved levels. The v1 rows in those files are
`AUTHORITATIVE` — v1 records `take_profit_price` on every trade, so no proxy is involved.

**Sign convention (spec Rule 7).** `C_g` is a positive magnitude, `expected_floor = −C_g`,
and `gap = mean_R − expected_floor = mean_R + C_g`. A negative gap is worse than the floor.
This is asserted in code (`engine_validation2_analysis.py:_assert_rule7`) for every table
that carries a gap. The pass-1 `d2`/`d5` files stored `expected_floor` as positive and are
replaced here.

## Populations — three of them, deliberately

| population | n | used for |
|---|---|---|
| DB OOS (`fact_trade_outcomes WHERE is_oos`) | 65,251 | every bank-level mean R; what vetting actually reads |
| Replay, OOS subset | 52,697 | price-derived measurement (stop geometry, slippage, ambiguity) |
| Replay, all trades | 75,251 | mechanical measurements where OOS is irrelevant and power helps |

The DB/replay gap is **entirely** the three `Range_Bollinger_*` strategies that no longer
instantiate — the already-registered O-3/O-4 orphaned rows. See `report.md` §Q0 and §N1.
Any table mixing populations says which it used.
