# FIX-S1-014 — the live champion cannot fire; integrity disqualification for vetting

**Raised:** 2026-08-14 · **Severity:** critical — the entire live model is one strategy that
emits no signals in real time.
**Decision taken:** pull it from the live map now; repair it causally as a separate research
candidate (owner's call, 2026-08-14).

---

## 1. The finding

`Range_Stochastic_Divergence` (strategy_id 10) is **the whole live model**:

| Regime | Variant | Rank |
|---|---|---|
| Trending-Up | `Range_Stochastic_Divergence@H1` | 1 |
| Trending-Down | `Range_Stochastic_Divergence@H1` | 1 |
| Ranging | `Range_Stochastic_Divergence@H1` | 1 |
| Ranging | `Range_Stochastic_Divergence@H4` | 2 |

Its divergence detection (`range_stochastic.py:245,248,281,284`) locates swing points with
`rolling(window=10, center=True)`. A centred 10-bar window at bar *t* spans `[t-4 … t+5]` — the
entry condition depends on five bars that have not happened yet.

The 2026-08-02 audit (`task/2026-W32/lookahead-audit/FINDINGS.md`) probed all ten qualified
strategies on 20,000 bars across two instruments: **nine clean, strategy 10 differs on 20/20
firing bars.** Computed honestly, every one of its signals becomes 0.

**So the live map routes 100% of capital to a strategy that, in real time, never trades.**
That is consistent with the money-layer result: 10 realised trades, all losers.

---

## 2. Why re-running vetting does not fix it

The obvious remedy — regenerate the map — **does not work**, and this is the important part.

`vet.py` reads `fact_strategy_regime_attribution`, which is derived from `fact_trade_outcomes`,
which were produced by backtesting the **look-ahead version**. Those rows still show
PF 1.92 / Sharpe 1.07 / WinRate 0.65. A fresh vetting run would re-qualify strategy 10 on the
strength of numbers that were never real.

Any fix therefore has to be **explicit and survive a re-run**. Deleting entries from
`regime_strategy_map.json` by hand would be silently undone by the next `vet --live`.

---

## 3. The fix — integrity disqualification

A new, separate rejection category in `vetting/vet.py`, checked **before** the performance gates:

```python
INTEGRITY_DISQUALIFIED: Dict[int, str] = {
    10: "look-ahead: centred rolling window in divergence detection; "
        "emits zero signals when computed causally (FIX-S1-014, audit 2026-08-02)",
}
```

Design notes, each deliberate:

- **It lives in `vet.py`, not `gates.py`.** `gates.py` encodes *performance* thresholds. This is
  an *integrity* judgement — a different kind of statement, and conflating them would imply the
  strategy could pass by improving its metrics. It cannot; its metrics are fiction.
- **Checked first, unconditionally.** No metric can override it.
- **It carries its reason as data**, so the rejection report explains itself without a human
  needing to find this document.
- **Counted separately** as `integrity_fail`, never folded into `pf_fail` or similar — a
  disqualification is not a near miss.

### Consequence: the live map becomes empty

Strategy 10 is the only qualified strategy, so removing it leaves **zero qualified cells**.

This is correct and is the point. An empty map is the honest representation of the current
state: nothing has proved an edge under honest measurement. It is milestone **M1 — honest zero**
in `docs/goals/VALUE_MILESTONES.md`. The number does not improve; it becomes true.

Downstream this is safe:

- `_update_registry` resets `is_qualified = false` for all rows before re-marking, so the
  disqualification propagates to `dim_strategy_registry` rather than leaving a stale `true`.
- The `non_empty_map` deployment gate will fail, so the orchestrator cannot promote a bundle
  built on nothing. That is the gate doing its job.
- The retrain cron is already held at Computer 2's request, so nothing auto-publishes.

---

## 4. Not in scope — the repair

The strategy is **not** being abandoned. Its divergence logic has never been evaluated honestly:
the audit shows the *current implementation* reads the future, not that the *idea* is worthless.

`causal_structure.confirmed_swing_points` now exists (built for FIX-S1-012's sibling work) and a
causal reimplementation is straightforward — divergences would still be detected, confirmed
`period` bars later. That is a separate piece of work, and the rebuilt strategy re-enters as an
ordinary contract-v2 research candidate with no special standing. It must clear the gates on its
own merits like the other 51.

Note the likely outcome honestly: a confirmation lag of several bars on a mean-reversion entry
may remove the edge entirely. That is a legitimate finding, not a failure.

---

## 5. Verification

- A test asserts strategy 10 is rejected by `build()` **with metrics that would otherwise pass**
  — i.e. the disqualification beats the gates rather than coinciding with them.
- A test asserts `integrity_fail` is counted separately and the reason string reaches the report.
- A test asserts an empty qualified set produces a valid, empty map rather than raising.
- `pytest src/system1` green.

## 6. Rollback

Remove the entry from `INTEGRITY_DISQUALIFIED` and re-run `vet --live`. The blocklist is the
only change; no data was deleted, and `fact_trade_outcomes` is untouched.
