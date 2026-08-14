# REPORT-inside_bar_continuation_ea

> Transcribed verbatim by the orchestrator from the authoring agent's returned text (this
> harness refuses subagent writes to `.md` report files).

**Verification:** black `PASS` · mypy `PASS` (`Success: no issues found in 1 source file`) ·
pytest `PASS` (8/8). Fixture produces exactly **2 orders**: one `buy_stop` (direction +1) at
bar 7, one `sell_stop` (direction −1) at bar 21.

Files delivered:

- `src/layer0/strategies/research/inside_bar_continuation_ea.py`
- `src/layer0/strategies/research/tests/test_inside_bar_continuation_ea_fixture.py`

## Implemented

A single-timeframe (H4, no context frames) inside-bar breakout. Five gates per side (Main Bar
direction, body dominance ≥ 0.5 × range, ATR14 size filter ≥ 1.5×, strict Signal Bar
containment, Signal Bar size ≤ 0.5 × Main Bar range), pending `buy_stop`/`sell_stop` at the
exact Main Bar extreme, `expires_after_bars=1`, static stop at `entry ∓ 0.62 × rng[t-1]`,
single TP1 leg at 1.0R (fraction 1.0), no breakeven/trail. `rng`/`body` implemented as private
module-level helpers per spec §3 (not inventory indicators). `pairs` set to the 5 live pairs
only (EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD) per the brief's rule to never include
pending pairs. `warmup_bars = ATR_PERIOD * 3 = 42`.

## Deviations

None from the spec. An explicit `if close_prev == open_prev: continue` (doji Main Bar) branch
was added; the spec does not discuss dojis explicitly, but §4.1/§5.1 require strict `>`/`<`,
so a flat Main Bar satisfies neither and correctly produces no order — a direct reading of the
stated rule, not a new gate.

## Uncertainties

None requiring escalation. One note: the fixture shrinks `ATR_PERIOD` from 14 to 1 (making
`ewm(span=1)` degenerate to `atr[t] == true_range[t]` with zero history-dependence), which is
what makes the ATR-filter arithmetic hand-checkable on 30 bars without a multi-step EWM
recursion. This only shrinks a lookback period, per the brief's explicit allowance, and does
not touch logic.

## Fixture rationale

30 H4 bars: three flat "filler" blocks (Open == Close everywhere, so they can never pass the
Main Bar directional gate, and identical adjacent bars can never satisfy strict containment)
bracket two hand-built setups — a bullish Main Bar + contained Signal Bar at bars 6–7 (fires
long) and a bearish Main Bar + contained Signal Bar at bars 20–21 (fires short). Both setups
use `rng[Main]=0.0070`, `body[Main]=0.0060` (dominance ratio 0.857), and Signal Bars
sized/positioned so `true_range[Signal]=0.0022` clears the 1.5× ATR filter
(`0.0070 ≥ 1.5 × 0.0022 = 0.0033`) — every number and the resulting stop/TP levels are derived
by hand in the test docstrings, tied back to spec sections §3–§7. An additional test
(`test_no_spurious_orders_from_filler_bars`) directly re-runs the strategy on filler-only
slices to prove no spurious signals independent of the two-order count check.

## Shared files

No issues found — `contract_v2.py`, `causal_structure.py` and `indicators.py` were read-only
references and needed no changes for this strategy (no swing/pivot constructs used, matching
spec §3's explicit statement that `detect_swing_points` is not referenced).
