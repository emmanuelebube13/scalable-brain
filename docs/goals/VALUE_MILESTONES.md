# Value milestones — what makes Scalable Brain worth something

**Written:** 2026-08-13 · **Purpose:** a target to steer by, and an honest baseline to steer from.

This is not a business plan. It is a ladder of falsifiable milestones, each tied to a blocker
that actually exists in this repo today. Its job is to keep effort pointed at the one thing
that creates value, and to make it obvious when we are working on something that does not.

---

## The thesis, in one line

> **The code is not the asset. A verified out-of-sample track record is the asset.**

Buyers in this industry — prop desks, funds, family offices — underwrite an equity curve first
and inspect the infrastructure second. Excellent engineering with no track record is a cost
centre. A mediocre codebase with two honest years of positive expectancy is a business.

Everything below is ordered by that logic.

---

## Milestone 0 — where we actually are (2026-08-13)

| Fact | Source |
|---|---|
| 10 realised trades, **all losers** | S3-006 audit, 2026-07-22 |
| Expectancy −367 CAD/trade; lifetime −15,935 CAD | same |
| Live map = **one strategy**, `Range_Stochastic_Divergence@H1` | `results/state/regime_strategy_map.json` |
| That strategy **emits zero signals** when computed honestly | `task/2026-August-week1/lookahead-audit/FINDINGS.md` |
| Regime labels were rank artifacts | FIX-S1-012 |
| Causal regime label leaks 2 bars | FIX-S1-013 |
| Retrain/promotion pipeline deliberately held | crontab, at Computer 2's request |

**Honest valuation: ~$0 as a trading business.** As a codebase, replacement cost is perhaps
6–18 months of a strong quant engineer — but replacement cost is not market price when there is
no revenue and the buyer pool is thin.

The sizing gate being jammed shut is currently the main thing preventing further loss. That is
the clearest possible statement of where we stand: the safety machinery is protecting the
account, not the edge.

---

## The ladder

### M1 — Honest zero
**Nothing in the live map that cannot fire in real time.**

- Remove or quarantine `Range_Stochastic_Divergence` from the regime→strategy map
- Re-fit regimes with corrected labelling (FIX-S1-012) and causal smoothing (FIX-S1-013)
- Re-run the discrimination test — finding B was measured against broken labels and may reverse

**Value delta: none.** The number stays ~$0. But it becomes *true*, and every measurement taken
after this point is trustworthy. Nothing above this rung is real until this one is done.

**Falsifier:** if the map still routes to a strategy whose honest signal count is zero, M1 is not
met, regardless of what else has been built.

---

### M2 — First honest qualifier
**At least one strategy clears the full gates, leak-free, on out-of-sample folds.**

- Gates unchanged: PF ≥ 1.5, Sharpe ≥ 0.8, MaxDD ≤ 25%, WinRate ≥ 40%, Recovery ≥ 3.0, OOS ≥ 60mo
- Must pass `assert_no_lookahead_v2`
- Must be reported **per (pair × granularity)**, not only pooled — a strategy that qualifies
  pooled while failing 9 of 13 cells is concentration risk, not an edge
- The 51-strategy CSV build is the supply line for this

**Value delta: small but real.** Moves the story from "infrastructure" to "infrastructure plus a
candidate". Still not sellable.

**Falsifier / honest possibility:** all 51 fail. That is a genuine outcome, not a project
failure — the T6 pilot came back PF 0.94, Sharpe −0.66, and the gates exist precisely to say no.
If 0 of 51 qualify, the correct conclusion is that this strategy family has no edge after costs,
and the next move is a different family, not looser gates.

---

### M3 — Forward test
**6 months of out-of-sample forward results with positive expectancy.**

- Paper or small live — size is irrelevant, honesty is not
- Decided in advance and not revised mid-flight: instrument set, position count, stop discipline
- Results recorded from the live signal path, not a re-backtest
- No parameter changes during the window. Any change restarts the clock

**This is the first milestone with genuine financial meaning.** It is the first evidence that
survives the question "how do I know this isn't curve-fit?"

**Falsifier:** live expectancy materially below backtest. Expect *some* decay — if live is
wildly better, suspect a measurement error, not a windfall.

---

### M4 — Verified curve
**12+ months of continuous, auditable, positive-expectancy results.**

- Broker statements reconcilable to the system's own trade log
- Drawdowns inside the modelled envelope
- At least one adverse regime survived (a real drawdown, not a quiet stretch)

**This is the sellable asset.** At this point the engineering quality — the leak-free discipline,
the checksummed publishing, the adversarial tests, the fix register — stops being overhead and
becomes the thing that makes the curve *credible*. Good infrastructure does not create value
here; it makes value defensible.

---

## What this ladder is for

Use it to answer one question when deciding what to work on:

> **Which rung does this move us up?**

Work that moves no rung is not necessarily wrong — the ingest repair, the cron diagnosis and the
regime work were all prerequisites for trustworthy measurement. But it should be recognised as
plumbing, and plumbing should be finished, not polished.

The recurring failure mode in this project has been building supply lines while the factory is
dark. The 51-strategy build is genuinely the right investment for M2 — and it produces nothing
until M1 is done, because a map keyed on a strategy that cannot fire will not be improved by
adding 51 more.

---

## Standing honesty rules

These exist because the incentive to fudge grows as the ladder gets higher.

1. **Never loosen a gate to pass a strategy.** If nothing qualifies, that is the finding.
2. **Never re-backtest to explain a live result.** The live path is the record.
3. **A rejection with per-gate numbers is a successful run**, not a wasted one.
4. **Look-ahead is the house risk.** This repo has now found it three separate times
   (FIX-S1-005, FIX-S1-013, the `detect_swing_points` audit). Assume it is present until a
   truncation probe says otherwise.
5. **Do not count M4 before M1.** The valuation conversation is only meaningful from the rung
   we are actually standing on.
