# FINDINGS-D7 — 0.06:1 R:R signal reached the wire

**Investigator:** Bob (agent)  
**Date:** 2026-09-03  
**Signal:** `b97120fc-25d4-57ad-8f6e-8775c250f2a6`, EUR_USD H4 short, strategy 30 `liquidity_grab_fade`  
**Evidence base:** `results/signals/2026-09-01.ndjson` row 3 (0-indexed), code reads of `src/layer0/strategies/research/liquidity_grab_fade.py` and `src/layer0/strategies/causal_structure.py`.

---

## 1. The facts from the ledger

Read `results/signals/2026-09-01.ndjson` line 3 on 2026-09-03:

| Field | Value |
|---|---|
| `signal_id` | `b97120fc-25d4-57ad-8f6e-8775c250f2a6` |
| `signal_time_utc` | `2026-09-01T13:00:00+00:00` |
| `pair` | `EUR_USD` |
| `granularity` | `H4` |
| `direction` | `short` |
| `strategy_key` | `liquidity_grab_fade` |
| `strategy_id` | `30` |
| `proposed_entry` | 1.15856 |
| `proposed_sl` | 1.16286 |
| `proposed_tp` | 1.158295 |
| `selection_basis` | `qualified` |
| `model_score` | 0.7412610054016113 |
| `threshold_calibrated` | 0.60 |
| `shadow_verdict` | `would_pass` |
| `regime` | `Trending-Down` |

Computed:
- Risk: `1.16286 − 1.15856 = 0.00430` = 43.0 pips
- Reward: `1.15856 − 1.158295 = 0.000265` = 2.65 pips
- R:R: 2.65/43.0 = **0.06:1**

This signal is **the only gate-qualified signal of the week** (`selection_basis: qualified`, `shadow_verdict: would_pass`, score 0.741 vs threshold 0.60). Every other signal that week has R:R ≈ 2:1.

---

## 2. Root cause: two independent findings

### Finding 2a — The take-profit logic has no minimum-distance floor

**Code:** `liquidity_grab_fade.py:221-224` (short path):
```python
valid_lows = [l for l in confirmed_lows_list if l < close_arr[i]]
tp_level = max(valid_lows) if valid_lows else np.nan
```

The take-profit is the **nearest confirmed swing low below the current close**: `max(valid_lows)`. In a trending-down market that has recently formed a new swing low, this can resolve to a level just 2–3 pips below the entry close. The formula is structurally correct for a liquidity-grab-fade — you are fading back to the last structural reference. But when the nearest structural reference is nearly at-the-money, the resulting trade has negative expected value even at a high win rate (0.06:1 requires > 94% win rate to break even net of spread).

There is no minimum R:R check, no minimum pip-distance check, and no guard that prevents this from being emitted. Every other strategy in the live map uses a hardcoded `RR_RATIO = 2.0` (e.g., `xard_ma_cross_daily_open.py:30`) — `liquidity_grab_fade` uses a market-derived target with no floor.

**Cause: strategy defect (missing minimum R:R floor).** The pattern likely fired correctly; the target was wrong because the nearest confirmed low happened to be nearly at-the-money at the signal bar.

**Forex-strategist agent assessment (2026-09-03):** Verdict "definitively broken risk-reward, but the pattern may be genuine." The agent confirmed: the 43-pip stop is at the outer edge of plausible (consistent with a large liquidity grab into an HTF resistance cluster), the pattern recognition (model score 0.741) appears to be working, and the root cause is "valid setup, no tradeable range" due to the nearest confirmed low being freshly formed just below entry. A human discretionary trader would skip this trade.

### Finding 2b — `confirmed_lows_list` is polluted with bar `i`'s own swing point at signal time

**Code:** `liquidity_grab_fade.py:104-108`:
```python
for i in range(self.warmup_bars, len(h4)):
    if not np.isnan(sh_vals[i]):
        confirmed_highs_list.append(sh_vals[i])   # ← appended BEFORE order logic
    if not np.isnan(sl_vals[i]):
        confirmed_lows_list.append(sl_vals[i])    # ← appended BEFORE order logic
```

At iteration `i`, the swing confirmed at bar `i` is appended to the list BEFORE the TP selection logic runs at that same bar. A confirmed swing high/low at bar `i` is available at the moment of bar `i`'s close (the swing confirmation is the close of bar `i`), but in a live system the signal is generated at bar `i`'s close — the entry and the swing confirmation arrive at the same instant. Feeding bar `i`'s own swing into bar `i`'s target selection is a concurrent-confirmation issue: the confirmed low at the signal bar itself could be the "valid low" that resolves the target.

