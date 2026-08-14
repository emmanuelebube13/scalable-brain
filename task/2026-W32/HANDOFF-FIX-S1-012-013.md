# HANDOFF — finish FIX-S1-012 and implement FIX-S1-013

**For:** an external LLM session with repo access.
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Date written:** 2026-08-12
**Baseline you are starting from:** `pytest src/system1` = **263 passed**. If that number is
lower before you touch anything, stop and report — something is already broken.

This file is self-contained. Do not assume any prior conversation.

---

## Environment

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

Python 3.12. Run pytest from the repo root. PostgreSQL is on `localhost:5432`, database
`ForexBrainDB` — **you will not touch it** (see constraints).

---

## HARD CONSTRAINTS — violating any of these fails the task

1. **NO DATABASE WRITES.** No `INSERT` / `UPDATE` / `DELETE` / `CREATE TABLE`. Do not run
   `python -m src.system1.regime.hmm_regime` — that rewrites `fact_market_regime_v2`.
2. **NO RE-FIT.** Do not modify or regenerate `models/hmm_model.joblib`. Read it only.
3. **DO NOT change the four label strings** `Trending-Up`, `Trending-Down`, `Ranging`,
   `High-Vol`, or `SEMANTIC_ORDER`. Downstream code (`src/system1/vetting/vet.py`,
   `src/system1/gatekeeper/train.py`, `src/system1/queue_producer/producer.py`) matches on
   them exactly.
4. **DO NOT change any default behaviour.** Task 2 must be OFF by default. A fresh checkout
   must behave exactly as it does today unless a caller opts in.
5. **`pytest src/system1` must end green**, at 263 tests or more.
6. **Do not touch** anything under `src/layer0/strategies/` — separate workstream, in flight.
7. If something in these instructions turns out to be wrong, **stop and report it**. Do not
   improvise a redesign.

---

## Background you need (read these two files first)

- `docs/proposed-fixes/system-1/FIX-S1-012-regime-labels-are-rank-artifacts.md` — the finding
- `docs/proposed-fixes/system-1/FIX-S1-012-tau-sensitivity.txt` — the measurement

Summary in three sentences: regime state→label mapping used to assign `Trending-Down` by
*rank* (`min()` over three states), so 75% of D1/H4 bars were labelled "Trending-Down" while
actually trending mildly **up**. That is now fixed — labels are assigned by *threshold* on the
value (`tau`). But a second problem was then exposed: because `High-Vol` is assigned **first**,
the genuine downtrend states are always claimed by `High-Vol`, so `Trending-Down` is now never
used at any `tau > 0`. That is Task 2.

---

## TASK 1 — FIX-S1-013: `persistence_smooth` trailing-edge look-ahead

### The defect

`src/system1/regime/mapping.py::persistence_smooth` claims in its docstring:

> The smoothed label at bar t depends only on bars 0..t (never future).

**This is false.** It decides a segment's fate from the segment's *total* length, which requires
scanning forward past `t`. Demonstrated:

```python
persistence_smooth(["A","A","A","B","B"], 3)        == ["A","A","A","A","A"]    # B-run of 2 -> absorbed
persistence_smooth(["A","A","A","B","B","B"], 3)    == ["A","A","A","B","B","B"] # B-run of 3 -> survives
persistence_smooth(["A","A","A","B","B","C"], 3)    == ["A","A","A","A","A","A"] # still 2 -> absorbed
```

Bars 3–4 are `A` or `B` depending entirely on what bar 5 turns out to be.

**Why it matters:** it is called at `src/system1/regime/hmm_regime.py:525`, under the comment
"Causal persistence smoothing", i.e. in the **causal** walk-forward label path. That label is
what `src/system1/attribution/attribute.py` joins trades to at entry. So the causal label —
created by FIX-S1-005 specifically to eliminate look-ahead — leaks up to `min_bars - 1` bars.

A test already pins the current (leaking) behaviour:
`src/system1/regime/tests/test_mapping.py::test_persistence_smooth_trailing_run_looks_ahead`.

### What to build

Add a **new** function alongside the existing one. Do not change `persistence_smooth`'s
behaviour — other callers and tests depend on it.

```python
def persistence_smooth_causal(
    labels: List[str], min_bars: int = 3
) -> Tuple[List[str], List[bool]]:
    """Debounce that is causal at every bar, including the trailing edge.

    Returns (smoothed, settled). ``settled[t]`` is False where the label at t is
    still provisional — i.e. the current run is shorter than ``min_bars`` and could
    still be absorbed by what happens next.
    """
```

Required semantics — a test must assert each:

- **Prefix invariance.** For every `k`, `persistence_smooth_causal(labels[:k])[0]` must equal
  `persistence_smooth_causal(labels)[0][:k]`. This is the property the existing function fails.
  Test it over at least 200 random label sequences.
- A run only becomes confirmed once it has actually reached `min_bars` observed bars.
- Until confirmed, a bar carries the **last confirmed** label, and `settled[t] is False`.
- The final `min_bars - 1` bars of any series will typically be unsettled. That is correct and
  unavoidable, not a bug to engineer around.
