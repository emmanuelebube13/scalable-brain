# FIX-S1-021 — engine_adapter ATR column casing: every v1-engine stop was warmup-dependent

**Status:** FIXED 2026-09-16 · **Severity:** medium (v1 evidence path only; deterministic but
history-length-dependent stops) · **Register:** task/OPEN.md O-12 · **Author:** Claude (Fable 5),
owner-authorized

---

## Summary

`src/layer0/strategies/engine_adapter.py` (`ContractStrategyAdapter.calculate_indicators`)
wrote the precomputed ATR to `df["atr"]` (lower case), but every reader in the incumbent
engine tests for `df["ATR"]` (upper case): `StrategyBase.calculate_stop_loss` (line 321),
`calculate_take_profit` (line 349), `check_volatility_filter` (line 375), and
`multi_timeframe.generate_mtf_signals` (`row["ATR"]`, lines 352–359). The lookup missed on
every call, so the stop/TP methods fell into their fallback branch and **recomputed ATR from
the data prefix passed in at each entry** — a 100-bar window (`backtest_engine.py:240`).
`indicators.atr` uses `ewm(adjust=False)`, which is recursive and seed-dependent, so every
v1-engine stop and take-profit depended on how much history happened to precede the entry:
badly seeded on early trades, converging thereafter. A stop computed on an unwarmed ATR is a
different strategy, not a rounding difference (`src/layer0/CLAUDE.md`).

The defect was **documented and tolerated** by
`src/layer0/strategies/tests/test_position_engine.py::test_v1_equivalence`, which named it
verbatim and accepted a bounded decaying residual (`max |dr| <= 1e-4`) between the T6 path
and the v2 `PositionEngine` path instead of exact agreement.

## Writer/reader survey (why upper-case won)

- Writers of a lower-case `atr` column: **engine_adapter.py:58 only**. No code anywhere in
  `src/layer0/`, `src/outcomes/` or `src/vetting/` reads `df["atr"]`. (The `required_indicators`
  properties returning `["atr"]` are declarative name lists for audit, never matched against
  columns; `layer2_config_adapter.py`'s `'atr'` is a T-SQL literal.)
- Writers of `ATR`: every direct v1 strategy that precomputes it (`range_bollinger`,
  `trend_donchian`, `trend_ema_adx`, `vcp_breakout`, `range_stochastic`, `support_resistance`)
  plus the `StrategyBase` fallback branches themselves.
- Readers of `ATR`: `strategy_base.py` 321/324/326, 349/352/354, 375/379;
  `multi_timeframe.py` 352–359 (fed by the same `strategy.calculate_indicators` output, so it
  is fixed by the same change).
- `src/signals/build.py` and gatekeeper code have their own ATR handling — untouched.

One writer to change versus ~15 read sites: the adapter moves to `"ATR"`.

## Fix (landed 2026-09-16, working tree)

- `src/layer0/strategies/engine_adapter.py` — `calculate_indicators` writes `df["ATR"]`;
  comment pins the casing contract. **Also sets `volatility_filter=False` explicitly**: the
  config default is True but the filter was structurally inert under the old casing
  (`check_volatility_filter` no-ops when `"ATR"` is absent). Fixing the casing without pinning
  the flag would have silently activated a 90th-percentile ATR entry filter and changed every
  research strategy's trade set — a semantics change far beyond this defect.
- `src/layer0/strategies/tests/test_position_engine.py` — `test_v1_equivalence` now asserts
  the T6 and v2 r-multiples agree **exactly** (`max |dr| == 0.0`); the recompute path is dead,
  both paths read the same full-frame ATR. Narrative comment rewritten (past tense, cites this
  FIX).
- `src/layer0/strategies/tests/test_wave1_guards.py` — `READONLY_SHA256` re-pinned for
  `engine_adapter.py` (`8c65fc44…` → `52cd5a03…`), with the justification comment the guard
  demands.

## Verification

- `test_v1_equivalence` passes with the zero-residual assertion, and the fixture still
  exercises all five exit paths (stop, TP, time-stop, signal-reverse, end-of-data) with
  `volatility_filter=False` — trade sets are structurally unchanged by the fix.
- Direct check: a v1 backtest through `BacktestEngine` + `ContractStrategyAdapter` produced
  20 trades whose stop and TP are **bit-identical** to
  `entry ± multiple × atr(full_frame).loc[entry_time]` — stops now come from the precomputed
  column, not a per-entry recompute.
- `python -m pytest src/layer0 -q --ignore=src/layer0/strategies/research/tests`: 166 passed.
- Full suite `python -m pytest src -q --ignore=src/layer0/strategies/research/tests`:
  842 passed, 1 skipped, 9 failed — all 9 in `src/signals/tests`, caused by a pre-existing
  uncommitted edit to `src/signals/run.py` (references `setup_dedup` without importing it;
  zero references at HEAD). Unrelated to this fix.
- `black` clean on all three changed files.

## Blast radius and follow-up

- **v1 `BacktestEngine` evidence path only**: adapter backtests →
  `src/outcomes/persist_all.py` → `fact_trade_outcomes` → attribution → vetting. The live
  signal path does not touch `StrategyBase`.
- **`fact_trade_outcomes` still holds warmup-dependent stops.** Rows persisted before this
  fix were built with per-entry recomputed ATR; the next `persist_all` rebuild (nightly /
  pipeline phase — deliberately NOT run as part of this fix) re-derives them under the
  corrected stops. Attribution and vetting verdicts should be re-read after that rebuild.
- Residual hazard (accepted): the `StrategyBase` fallback recompute branches remain for
  direct v1 strategies. Any future strategy whose `calculate_indicators` fails to write
  `"ATR"` re-enters the warmup-dependent path silently. The wave1 hash pin plus the exact
  equivalence test now guard the adapter path; the fallback itself was left as-is to keep
  this change minimal.
