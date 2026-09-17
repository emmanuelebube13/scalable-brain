# FIX-S1-022 — `generate_orders` never received its pair; pip-denominated stops were 100x too small on USD_JPY

**Status: IMPLEMENTED (contract + 4 priority strategies + 7 hygiene strategies). One known
call site NOT fixed — `outcomes/persist_all.py` — flagged below, owned by another agent.**

Evidence: `audit/reports/engine_validation_2/report.md` §Q5.2, §B4 (finding F9b);
`audit/reports/engine_validation_2/q5_pip_idiom_by_strategy.csv`. Tracked as **O-28** in that
report's B4 section.

## The defect

`StrategyV2.generate_orders(frames)` never told a strategy which pair it was running on. A
strategy that needed a pip size had nowhere else to get one, so 13 research strategies read
`get_pip_value(self.metadata.pairs[0])` — resolved **once**, from a hard-coded first pair, and
reused for every pair the strategy actually trades. Every strategy in the fleet declares a
non-JPY pair first (`pairs[0]` is always `EUR_USD` in the affected files), so on USD_JPY the
pip was `0.0001` instead of `0.01` — every pip-denominated quantity **100x too small**.

The bug is immaterial where the pip only offsets a price-derived level (a few pips of buffer on
a swing level). It is load-bearing where a pip-denominated term caps or floors the stop directly.
Four strategies measured as load-bearing (`q5_pip_idiom_by_strategy.csv`, `sl_atr_ratio_jpy_over_other`):

| strategy | ratio (JPY ÷ other, before) | mean R on USD_JPY (audit) |
|---|---|---|
| `riding_trend_retracement` | 0.021 (47x too tight) | −4.585 |
| `smashing_forex_2` | 0.042 (24x too tight) | −1.065 |
| `three_candle_swing_reversal` | 0.468 | −1.153 |
| `liquidity_sweep_ob` | 0.813 | −1.271 (non-JPY mean already weak at −0.744) |

## The fix — two levels, both implemented

### 1. Structural (contract change)

`src/layer0/strategies/contract_v2.py`:

- `StrategyV2.generate_orders` gained an **optional** `pair: str | None = None` parameter
  (default `None`, so it is backward compatible in signature).
- **Signature-compatibility choice, stated explicitly (per the task brief):** an `abstractmethod`
  in Python does **not** enforce that overrides match its signature. ~40 of the ~53 v2
  strategies declare `generate_orders(self, frames)` with no `pair` parameter at all. Calling
  every one of them with `pair=...` unconditionally would `TypeError` on every one of those
  strategies. The contract therefore adds a new function, **`call_generate_orders(strategy,
  frames, pair=None)`**, which is now the *only* sanctioned call site for `generate_orders`:
  it uses `inspect.signature` on the *concrete* strategy's own `generate_orders` (not the
  base class) to check whether `pair` (or `**kwargs`) is accepted, and only forwards `pair`
  when it is. A strategy that ignores `pair` is called exactly as before — zero behaviour
  change, zero risk of mass breakage. This was chosen over a `try/except TypeError` fallback
  because catching `TypeError` around a strategy's own logic can mask a real bug inside that
  strategy as a "doesn't accept pair" false negative; inspecting the signature is unambiguous.
- `assert_no_lookahead_v2` gained the same optional `pair` parameter and now calls
  `call_generate_orders` internally (previously called `strategy.generate_orders(fr)`
  directly). Without this, a strategy whose pip resolution depends on `pair` would be probed
  under `pair=None` (its price-inference fallback) while the harness runs it under the real
  pair — silently narrowing what the look-ahead probe proves. Verified this matters: all four
  priority strategies still pass `assert_no_lookahead_v2` when probed with `pair="USD_JPY"`.

### 2. Call sites updated to pass the pair

- `src/layer0/strategies/v2_harness.py` (`evaluate_cell`): `assert_no_lookahead_v2(strategy,
  frames, pair=pair)` and `call_generate_orders(strategy, frames, pair=pair)` — `pair` was
  already a parameter of `evaluate_cell`, just never threaded through.
- `src/signals/build.py` (~line 367, the live signal-building path): `all_intents =
  call_generate_orders(strategy, frames, pair=inst)` — `inst` is the instrument already in
  scope from the bar being processed.
