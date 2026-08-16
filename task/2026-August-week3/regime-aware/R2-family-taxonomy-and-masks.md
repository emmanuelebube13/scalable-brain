# R2 — Strategy family taxonomy and pre-registered regime masks

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Estimated time:** 2–3 hours · **Risk:** low — declarative, no production impact.
**Blocks:** R3.

**Read `STATE.md` first. Read `README.md` §4 — it is the whole basis of this task.**

---

## Why this task exists

The trial routes strategies to regimes. Something has to say *which* strategy belongs in
*which* regime. This task produces that mapping, and — more importantly — produces it in a
way that cannot be quietly fitted to the answer we want.

**The rule, restated because everything here depends on it:**

> A strategy's regime mask is derived from its **declared family**, assigned **before**
> anyone looks at how that strategy performed per regime. The mask is then **frozen**.

A mask chosen from declared family is a hypothesis and can be tested. A mask chosen from
observed per-regime results is a fit over four cells whose intervals already straddle 1.0,
and it will produce a convincing number that means nothing. This project has already been
burned by exactly that (T3, p = 0.0428, pure pair selection).

---

## Hard constraints

1. **Assign families from what the strategy *is*, not from what it scored.** Read its code
   and its docstring. If R0 has already produced per-regime results, **do not open them
   while assigning.** State in `STATE.md` that you did not.
2. The mask vocabulary is the existing one — `Trending-Up`, `Trending-Down`, `Ranging`,
   `High-Vol`, `UNKNOWN`. Do not invent new label names. `src/regime_aware/context.py`
   defines `ALL_REGIMES`; import it.
3. **`UNKNOWN` always means do not trade.** Never treat it as permissive. It covers EMA
   warm-up and any bar with no label, and the honest default there is to sit out.
4. Everything lives in `src/regime_aware/`. Nothing in `src/system1/` changes.
5. Once frozen, a mask changes only by the owner's explicit decision, recorded in `STATE.md`.

---

## Execution plan

### Step 1 — Declare the family taxonomy

Three families, as agreed:

| Family | What qualifies | Favourable regimes | Sits out |
|---|---|---|---|
| `trend_following` | Follows established direction — MA crossovers, Donchian/channel breakouts in the direction of trend, pullback-continuation | `Trending-Up`, `Trending-Down` | `Ranging`, `High-Vol`, `UNKNOWN` |
| `mean_reversion` | Fades extremes — Bollinger reversion, RSI/stochastic reversal, range fades | `Ranging` | `Trending-Up`, `Trending-Down`, `High-Vol`, `UNKNOWN` |
| `breakout` | Trades expansion out of compression — volatility breakouts, box/range breaks, sweeps | `High-Vol`, `Trending-Up`, `Trending-Down` | `Ranging`, `UNKNOWN` |

If a strategy genuinely does not fit one of these three, **do not force it.** Assign
`unclassified`, give it an all-permissive mask (it trades everywhere, exactly like the blind
arm), and list it in the summary. A strategy whose family is ambiguous tests nothing, and
guessing its family to make the table tidy is the fit we are trying to avoid.

### Step 2 — Classify every discovered strategy

**Cover both universes** (`README.md` §9): all 43 `StrategyV2` strategies discovered by
`python -m src.layer0.strategies.v2_harness --list`, **and** the 9 legacy ports in
`src/regime_aware/strategies/`. The 43 are the primary subject; the legacy 9 are included so
the T3 result stays comparable. Record which universe each belongs to.

For each, record: `strategy_key`, family, universe, and **one sentence of evidence from its
code or docstring** justifying the family. The evidence sentence is not decoration — it is
what makes the assignment auditable and what stops a later reader assuming the family was
reverse-engineered from results.

Output: `src/regime_aware/families.py` (or `.json` if that suits the codebase better —
inspect and match house style). Machine-readable, since R3 consumes it.

### Step 3 — Derive the masks

Mechanically, from the family table in step 1. The mask is a `ParamBlock` per regime with
`enabled=True/False` — nothing else changes between regimes this week. **No parameter
differences, no risk differences.** Gate only.

This matters: keeping every other field identical across blocks means the aware arm differs
from the blind arm in exactly one respect, so any divergence is attributable to the gate.
It also means the equivalence test in R3 is a clean check.

### Step 4 — Freeze and pre-register

Write `results/regime_aware/R2/PREREGISTRATION.md` containing:

- the family table
- every strategy's assignment plus its evidence sentence
- the derived masks
- a UTC timestamp
- an explicit statement that no per-regime performance data was consulted

Then append the file's SHA256 to `STATE.md`. That hash is what makes "we did not change the
mask after seeing results" checkable rather than merely asserted.

### Step 5 — Tests

- Every discovered strategy has exactly one family assignment.
- Every family maps to a mask covering all five regime values including `UNKNOWN`.
- `UNKNOWN` is `enabled=False` in every mask, with no exceptions.
- `unclassified` produces an all-permissive mask (behaviourally identical to blind).
- The mask set round-trips through the `ParamBlock` contract without loss.

### Step 6 — Append to STATE.md

Counts per family, the pre-registration hash, and the explicit note that results were not
consulted.

---

## Definition of done

- [ ] All 43 (or current count) classified, each with an evidence sentence
- [ ] Machine-readable family/mask module that R3 can import
- [ ] `PREREGISTRATION.md` written, timestamped, hashed, hash recorded in `STATE.md`
- [ ] Tests above pass
- [ ] `STATE.md` states that no per-regime performance was consulted during assignment

## What the reviewer will check

- **Spot-check the family assignments against the actual strategy code.** A trend strategy
  filed as mean-reversion silently inverts its mask and would look like a failed hypothesis
  when it is really a filing error.
- That every mask has `UNKNOWN` disabled.
- That masks differ from each other **only** in `enabled`, with no parameter or risk drift
  sneaking in.
- That the pre-registration hash matches the file at review time.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
