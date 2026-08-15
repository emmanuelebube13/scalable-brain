# Triage — S3-001, S3-003, S3-005

Not implemented this week (per T5 step 5). Each is a half-page: what it is, why it matters,
a fix sketch, and a this-week/next-week call.

---

## S3-001 — correlation & exposure gates are blind to open positions · **P1 · NEXT WEEK, but first**

**What.** `ExecutionPipeline.open_positions` is empty in production, so the two portfolio-level
guards — correlation ≤ 0.85 and max exposure — evaluate against nothing and **can never
reject**. Two risk controls that appear in the architecture diagram do not exist at runtime.

**Why it matters now.** This is a hard prerequisite for S3-002. My corrected exposure gate
computes `sum(notional) / equity`, which is `0 / equity = 0` if the position list is empty —
i.e. applying S3-002 on top of S3-001 produces a gate that is *still* inert, just with better
arithmetic. **S3-002 cannot deliver value until S3-001 is fixed.**

Finding 3 of S3-006 sharpens this: S3 believes it holds 1 position while the broker holds 0,
so the position list is not merely empty — it is *wrong in both directions*.

**Fix sketch.** Populate `open_positions` from the broker's authoritative position list on
every decision cycle (not from local state), including `instrument`, `units`, `entry_price`.
Reconcile against `s2status.open_positions` and reject on divergence rather than proceeding
with a phantom book — default-safe posture.

**Call:** must land **before** S3-002 is switched on. Sequence it first next week.

---

## S3-003 — Kelly sizing is inert and rests on a stale, wrong-signed edge · **P1 · NEXT WEEK**

**What.** `FIXED_WIN_RATE` is a hardcoded constant, and the resulting Kelly fraction is always
larger than the hard cap, so `risk_capital = min(kelly, max_risk)` **always selects the cap**.
Every trade is sized identically. The "Quarter-Kelly, edge-aware" sizing described in the
architecture never influences a single bet.

**Why it matters.** Two compounding problems. First, the subsystem is theatre — removing it
entirely would change no output, which is worth knowing before anyone trusts it. Second, and
worse: S3-006 measures the *actual* live edge at **profit factor 0.0, expectancy −367 CAD over
10 trades, all losers**. A Kelly formula fed a positive hardcoded win rate on a strategy whose
realised edge is negative would, if it ever became active, size *up* into a losing system.

**Fix sketch.** Either (a) delete the Kelly path and document that sizing is a flat risk cap —
honest and safe; or (b) feed it a *measured, current* win rate with an explicit staleness
bound, and hard-refuse to size when the measured edge is ≤ 0. Option (a) is the right move
until there is a demonstrated live edge.

**Call:** next week. Do **not** "activate" Kelly as a fix — that is the dangerous reading.

---

## S3-005 — auditor scans from the entry bar inclusive (pre-fill leakage) · **P2 · NEXT WEEK**

**What.** `determine_outcome_m1_chunked` scans the price path from the entry bar **inclusive**,
so price action *before* the fill can decide WIN/LOSS. Plus a brittle float-equality `UPDATE`
in `main` that can silently miss rows.

**Why it matters.** `Actual_Outcome` feeds retraining and decay analysis. Mislabelled outcomes
are a *training-data* corruption — the same class of defect as the causal-label leakage
FIX-S1-005 fixed on the System-1 side. It is the quietest item here and the one most likely to
poison future models rather than lose money today.

**Fix sketch.** Scan strictly *after* the entry timestamp (exclusive lower bound). Replace the
float-equality match in the `UPDATE` with the trade's primary key. Add a regression test where
the pre-entry bar would touch the stop but the post-entry path does not.

**Call:** next week. Low urgency for capital, real urgency for data integrity — and it is
cheap. Pair it with the System-1 outcome-integrity work.

---

## Ordering recommendation

```
1. S3-006 Finding 4  — assert sizing ccy == broker account ccy   (cheap, prevents recurrence)
2. S3-004            — risk cap in account currency              (packaged, tested, ready)
3. S3-001            — populate + reconcile open_positions       (unblocks S3-002)
4. S3-002            — exposure as a fraction of equity          (packaged, tested, ready)
5. S3-006 Finding 2  — why approved orders produce zero fills
6. S3-003 / S3-005   — Kelly honesty, auditor leakage
```

**Before any of it:** S3-006's warning stands. Profit factor 0.0 over 10 trades. Fixing the
gates without answering *why every trade loses* converts a stalled system into a reliably
losing one. The unit fixes in this package make sizing **correct**; they do not make the
strategy **profitable**, and correct sizing of a negative-edge strategy loses money faster.