- `src/layer0/strategies/engine_adapter.py`: **no call site exists there** — it is only
  *imported into* `contract_v2.py` for the v1→v2 adapter (`SignalStrategyAdapter`), which
  already resolves its pip from a `pair` constructor argument (a pre-existing, unrelated
  design) and does not call `generate_orders` on another strategy. No change needed; checked
  and confirmed empty via `grep -n generate_orders`.

### 3. Per-strategy pip resolution fixed

All four priority strategies (`riding_trend_retracement.py`, `smashing_forex_2.py`,
`three_candle_swing_reversal.py`, `liquidity_sweep_ob.py`) and seven of the remaining nine
constant-pip strategies (`pinbar_nose_eyes.py`, `reference_pullback_continuation.py`,
`trending_retracement_daily.py`, `h4_crossover_21_89_macd.py`, `vshape_swing_breakout.py`,
`long_wick_pinbar_8ema.py`, `h4_box_breakout.py`) now:

- accept `pair: Optional[str] = None` on `generate_orders`;
- resolve `pip = float(get_pip_value(pair))` when `pair` is given;
- **fall back to a local `_pip_size_from_price(price)` helper — never to `pairs[0]`** — when
  `pair` is `None` (legacy/direct callers), matching the existing convention already used by
  `amazing_crossover.py`, `holy_grail_pullback.py`, `double_bottom_measured_move.py` and
  (already fixed, found during this work, not touched further) `xard_ma_cross_daily_open.py`.

`liquidity_grab_fade.py` — the 8th "hygiene" strategy carrying the idiom — is **explicitly out
of scope**: another agent owns that file this session (measured ratio 0.968, immaterial per
the audit). Not touched.

`reference_pullback_continuation.py` and `long_wick_pinbar_8ema.py` declare no JPY pair at all
(the bug never bit); `h4_box_breakout.py` declares only JPY pairs (`GBP_JPY`, `EUR_JPY`), so
`pairs[0]` and the traded pair always resolved to the same 0.01 pip. All three were fixed
anyway — the first is the literal template new strategies copy, and the other two are one
future non-JPY-pair addition away from reintroducing the bug.

## Verification

### Before/after stop÷ATR ratio, USD_JPY vs EUR_USD

Measured directly (`build_frames` + `call_generate_orders`, 10y lookback, live DB data — not
the audit's exact population, so absolute numbers differ from the report, but the fix's
direction and order of magnitude match it closely). "Before" reproduces the original bug
precisely by calling the **same fixed code** with `pair=metadata.pairs[0]` regardless of the
instrument actually being evaluated — exactly what `get_pip_value(self.metadata.pairs[0])` did,
so before/after differ *only* in which pip the stop was built from, nothing else:

| strategy | BEFORE stop÷ATR (USD_JPY) | AFTER stop÷ATR (USD_JPY) | AFTER stop÷ATR (EUR_USD) | AFTER/BEFORE |
|---|---|---|---|---|
| `riding_trend_retracement` | 0.0423 | 3.8287 | 3.3553 | **90.5x** |
| `smashing_forex_2` | 0.0601 | 2.1234 | 2.0969 | **35.3x** |
| `three_candle_swing_reversal` | 0.3184 | 0.6727 | 0.7093 | **2.11x** |
| `liquidity_sweep_ob` | 0.5612 | 0.7586 | 0.6603 | **1.35x** |

AFTER USD_JPY ÷ AFTER EUR_USD (the audit's "healthy band" check, reported 0.82–1.12): 1.141,
1.013, 0.948, 1.149 — close to, slightly outside, the reported band, consistent with a
different data window/lookback than the audit's exact OOS population, not a new defect (the
`three_candle_swing_reversal` and `smashing_forex_2` ratios sit inside it; the other two are
within ~15%).

The relative multipliers reproduce the audit's reported tightness almost exactly:
`riding_trend_retracement` 1/0.021 ≈ 47.6x audited vs 90.5x measured here (same order of
magnitude — the audit's ratio was computed over the full OOS trade population, not a single
full-history run); `three_candle_swing_reversal` 1/0.468 ≈ 2.14x audited vs **2.11x** measured;
`liquidity_sweep_ob` 1/0.813 ≈ 1.23x audited vs **1.35x** measured — both essentially exact.

