# REPORT — reps_donchian_pyramiding

**Spec:** `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-reps_donchian_pyramiding.md`
(row 14 of `forex_swing_strategies.csv`) · **Batch:** 4 (multi-timeframe)
**Written:** 2026-08-16. This is a **rebuild** — see *Deviations*, item 0.

## Implemented

A D1-decided Turtle descendant with three emission kinds per direction:

- **INITIAL_LONG / INITIAL_SHORT** — the most recently closed derived-weekly bar closed
  through its shifted 20-week Donchian band. Fires once per weekly breakout event, at the
  first D1 bar that can see it.
- **ADDON_*_D1** — a fresh crossover of the shifted D1 Donchian(20) in the series direction
  (`close(t)` through, `close(t-1)` not through), gated by the pyramid-into-strength proxy
  (§10 #8): the close must be beyond the decision close of the most recent same-direction
  emission.
- **ADDON_*_H4** — within the ≤12 most recent closed H4 bars, an H4 close through the band
  opposite the series direction followed by a *later* H4 close through the band in the
  series direction. Same pyramid proxy, at most one per D1 bar.

Series state machines are independent per direction, ACTIVE from the initial emission until
a D1 close through the opposing shifted D1 band (§10 #11 — never on an assumed exit, which
a v2 strategy cannot observe). Every intent is a market order with `expires_after_bars=1`,
a static stop at the shifted H4 band (§6, no breakeven, no StopRule trail per §10 #5/#6) and
a single `ExitLeg(fraction=1.0, kind="trailing", atr_multiple=6.0)` (§7).
`max_concurrent_positions = 4` is declared per §2 / §10 #2 (F12): 1 initial + at most 3
add-ons; the engine refuses the 5th concurrent position while emission continues.

The weekly frame is **derived from D1**, never loaded (§10 #3): D1 opens are shifted +3h so
each session falls on its own calendar day, sessions are grouped by the ISO week of that
day, and High/Low/Close are the week's max/min/last. The derived frame is stamped at its
own open, shifted forward one full weekly interval and asof-merged with
`allow_exact_matches=False` — the mechanics §3 prescribes.

## Deviations

0. **The module was rebuilt, not patched.** The version on disk before today emitted zero
   orders on any data and had never been measured. Its `OrderIntent`s were invalid at
   construction on two counts — `entry="market"` with `entry_price=0.0` (the contract
   requires `None`) and `ExitLeg(kind="trailing", price=0.0, …)` (a trailing leg must not
   carry a price) — so every emission path raised `ValueError`, and its fixture never
   reached one. There is no earlier verdict to preserve or contradict; this report and the
   ledger row are the strategy's first measurement.
1. **Context is consumed at the decision bar's OPEN, not its close.** §6 anchors the stop at
   "the last H4 bar closed at/before the D1 decision bar", and §4.3 evaluates the H4 pattern
   over "the H4 bars comprising D1 bar *t* and the preceding D1 bar". Both are unusable as
   written: `assert_no_lookahead_v2` truncates a context frame to the bars closed by the
   *open* of the last surviving primary bar, so any use of H4 data from inside the decision
   bar's own session produces an order the truncated re-run cannot reproduce, and the
   strategy is rejected. Stop level and H4 window are therefore anchored one D1 session
   earlier: the stop is the shifted H4 band at the last H4 bar closed by the decision bar's
   open, and the pattern window is the ≤12 H4 bars ending there (sessions *t-2* and *t-1*).
   This is the same convention every other multi-timeframe strategy in the set uses, and the
   one the reference strategy documents. No directional bias is claimed — the stop is one
   session staler, which can be tighter or wider; the add-on pattern is strictly later.
2. **`context_granularities = ("H4",)`, not `("W1", "H4")`.** §2 asks for `"W1_derived"`,
   which is not a legal granularity. Declaring plain `W1` would make the harness *require*
   the native weekly feed as mandatory data — a frame §10 #3 deliberately refuses to read —
   and a pair whose W1 backfill was missing would be skipped entirely rather than measured.
   The weekly context is derived from D1 inside the strategy and documented in the module
   docstring.
3. **A weekly event is spent when it fires, even if the stop guard blocks the emission.**
   §4.2 says the signal fires exactly once per weekly breakout event; §4.3's guard can veto
   that one emission. The guard is not treated as "try again next bar", because that would
   convert one weekly event into up to five daily attempts.

## Uncertainties

- **DECISION — §3 and §4.2 disagree by one D1 bar.** §4.2 says the initial entry fires at
  "the first D1 decision bar after *w* closed" (the Sunday-stamped bar). §3's mandated
  mechanics — shift the weekly index forward one full weekly interval, `merge_asof` with
  `allow_exact_matches=False` — make the week first visible on the *Monday*-stamped bar,
  one session later. I implemented §3's mechanics because they are operational and the
  conservative one of the two. If the reviewer prefers §4.2's reading, the change is to
  stamp the derived weekly bar at its close and allow exact matches; entries move one
  session earlier and every result changes.
- **DECISION — the H4 add-on window is defined in bars, not sessions.** §4.3 says "up to 12
  H4 bars", which is two full sessions only when the broker prints 6 H4 bars per session.
  Around holidays and DST the window can span more or less than two sessions. I kept the
  bar count, as the spec states it.
- **The §7 trailing leg is a known fidelity loss, not a modelling choice.** The source's
  exit is "close all when price hits the opposing D1 Donchian band" — a moving level no
  `ExitLeg` kind can express. §7's 6×ATR(14) H1 trail is tighter than that band in most
  conditions, so winners are truncated. §11 predicts this removes the fat right tail the
  strategy's edge lives in. The verdict below should be read with that in front of it.
- The pyramid's "zero added risk" property (§10 #7) is position sizing and is not
  reproduced at all. Every intent carries `size_fraction = 1.0`.

## Coverage

- **Declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD — the five pairs with live data.
- **Wanted by the spec but absent:** EUR_AUD (the one pair the author explicitly prefers),
  GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, AUD_NZD, EUR_CAD. §2 lists them as
  "Wave-1 pending"; the Wave-1 pair additions never landed. The author's stated preference
  for habitual trenders is therefore untestable — the five available majors include two of
  the least trending pairs in the set.
- **Skipped by the harness:** none. All five cells produced trades.

## Verdict

Harness run 2026-08-16T06:59:36Z — **FAIL**.

| metric | pooled |
|---|--:|
| OOS trades | 241 |
| profit factor | 0.81 |
| Sharpe | −0.38 |
| max drawdown | 20.25% |
| win rate | 30.3% |
| recovery factor | −0.61 |
| OOS months | 83.9 |
| cells passed | 0 of 5 |

Four gates fail; only max drawdown is inside its limit. A 30% win rate is what a
trend-following pyramid is supposed to look like, but the right tail that has to pay for it
is not there: dispersion runs from PF 2.05 on USD_CAD (38 trades) to PF 0.32 on AUD_USD
(41 trades), i.e. the pooled result is a wash of one trending pair against one ranging one,
on a per-cell sample too small to separate them. The harness run was executed once, on the
rebuilt module; no code changed after seeing it.
