# REPORT-h4_forex_system

> Transcribed verbatim by the orchestrator from the authoring agent's returned text (this
> harness refuses subagent writes to `.md` report files).

**Strategy id:** `h4_forex_system` · **Class:** `H4ForexSystem`
(`src/layer0/strategies/research/h4_forex_system.py`)

**Verification:** all three pass.

- `black` — clean (no reformatting needed on final check)
- `mypy --ignore-missing-imports --follow-imports=silent` — `Success: no issues found in 1 source file`
- `pytest src/layer0/strategies/research/tests/test_h4_forex_system_fixture.py -q` — `6 passed`

**Fixture output:** exactly 2 orders — 1 long (decision bar idx 6,
`2020-01-02 00:00:00+00:00`), 1 short (decision bar idx 10, `2020-01-02 16:00:00+00:00`).
`assert_no_lookahead_v2` was also run directly against the fixture frames outside pytest as a
sanity double-check — passes.

## Implemented

- 6-EMA / 13-SMA cross, MACD(12,26,9) same-bar cross, and Parabolic SAR (Wilder 1978)
  position, as a strict three-way conjunction on the H4 native frame (spec §4/§5, §10 #1). No
  context frames (`context_granularities: none`).
- Parabolic SAR implemented as a private module-level function `_parabolic_sar` (step=0.02,
  max=0.20), following spec §3's recursion exactly, including the clamp against
  `Low[t-1]`/`Low[t-2]` (long) or `High[t-1]`/`High[t-2]` (short) and the reversal rule that
  reseeds `SAR` at the prior leg's extreme point.
- Static per-cell stop and single take-profit leg anchored at the decision-bar close (spec
  §6/§7): H4 GBP_USD SL = 70 pips, TP = 60 pips. No breakeven, no trailing, no signal-based
  exit (both correctly rejected as inexpressible per §10 #2/#4).
- `warmup_bars = 27` per spec §3 ("slow EMA 26 + signal seed"), with an explicit per-bar
  `isfinite` gate on every input (EMA/SMA/MACD/signal at t and t-1, PSAR at t) so nothing
  fires before all indicators are defined.
- `metadata.pairs = ["GBP_USD"]` only — GBP_JPY excluded per spec §2 (pending Wave-1 backfill).

The spec was not thinner than the code needed anywhere notable; §3's PSAR recursion was
unusually explicit and translated close to literally.

## Deviations

None from the H4 cell as specified. One scope decision, recorded under Uncertainties rather
than silently resolved.

## Uncertainties

1. **D1 cell not implemented.** Spec §2/§10 #6 describes the source's D1 variant as a
   *separate cell* (own SL/TP table: SL = 100/150, TP = 280/320 for GBP_USD/GBP_JPY), run
   independently of the H4 cell. `StrategyMetadataV2.primary_granularity` is a single field,
   and this fleet assigns one file per `strategy_id`; the assigned id is `h4_forex_system` and
   spec §2's top-level `primary_granularity: H4` names the H4 cell specifically. Only the H4
   cell was implemented, and no second class/file for D1 was invented, since (a) no
   `SPEC-d1_forex_system.md` (or similar) exists in this wave's spec set to translate against,
   and (b) inventing a D1 variant under the `h4_forex_system` id would need a
   `primary_granularity="D1"` that collides with the declared metadata. This is the more
   conservative reading (fewer cells traded). **Flagged as load-bearing**: if the reviewer
   intended one agent to cover both cells, the D1 cell — which spec §11 calls "the more
   plausible carrier of any edge", R:R 2.8/2.1 vs H4's sub-1R — is currently missing entirely
   from the fleet's output under this id.
2. **GBP_JPY pip/SL/TP table is present but unreachable.** `SL_PIPS`/`TP_PIPS` are kept as
   dicts keyed by pair (mirroring spec §6/§7's tables, including the GBP_JPY row) even though
   `metadata.pairs` only contains `GBP_USD`, so the code is forward-compatible if GBP_JPY's
   backfill completes and pairs get extended later — but as written today that GBP_JPY row is
   dead code. Noted so a reviewer does not mistake it for scope creep.
3. Spec §11 itself flags the H4 cell's sub-1R risk:reward (70:60) as structurally likely to
   fail deployment gates even before costs. Implemented as specified (no parameter tuning per
   hard rule 5) — flagged per the spec's own words, not proposing a fix.

## Fixture rationale

36 H4 bars, constant `High = Close + 0.0010` / `Low = Close - 0.0010` spread throughout (so
every EMA/SMA/MACD/PSAR value is reproducible from `Close` alone by hand):

- idx 0–5: flat at 1.1000 — seeds Parabolic SAR in long mode with zero cushion (the dot sits
  exactly on the bar, never below, since `SAR == Low` when flat) and warms SMA(3).
- idx 6–9: a clean rise 1.1030 → 1.1120 — by bar 6 the EMA/SMA analogue crosses up, the MACD
  analogue crosses up, and the SAR (still lagging from the flat seed at 1.0990) sits strictly
  below the bar: all three §4 conditions land on bar 6 by construction.
- idx 10: a sharp drop to 1.0950 — engineered to push `Low[10]` under the still-rising
  long-mode SAR (forcing the §3 reversal to short mode, with SAR jumping to the prior leg's
  extreme 1.1130, well above price, satisfying "dot above") while simultaneously flipping the
  EMA/SMA and MACD analogues down. All three §5 conditions land on bar 10.
- idx 11–35: ease down to a floor at 1.0920 and hold flat for 23 bars — pads to 36 bars and
  drives EMA/SMA to exact equality, so the three-way conjunction can never re-fire; this is
  what lets the fixture assert "exactly 2 orders", not just "the first 2".

The fixture subclasses `H4ForexSystem` to shrink `EMA_FAST_PERIOD` (6→1), `SMA_SLOW_PERIOD`
(13→3), `MACD_FAST/SLOW/SIGNAL` (12/26/9→1/2/2), and `warmup_bars` (27→3) — the same pattern
as the reference fixture's `_FixtureScale`. `PSAR_STEP`/`PSAR_MAX_AF` were deliberately **not**
shrunk since they are the level formula itself, not a lookback period. Every intermediate
EMA/SMA/MACD/PSAR value used in the two hand-arithmetic comment blocks was derived from the
spec's recursions before running any code, then verified against the actual output (matched
exactly, including the float-rounding artifact `1.1019999999999999` for the short stop, which
`pytest.approx` absorbs).

## Shared files

Nothing outside the two deliverable files was touched. No issues found in `contract_v2.py`,
`causal_structure.py` or `indicators.py` that needed reporting — `indicators.py` correctly has
no Parabolic SAR, matching spec §3's expectation that it be private.