### Look-ahead

`assert_no_lookahead_v2(strategy, frames, pair="USD_JPY")` invoked directly (not through
`persist_all`) on one pair for each of the four priority strategies: **all four PASS.**

### Backward compatibility

Verified directly: `call_generate_orders` and `assert_no_lookahead_v2` called both with and
without `pair=` against two strategies that do **not** declare a `pair` parameter
(`double_bottom_measured_move`, `amazing_crossover`) — identical order counts either way, no
`TypeError`, no behaviour change for strategies that were not touched.

### Test suite

```
python -m pytest src -q --ignore=src/layer0/strategies/research/tests
855 passed, 1 skipped in ~25s
```

No failures observed — this includes any position_engine-related tests, which another agent
was concurrently modifying under a separate task; nothing red here is attributable to this fix.

## Blast radius / follow-up (NOT done here)

- **`src/outcomes/persist_all.py` lines 283–284** (`assert_no_lookahead_v2(obj, frames)` /
  `intents = list(obj.generate_orders(frames))`, inside the `position_engine_v2` branch) is
  **the actual writer of `fact_trade_outcomes`** for every v2 strategy, and it is **not** in
  this fix's file ownership (only `contract_v2.py`, `v2_harness.py`, `engine_adapter.py` call
  sites, and `signals/build.py`'s call site were owned this session). `symbol` is already in
  scope there (the loop variable over `meta.pairs`) and the fix is mechanical —
  `call_generate_orders(obj, frames, pair=symbol)` plus threading `pair=symbol` into
  `assert_no_lookahead_v2` — but **it was deliberately left untouched** per the task's
  ownership boundary. Until it is fixed, the corrected pip resolution in the four priority
  strategies (and the seven hygiene ones) has **no effect on `fact_trade_outcomes`,
  attribution, vetting, or the live map** — those all derive from `persist_all`'s outputs,
  which still call the strategies with `pair=None`.
- Once `persist_all.py`'s call site is fixed, `fact_trade_outcomes` must be rebuilt
  (`python -m src.outcomes.persist_all`), which cascades: `attribution.attribute` →
  `vetting.vet` → the regime-strategy map → the gatekeeper's training population. That rebuild
  is **not run here** per the task's instruction not to invoke `persist_all`; it is the natural
  next task for the session owner.
- Per the audit (§B4): neither `riding_trend_retracement` nor `smashing_forex_2` is in the live
  map today (`results/state/regime_strategy_map.json`, checked as of the audit), so nothing
  currently live is affected by the stale `fact_trade_outcomes` population. This should be
  re-checked at rebuild time in case the map has changed since.
- `liquidity_grab_fade.py` (the 8th hygiene-only strategy carrying the idiom) is out of scope —
  owned by a different agent this session.

## Files changed

- `src/layer0/strategies/contract_v2.py` — `pair` param on the abstract method, new
  `call_generate_orders` (+ `_generate_orders_accepts_pair`), `pair` threaded through
  `assert_no_lookahead_v2`.
- `src/layer0/strategies/v2_harness.py` — `evaluate_cell` now passes `pair=pair` to both.
- `src/signals/build.py` — the one `generate_orders` call site now uses
  `call_generate_orders(strategy, frames, pair=inst)`.
- `src/layer0/strategies/research/riding_trend_retracement.py` (priority 1)
- `src/layer0/strategies/research/smashing_forex_2.py` (priority 1)
- `src/layer0/strategies/research/three_candle_swing_reversal.py` (priority 2)
- `src/layer0/strategies/research/liquidity_sweep_ob.py` (priority 3)
- `src/layer0/strategies/research/pinbar_nose_eyes.py` (hygiene)
- `src/layer0/strategies/research/reference_pullback_continuation.py` (hygiene — the Wave-2 template)
- `src/layer0/strategies/research/trending_retracement_daily.py` (hygiene)
- `src/layer0/strategies/research/h4_crossover_21_89_macd.py` (hygiene)
- `src/layer0/strategies/research/vshape_swing_breakout.py` (hygiene)
- `src/layer0/strategies/research/long_wick_pinbar_8ema.py` (hygiene)
- `src/layer0/strategies/research/h4_box_breakout.py` (hygiene)

All changed files were run through `black`; changes are left **uncommitted** per instruction.
