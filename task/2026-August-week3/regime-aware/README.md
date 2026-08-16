# Regime-aware trial — orientation

**Week:** 2026-August-week3 (Monday 2026-08-17)
**Engineer:** Gemini Pro · **Reviewer:** Claude · **Owner:** Emmanuel
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`

**Read `STATE.md` first, always.** It is the resume ledger. If a previous session was cut
off by a rate limit, `STATE.md` tells you exactly where to restart.

---

## 1. Why this exists

We have ~43 strategies built and measured. Almost none clear the gates on their own. The
owner's hypothesis:

> Most strategies fail because they are asked to trade in conditions they were never good
> at. Route the right *type* of strategy to the right *type* of market, and the same
> strategies produce better outcomes — fewer trades, higher probability per trade.

A trend-following strategy should trade when the market trends, and sit out when it does
not. That is the whole idea. The intervention is a **gate**, not a re-tuning.

**Goal for the first week or two is operational, not statistical.** We want to see the
system work end to end: labels resolving in real time, two arms running side by side,
outcomes landing tagged and separable, System 2/3 able to see regime per strategy per
timeframe. A week of D1/H4 bars cannot settle whether regime-gating pays, and nothing in
this folder should claim it can.

---

## 2. The decisions already made — do not relitigate them

| Decision | Value | Why |
|---|---|---|
| **Routing label** | **D1 trend** (`context.py::build_trend_labels`) | Only label that varies on every pair. Nothing fitted, so it cannot overfit. |
| HMM label | Reported alongside; usable as a gate at **D1 only** | See §3 — it is unusable as an H4 gate. |
| Blind arm | Unchanged, stays live | It is the control. Touching it destroys the comparison. |
| Mask assignment | From **declared strategy family**, pre-registered | See §4. This is the anti-overfit rule. |
| Per-regime parameter tuning | **Not in scope this week** | 4× the search space on intervals that already straddle 1.0. Gate first, tune never-until-justified. |
| Frontend/dashboard | **We do not build it** | Telemetry is System 2/3's department. We build the data and ship them a spec — see `notes-for-systems-2-3/`. |
| Promotion to live | **Not in scope** | The v2→live path does not exist. See `CONTRACT_V2_AND_POSITION_ENGINE.md` §11. |

---

## 3. The label evidence — read this before touching anything

Two things in this repo are called "the regime". They are not interchangeable. Full
explanation: **`docs/design/REGIME_LABELS_EXPLAINED.md` — read it.**

Measured from `fact_market_regime_v2.regime_causal` on 2026-08-16:

```
D1  AUD_USD  n=  4891 | Up 11.4%  Dn  5.3%  Rng 78.8%  HV  4.4%
D1  EUR_USD  n=  4911 | Up 16.7%  Dn  3.3%  Rng 79.4%  HV  0.7%
D1  GBP_USD  n=  4904 | Up 12.4%  Dn  5.5%  Rng 78.3%  HV  3.8%
D1  USD_CAD  n=  4916 | Up 15.4%  Dn  3.7%  Rng 78.0%  HV  2.8%
D1  USD_JPY  n=  4921 | Up 20.3%  Dn 23.7%  Rng  4.3%  HV 51.7%
H4  AUD_USD  n= 28185 | Up  0.0%  Dn  4.0%  Rng 90.5%  HV  5.5%
H4  EUR_USD  n= 28222 | Up  0.0%  Dn  1.7%  Rng 93.5%  HV  4.9%
H4  GBP_USD  n= 28164 | Up  0.0%  Dn  3.5%  Rng 91.1%  HV  5.4%
H4  USD_CAD  n= 28172 | Up  0.0%  Dn  1.3%  Rng 95.0%  HV  3.8%
H4  USD_JPY  n= 28187 | Up 23.9%  Dn 14.0%  Rng 10.9%  HV 51.2%
```

**Every Trending-Up H4 bar in the database belongs to USD_JPY.** The zeros are literal, not
rounding. Gating on HMM Trending-Up at H4 silently converts any strategy into a USD_JPY-only
strategy, and the resulting "improvement" is pair selection. This already happened once
(T3, p = 0.0428, entirely an artifact).

D1 trend label coverage, by contrast:

```
             Trend-Up   Trend-Dn   UNKNOWN
