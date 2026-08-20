# FIX-S1-013 — `persistence_smooth` trailing-edge look-ahead

**Found:** 2026-08-12
**Severity:** moderate — leaks up to 2 bars of future information (2 days on D1, 2 hours on H1) into the causal regime label, which leaks into strategy attribution.
**Status:** IMPLEMENTED and ENABLED. Shipped disabled on 2026-08-12 pending a re-fit
decision; the owner took that decision on **2026-08-14** and `CAUSAL_SMOOTHING` is now
`True` in `hmm_regime.py`, with `fact_market_regime_v2` re-derived by the re-fit run of
the same day. Rollback is the flag plus a re-run.

---

## 1. The finding

`src/regime/mapping.py::persistence_smooth` claims in its docstring:
> The smoothed label at bar t depends only on bars 0..t (never future).

**This is false.** It decides a segment's fate from the segment's *total* length, which requires scanning forward past `t`.

Demonstrated:

```python
persistence_smooth(["A","A","A","B","B"], 3)        == ["A","A","A","A","A"]     # B-run of 2 -> absorbed
persistence_smooth(["A","A","A","B","B","B"], 3)    == ["A","A","A","B","B","B"] # B-run of 3 -> survives
persistence_smooth(["A","A","A","B","B","C"], 3)    == ["A","A","A","A","A","A"] # still 2 -> absorbed
```

Bars 3–4 are `A` or `B` depending entirely on what bar 5 turns out to be.

---

## 2. Consequences

This is called at `src/regime/hmm_regime.py`, under the comment "Causal persistence smoothing", i.e., in the **causal** walk-forward label path. That label is what `src/attribution/attribute.py` joins trades to at entry. 

So the causal label — created by FIX-S1-005 specifically to eliminate look-ahead — leaks up to `min_bars - 1` bars into the past. 

**Severity in real terms:** The smoothing window is 3 bars (`min_bars=3`). The leak is exactly `min_bars - 1 = 2` bars. This is 2 hours on H1, but it is **2 days on D1**, which is highly material when evaluating long-term strategies.

---

## 3. The Fix

1. **A new function `persistence_smooth_causal`** was added alongside the existing one, leaving `persistence_smooth` unchanged to not break other dependents.
2. **Prefix Invariance:** The new function guarantees `f(labels[:k])[0] == f(labels)[0][:k]`. A bar carries the *last confirmed* label until the new run reaches `min_bars`. It yields a `settled` mask to explicitly mark provisional bars.
3. **Trailing edge effects:** The final `min_bars - 1` bars of any series are naturally unsettled. This is unavoidable in a causal system.
4. **Behind a flag:** The fix is wired into `hmm_regime.py` behind a `CAUSAL_SMOOTHING` flag,
   which shipped `False` so a fresh checkout behaved exactly as before. **Set to `True` on
   2026-08-14** — enabling it changes the labels, which is why it required a re-fit and a
   deliberate owner decision rather than a default flip.

When enabled, the run summary dict reports `n_unsettled`, so the size of the trailing-edge effect is transparent.
