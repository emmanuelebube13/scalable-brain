# WAVE 0 — Strategy specification extraction (paste this whole file as the prompt)

**Fleet size:** 51 agents, one per strategy. Fully parallel — no agent depends on another.
**Depends on:** nothing. Run this concurrently with Wave 1.
**Output:** one `SPEC-<strategy_id>.md` per agent, plus `DATA-GAP-<strategy_id>.md` where
applicable.

---

## Uploaded files

- `forex_swing_strategies.csv` — 51 rows, the source material
- `CONTRACT_V2_AND_POSITION_ENGINE.md` — the interface your spec must be expressible in
- `DATA_AVAILABILITY.md` — which pairs and granularities exist
- `INDICATOR_INVENTORY.md` — indicators already implemented; do not invent new ones lightly

---

## Your assignment

You are assigned **exactly one row** of `forex_swing_strategies.csv` (row N, 1-indexed
excluding the header). Read that row's twelve fields in full. Your job is **not** to write
code. It is to convert trader prose into an unambiguous specification that a different agent
can implement mechanically in Wave 2 without making a single interpretive decision.

The CSV was written by discretionary traders. Its language hides decisions. Example, from
row 1:

> "when price resumes trend direction place buy stop 2 pips + spread above the SECOND
> consecutive higher high"

That sentence contains at least five unresolved decisions:

1. Which swing detector defines a "higher high", and with what lookback?
2. "Second consecutive" — counted from when? Does the count reset on a lower high?
3. When is the swing *knowable*? (A swing high at bar *k* is only confirmed at *k+period*.)
4. Is "+ spread" applied at decision time or at fill time?
5. What if a third higher high forms before the buy stop fills — re-place the order, or
   leave it?

**Your deliverable resolves every one of these, explicitly, choosing the more conservative
reading each time, and records what you rejected.**

---

## Required output: `SPEC-<strategy_id>.md`

Use exactly this structure. `<strategy_id>` is `lower_snake_case`, 3–64 chars, derived from
`strategy_name` — e.g. "Riding The Trend after Retracement" → `riding_trend_retracement`.

```markdown
# SPEC-<strategy_id>

**Source:** row <N> of forex_swing_strategies.csv · <source_url>
**Conviction (author's):** HIGHLY_RECOMMENDED | MODERATE | EXPERIMENTAL

## 1. Hypothesis
One paragraph, ≥ 8 words, stating the edge this strategy claims and *why it should
persist*. Not a restatement of the rules — the economic or behavioural reason. This is
required by the contract and a reviewer will check it against results later.

## 2. Scope
- primary_granularity: <H1|H4|D1|W1>       # the frame signals are emitted on
- context_granularities: [...]             # e.g. [D1] for a D1 trend filter; [] if none
- simulate_on: H1                          # fill-resolution frame; H1 unless stated
- pairs_requested: [...]                   # verbatim from the CSV
- pairs_available: [...]                   # intersect with DATA_AVAILABILITY.md
- pairs_missing: [...]                     # → triggers a DATA-GAP note

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| ema | 8 | INDICATOR_INVENTORY (ema) |
| confirmed swing highs | period=5 | causal_structure.confirmed_swing_points |

Every indicator MUST map to either the existing inventory or `causal_structure`. If the
strategy needs something absent from both, say so here and specify it precisely enough to
implement — do not hand-wave.

## 4. Entry — long
Numbered, mechanical conditions. Each MUST be evaluable from data at or before the decision
bar. Then state the order:
- entry type: market | buy_stop | buy_limit
- entry level: <exact formula>
- expires_after_bars: <n>

## 5. Entry — short
Mirror of §4. If the strategy is long-only, say so explicitly and say why.

## 6. Stop
- initial stop: <exact formula>
- move_to_breakeven_on: <leg label | none>
- trail: <atr multiple | none>

## 7. Exit legs
| Label | Fraction | Kind | Level formula |
|---|--:|---|---|
| TP1 | 0.333 | take_profit | entry + 200 pips |
Fractions MUST sum to 1.0.

## 8. Filters
Trend filters, session filters, volatility filters, anything gating entry. State the
timeframe each is evaluated on and — critically — **when it becomes knowable**.

## 9. Causality audit
For each rule above, state the bar at which its inputs are fully known. Any rule depending
on a swing point MUST state the confirmation lag. This section is what a reviewer reads
first; a spec that skips it is rejected.

## 10. Ambiguities resolved
| # | Ambiguity in the source | Conservative reading taken | Alternative rejected |
|---|---|---|---|
Minimum of three rows for any non-trivial strategy. If you found none, you did not read
carefully enough — the source is trader prose, it is always ambiguous somewhere.

## 11. Expected behaviour
- rough trade frequency (the CSV often states it — e.g. "1 trade per 4-8 weeks per pair")
- what would make this strategy fail the gates
- whether the author's stated conviction seems justified by the rules as written
```

---

## Rules

1. **Do not write implementation code.** Formulas in the spec are fine and encouraged;
   a Python module is not your deliverable.
2. **Conservative readings only.** Where two readings exist, take the one that produces
   fewer trades, later entries, or worse fills — and record the other in §10.
3. **Swing/pivot/ZigZag logic MUST account for confirmation lag.** A swing high at bar *k*
   is knowable only at bar *k+period*. A spec that treats it as knowable at *k* is
   look-ahead and will be rejected. This applies to 36 of the 51 strategies — assume it
   applies to yours until you have checked.
4. **Do not invent data.** If the strategy needs COT positioning, options flow, an economic
   calendar, tick volume, VIX, or DXY, it goes in the data-gap note — do not substitute a
   proxy without flagging it prominently in §10.
5. **Fractions sum to 1.0.** If the source says "scale out 3 lots", that is 0.333/0.333/0.334,
   not three separate full-size trades.

---

## Conditional deliverable: `DATA-GAP-<strategy_id>.md`

Produce this **only if** the strategy needs a pair, granularity, or data source not listed
in `DATA_AVAILABILITY.md`. Structure:

```markdown
# DATA-GAP-<strategy_id>

## What is missing
Precisely: which pairs, which granularity, which external series.

## Why the strategy needs it
Quote the CSV field that requires it.

## How it could be obtained
- OANDA v20 REST (same ingest path as existing pairs) — cheapest, already built
- another vendor — name it, note licence/cost
- derivable from existing data — show the derivation
- not obtainable — say so plainly

## Recommended integration
Concrete: the ingest command, the `dim_asset` row, the schema change if any.

## Recommendation
Implement now with reduced pair coverage / defer until data lands / drop the strategy.
State which, and why.

## Impact if we proceed without it
What the backtest would measure instead, and whether that is still informative.
```

These notes are collated into the `.docx` the operator asked for. Write them to be read by
a decision-maker, not by an engineer: lead with the recommendation.

---

## Definition of done

- `SPEC-<strategy_id>.md` complete, all 11 sections, no section left as a placeholder
- §9 causality audit covers every rule, with explicit confirmation lags
- §10 has at least three resolved ambiguities (or a defensible argument that the source is
  fully mechanical)
- `DATA-GAP-<strategy_id>.md` if and only if data is missing
- Every indicator maps to the inventory or to `causal_structure`, or is fully specified