- Leading edge: before any run has reached `min_bars`, carry the raw label and mark unsettled.

### Wire it in — carefully

At `hmm_regime.py:525` the causal path calls `M.persistence_smooth(seq, min_bars=3)`.

- Add a module-level constant `CAUSAL_SMOOTHING = False` in `hmm_regime.py`.
- When `True`, the causal path uses `persistence_smooth_causal` and records the `settled` flags.
- When `False` (the default, and what must ship), behaviour is byte-identical to today.
- Add `n_unsettled` to the per-granularity run summary dict when the causal path runs, so the
  size of the trailing-edge effect is visible in the logs.

**Do not** change the reporting-label path — only the causal one.

### Write the fix document

Create `docs/proposed-fixes/system-1/FIX-S1-013-persistence-smooth-trailing-lookahead.md`,
following the structure and tone of the FIX-S1-012 document. It must contain: the finding with
the three-line reproduction above; why it matters (causal label → attribution join); the
severity in real terms (`min_bars - 1` = 2 bars, i.e. 2 hours on H1, 2 days on D1 — state this
explicitly, D1 is the material one); the fix; and the fact that it ships **disabled** pending a
re-fit decision by the repo owner.

---

## TASK 2 — trend-first ordering, behind a flag, DEFAULT OFF

### Why

`map_states_to_labels` assigns `High-Vol` first (highest `volatility_20 + atr_14`), then
thresholds the remainder on trend. Volatility spikes during selloffs, so the genuine downtrend
state is always eaten by `High-Vol` — and `Trending-Down` ends up unused at every `tau > 0`.

The sensitivity report measured the alternative. Trend-first, from
`FIX-S1-012-tau-sensitivity.txt` Section 2:

| gran | tau | Trend-Up | Trend-Down | Ranging | High-Vol |
|---|---|---|---|---|---|
| D1 | 0.25 | 9.6% | **6.4%** | 75.1% | 8.9% |
| H4 | 0.25 | 8.6% | **7.5%** | 74.6% | 9.2% |
| H1 | 0.10 | 15.0% | **7.5%** | 43.4% | 34.0% |

All four labels used; the real downtrends land in `Trending-Down`.

### What to build

Add a keyword argument to `map_states_to_labels`:

```python
def map_states_to_labels(
    means, feature_names, direction_feature="returns_1",
    tau: float = 0.25,
    order: Literal["volatility_first", "trend_first"] = "volatility_first",
) -> Dict[int, str]:
```

`trend_first` rule, exactly as the sensitivity script models it in Section 2:

1. Any state with mean direction `> +tau` → `Trending-Up`; `< -tau` → `Trending-Down`.
2. Among the states left in the neutral band, the one with the highest `volatility_20 + atr_14`
   → `High-Vol`.
3. Everything else → `Ranging`.
4. The mapping may be non-bijective and labels may be unused — that is already supported.

`volatility_first` must remain the default and must be byte-identical to current behaviour.

Also add per-granularity tau support in `hmm_regime.py`:

```python
TAU_BY_GRANULARITY = {"D1": 0.25, "H4": 0.25, "H1": 0.10}
```

Used only when a caller opts into `trend_first`. Default path unchanged.

### Verify against the report

Add a test that reproduces the nine numbers in the table above from the state means recorded in
`FIX-S1-012-...md` §1, under `order="trend_first"` at the stated tau. If your implementation
disagrees with the published sensitivity report, **the report is the reference — stop and
report the discrepancy** rather than adjusting either side to match.

---

## TASK 3 — finish the FIX-S1-012 record

Append a `## 7. Implementation record` section to
`docs/proposed-fixes/system-1/FIX-S1-012-regime-labels-are-rank-artifacts.md` covering:

- every change with `file:line`
- which call sites assumed a bijective mapping, and how each was fixed
- the kappa gate: constant value, where it is enforced, what the summary dict now reports
- your reading of the sensitivity report: which `tau` and which ordering you would recommend,
  **including** the honest observation if some granularity ends up with only two live labels
- what remains undone and why

---

## Definition of done

```bash
pytest src/system1 -q            # >= 263 passed, 0 failed
black --check src/system1/regime
mypy src/system1/regime          # no NEW errors vs before your change
git status --porcelain           # no changes outside the files listed below
```

Files you may create or modify — **nothing else**:

```
src/system1/regime/mapping.py
src/system1/regime/hmm_regime.py
src/system1/regime/tests/*.py
docs/proposed-fixes/system-1/FIX-S1-012-regime-labels-are-rank-artifacts.md
docs/proposed-fixes/system-1/FIX-S1-013-persistence-smooth-trailing-lookahead.md
```

Confirm explicitly in your final report:

- [ ] `fact_market_regime_v2` untouched — no DB writes made
- [ ] `models/hmm_model.joblib` unmodified (compare its sha256 before and after)
- [ ] default behaviour unchanged — both new paths ship OFF
- [ ] test count before and after

Report concisely: files changed, test counts, and anything you could not do or disagreed with.