EUR_USD        48.4       43.8       7.8
GBP_USD        55.9       36.3       7.8
USD_JPY        58.8       33.5       7.8
AUD_USD        37.2       55.0       7.8
USD_CAD        52.6       39.6       7.8
```

**Only ever read `regime_causal`.** The sibling column `regime_smoothed` is fitted
forward *and* backward over full history and leaks the future. Feeding it to a strategy
reproduces the defect that disqualified `Range_Stochastic_Divergence` (FIX-S1-014).

---

## 4. The anti-overfit rule — this is load-bearing

**A strategy's regime mask is derived from its declared family, before anyone looks at how
it performed per regime.**

```
trend_following   → trade in Trending-Up and Trending-Down; sit out otherwise
mean_reversion    → trade when NOT trending; sit out in Trending-Up/Down
breakout          → trade in High-Vol and trending states; sit out in quiet ranges
```

The mask is **pre-registered in R2 and frozen before R3 runs.** No mask may be revised
because a result was disappointing. If you find yourself wanting to change a mask after
seeing an outcome, that is the overfit — stop and write it in the failure log instead.

Rationale: a mask chosen from declared family is a *hypothesis*. A mask chosen from observed
per-regime performance is a *fit* over four cells whose confidence intervals already straddle
1.0. The first can be tested. The second cannot.

---

## 5. Required reading, in order

| # | Document | Why |
|---|---|---|
| 1 | `docs/design/REGIME_LABELS_EXPLAINED.md` | The two labels. Confusing them has already produced a false result. |
| 2 | `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` | The eight rules. Your output is judged against them. |
| 3 | `task/2026-August-week2/deliverables/T3-regime-aware/README.md` | What the first regime-aware experiment found, and the confound it exposed. |
| 4 | `src/regime_aware/contract.py` | The `ParamBlock` contract and why indicators are computed over the continuous frame. |
| 5 | `docs/design/systems/CONTRACT_V2_AND_POSITION_ENGINE.md` §11 | Why nothing here reaches live, and the nine gaps that would have to be built first. |

---

## 6. Task map

Run in order. Each has its own file, its own definition of done, and its own failure log.

| Task | What | Est. | Blocking? |
|---|---|---|---|
| **R0** | Discrimination baseline — measure whether the 43 discriminate on either label | 1–2 h | No. A null result does **not** stop the trial (owner's explicit decision). |
| **R1** | Schema — arm-tagged, regime-tagged trade outcomes | 2–3 h | Yes, R3 needs it |
| **R2** | Strategy family taxonomy + pre-registered regime masks | 2–3 h | Yes, R2b and R3 need it |
| **R2b** | **The contract-v2 regime gate** — so the 43 new strategies can be routed at all | 3–4 h | Yes, R3 needs it. See §9. |
| **R3** | Dual-arm runner — blind and aware over the same bars, both universes | 4–6 h | Yes |
| **R4** | Publish regime per strategy per timeframe | 3–4 h | No |
| **R5** | Documentation bundle + the note to Systems 2/3 | 2–3 h | No |

---

## 7. Roles

- **Gemini Pro** does the build. On rate limit, Claude resumes from `STATE.md`.
- **Claude reviews.** Nothing is believed until reviewed. In particular Claude verifies
  every equivalence test personally — an equivalence test the engineer reports as passing,
  but which was never actually run against the blind twin, is the single failure that would
  invalidate the whole week.
- **The owner decides.** Anything ambiguous stops and asks rather than guessing.

---

## 8. Hard constraints

1. **Nothing in `src/system1/` changes.** The blind arm is the control.
2. **New code lives in `src/regime_aware/`** except the schema migration (R1), which goes
   where migrations go.
3. **Read-only on every `fact_*` table** except the new one R1 creates.
4. **No new files at the repo root.** See `STRUCTURE.md`.
5. **No promotion, no publish to the live pointer, no touching `latest.json`.**
6. Append to `STATE.md` after **every** numbered step, not at the end of the session.

---

## 9. Two strategy universes — the trial covers both, by different means

This is the thing most likely to be got wrong, so it is stated explicitly.

| | **Legacy 9** | **The 43 new strategies** |
|---|---|---|
| base class | v1 `Strategy` subclasses | `StrategyV2` |
| engine | `layer0.core_engine.BacktestEngine` | `PositionEngine` |
| exits | uniform ATR 1:3 via `engine_adapter` | each strategy's **own declared exits** |
| already regime-aware? | **yes** — `src/regime_aware/strategies/`, 9 ported | **no** — nothing supports them |
| gated how | `ParamBlock` + `resolve_at` (existing) | **R2b's intent filter** (to be built) |

`src/regime_aware/` was built on the legacy engine deliberately — its `__init__.py` explains
that a like-for-like A/B meant not changing engine and contract at once. That decision was
correct for the legacy ports and it means **the existing framework cannot execute a single
one of the 43.**

The 43 are the reason this trial exists, so R2b builds a gate at the v2 layer. Pushing them
down to the v1 engine is **not** an option: it would apply the uniform ATR harness and
discard the declared exits that contract v2 exists to preserve, which the owner has decided
to keep. It would also inherit the T6 ATR case-mismatch.

**The 43 are the primary subject.** The legacy 9 run alongside for continuity with the T3
result, and because they are already built. If time runs short, the legacy 9 are what gets
cut — not the 43.

---
