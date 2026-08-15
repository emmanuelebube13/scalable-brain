# REPORT-h4_box_breakout

> Transcribed verbatim by the orchestrator from the authoring agent's returned text (this
> harness refuses subagent writes to `.md` report files).

## Verification results

- `black` — pass (test file received only whitespace reformatting; strategy file unchanged)
- `mypy --ignore-missing-imports --follow-imports=silent src/layer0/strategies/research/h4_box_breakout.py` — **Success: no issues found in 1 source file**
- `pytest src/layer0/strategies/research/tests/test_h4_box_breakout_fixture.py -q` — **11 passed**

Fixture produces **4 orders**: 2 long (`buy_stop`) and 2 short (`sell_stop`) — one long/short
pair per box (2 boxes in the fixture). All fire correctly; none blocked.

Files delivered (the only files touched):

- `src/layer0/strategies/research/h4_box_breakout.py`
- `src/layer0/strategies/research/tests/test_h4_box_breakout_fixture.py`

## Implemented

`H4BoxBreakout(StrategyV2)`. Box = the H4 bar stamped Sunday 21:00 UTC, found by a private
`_week_open_box_positions` helper matching on `(dayofweek, hour, minute, second)` — no
lookback, no context frame (`context_granularities=()`), zero confirmation lag per spec §9.
At that bar's close, emits a `buy_stop` at `box_high + 21 pips` and a `sell_stop` at
`box_low − 21 pips`, both `expires_after_bars=29`, stop at the opposite box edge (no buffer),
and a four-leg equal-weighted (0.25 each) take-profit ladder at 1/2/3/4 box heights anchored
to the declared entry level. `warmup_bars=1` (only to protect against a truncated boundary
bar — the box itself needs no real lookback). No swing structure, no MTF join, no indicators
beyond `get_pip_value`.

The spec was fully mechanical here — nothing needed inventing beyond what §3–§10 already
specify literally.

## Deviations

None. Implemented exactly as specified, including the deliberately "worse-than-source"
choices the spec calls out (wider 21-pip buffer, equal-weighted ladder, no breakeven,
both-sides-fill risk retained).

## Uncertainties

1. **Pair declaration vs. the fleet's general "never declare a pending pair" rule.** The
   RUN_BRIEF's metadata guidance says `pairs` = "the *available* pairs from §2 (never a pair
   the spec lists as missing/pending)." But this spec's own §2 lists **only** GBP_JPY and
   EUR_JPY under "pairs_available" — each annotated "pending" (Wave-1 backfill in flight) —
   with an explicit instruction: "declare, harness skips if backfill incomplete." Zero pairs
   are currently fully live. Resolved by declaring `["GBP_JPY", "EUR_JPY"]`, reasoning that
   (a) `StrategyMetadataV2` requires at least one pair, (b) the spec's own explicit
   instruction overrides the brief's generic phrasing for this specific case, and (c) the
   harness — not the strategy module — is stated to be the mechanism that skips incomplete
   backfills. **This is the load-bearing call in this submission** — if the reviewer's intent
   was instead "declare zero pairs / this strategy cannot exist yet," that would need a
   different resolution (e.g. the strategy simply cannot pass `StrategyMetadataV2`'s "at
   least one pair" gate, so it may need to sit out of this wave entirely). Flagged explicitly
   per the judgement-call rule.
2. Per spec §2/§10 note, a `DATA-GAP-h4_box_breakout.md` is called out as a required
   deliverable in the spec text, but the RUN_BRIEF restricts the agent to exactly two files
   ("touch nothing else"). That file was not created — noting its absence for the
   reviewer/orchestrator to handle centrally. (One already exists at
   `task/2026-August-week1/wave0/DATA-GAP-h4_box_breakout.md`.)
3. Spec §10 row 1 rejects a DST-drifting week boundary and fixes it at literal Sunday 21:00
   UTC. If the live OANDA H4 feed's winter week-open bar is ever stamped 22:00 UTC (DST edge
   case) rather than 21:00, those weeks would silently produce no box / no setup. Inherited
   directly from the spec's own resolution, not introduced here, but flagged since it is a
   live-data behaviour worth the reviewer's awareness.

## Fixture rationale

40 hand-built H4 bars around a GBP_JPY tape (185.00 handle), split into three calendar
fragments to test the calendar logic itself, not just the arithmetic:

- **Bars 0–5**: tail of a week whose Sunday-21:00 box bar is *not* in the frame → proves a
  week without its week-open bar produces nothing (§3 step 2 / §10 row 8), and that
  Monday-01:00 bars are never mistaken for boxes (§10 row 1).
- **Bars 6–35**: one complete 30-bar feed week (Sun 21:00 → Fri 17:00), with bar 6 as a
  deliberately round 1.00-wide box (185.00/184.00) so every downstream level is exact by
  hand; price breaks the long trigger mid-week and trends, a realistic path.
- **Bars 36–39**: start of the next feed week with a second, narrower 0.50-wide box
  (186.50/186.00) after a weekend gap — proves the ladder is rederived per-box from `H`, not
  hard-coded.
- A separate 4-bar `FLAT_BOX_BARS` series with `High == Low` on the box bar proves the
  `H <= 0` degenerate-week skip (§3 step 3).

On the main series the strategy fires exactly 4 times (2 long, 2 short) — one long/short pair
per box — with all entry/stop/TP arithmetic verified by hand in comments against
§3/§4/§5/§6/§7, plus dedicated assertions for the ladder fraction sum, the sub-1R TP1
consequence of the buffer, the pending-order market-side rule, and the literal (unbuffered)
opposite-box-edge stop. `assert_no_lookahead_v2` passes and is meaningful here because box
#1's decision bar (position 6) falls inside every truncation window the probe constructs at
this fixture size — confirmed by tracing the probe's windowing math against `n=40`,
`warmup_bars=1`.

---

## Orchestrator note

Uncertainty 1 is genuine and unresolved. Because both declared pairs are pending backfill,
this strategy is expected to come back **SKIP** ("no real data for any declared pair") from
`verify_wave2.py` rather than PASS — which is the correct outcome, not a failure, but it
means the real-data look-ahead probe has **not** been exercised for this strategy. It will
need a re-run once GBP_JPY/EUR_JPY land. Note also that the Wave-0 gap register lists this
strategy's gap as AUD_JPY/CHF_JPY/CAD_JPY with a verdict of "implement now with reduced
coverage", which does not obviously square with §2 offering only two pending JPY crosses;
the reviewer should reconcile the register against the spec.