**Leakage-hunter agent assessment (2026-09-03):** Verdict **SUSPECTED_LEAKAGE / confirmed structural concern**. The fix is to move the append to the end of the loop body, so bar `i`'s swing is only available for bar `i+1`'s order generation. The `causal_structure.py` functions themselves are clean (truncation-invariant, confirmed-swing output stamped at confirmation bar); the issue is in how `liquidity_grab_fade` consumes them.

**Impact on this specific signal:** If bar `i = 13:00Z` had a confirmed swing low at 1.158295 (which is `proposed_tp`), that swing was appended to `confirmed_lows_list` before the TP lookup ran, and the TP resolved to that level. Without the concurrent-bar swing, `valid_lows` might have included only older lows farther below, giving a better R:R or no signal at all. The near-at-the-money target is consistent with this bug: a fresh confirmed swing low at bar `i` is by construction nearly at the entry close.

---

## 3. Effect on live output

Strategy 30 (`liquidity_grab_fade`, `qualified` at H4 Trending-Down) is currently **the only gate-qualified strategy emitting**. Fixing or disqualifying it takes the live output from **1 qualified + 8 designated → 0 qualified**. This is an owner-visible trading-activity change, not a silent fix.

FIX-S1-013 precedent: a strategy whose attribution rows come from a look-ahead backtest looks healthy for exactly the wrong reason. `confirmed_lows_list` being polluted with bar `i`'s own swing point would produce a subtly improved backtest (targets resolve to nearer-at-the-money levels that get touched quickly, artificially inflating win rate) — making the strategy look more qualified than it is. Whether that is the cause of its qualification status requires a re-run of the attribution pipeline with the corrected logic; that was **not done in this investigation**.

---

## 4. What is not known

- Whether the `confirmed_lows_list` leakage actually changed the result for this specific bar (2026-09-01T13:00:00Z): it would require re-running `generate_orders` with the fix applied and checking if `valid_lows` produces a different (lower) target or no signal at all. **Not run.**
- Whether strategy 30's qualification metrics are inflated by the leakage in backtesting. The strategy appears in the live map with `selection_basis: qualified`; re-running attribution with the fixed loop is required to verify. **Not run.**
- The specific market structure at 2026-09-01T13:00:00Z (EUR_USD H4): which confirmed swing lows were available at that bar, and whether the leakage fix would change the signal. **Not checked against live DB.**

---

## 5. Adversarial pass — agents invoked, 2026-09-03

**`forex-strategist` (2026-09-03):**
- Pattern validity: likely genuine (model score 0.741 supports this)
- R:R viability: 0.06:1 is not tradeable under any position-sizing model
- Stop geometry: 43 pips is conditionally plausible for an HTF-resistance liquidity grab; not definitively wrong
- Root cause: "nearest confirmed low was freshly formed, collapsing the reward"
- Human action: **skip — valid pattern, no tradeable range**
- Recommended systemic fix: minimum R:R floor before signal emission

**`leakage-hunter` (2026-09-03):**
- `confirmed_swing_points()` in `causal_structure.py`: **CLEAN** (truncation-invariant, confirms at `k+period`)
- `last_n_confirmed_highs/lows`: **CLEAN** (forward pass + ffill, no future bars)
- `confirmed_highs/lows_list` appended before order logic: **LEAKAGE** — bar `i`'s own swing confirmation enters the TP pool at bar `i` before the order is generated
- Episode tracking (`episode_b`, `ob_high/low`, `grab_j0`): **CLEAN** (all from `j < i`)
- `csh_arr[i-1]` / `csl_arr[i-1]` for BOS detection: **CLEAN** (one-bar lag, conservative)

---

## 6. Owner decisions required before any fix (Q2)

**Q2 (from STATE.md):** Should System 1 refuse to emit a bad-R:R signal, or compute and publish R:R and let System 3 decide? A refusal is a new enforcing live gate.

**Constraint:** "Do not add an enforcing gate as a bug fix" (PROMPT §D7, O-16). The FIX-S1-018 shadow-mode decision exists precisely to prevent that.

**Implication of the leakage finding (2b):** The leakage bug is independent of the R:R guard question. Fixing the loop-append order is a correctness fix to the strategy's own logic, not a gate. However, fixing it may change the strategy's behavior (different targets or no signal) and must be declared as a change to live output — given that strategy 30 is currently the only qualified emitter.

**Two questions for the owner, in order:**
1. (Q2) R:R guard: publish R:R in the ledger and let System 3 decide, or add an enforcing gate?
2. (Independent) Correct the `confirmed_lows_list` loop order in strategy 30, knowing it may change live output and may reveal that the qualification metrics are inflated by the leakage?

Both require owner sign-off before implementation.
