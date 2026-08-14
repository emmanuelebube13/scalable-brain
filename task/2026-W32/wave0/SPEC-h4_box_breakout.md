# SPEC-h4_box_breakout
**Source:** row 36 of forex_swing_strategies.csv · https://www.trade2win.com/threads/4h-box-breakout.63584/
**Conviction (author's):** MODERATE

## 1. Hypothesis
The first 4-hour range of a trading week on volatile JPY crosses marks the market's initial
equilibrium after the weekend close; a decisive break of that range, beyond a noise buffer,
signals that the week's dominant directional flow (institutional position-building, weekend
news resolution, Asian-session JPY repricing) has committed, and that commitment tends to
persist for one to four box-heights because early-week positioning is not yet profitable
enough to unwind. The edge should persist as long as JPY crosses concentrate weekly
range-expansion into their opening sessions and breakout-following flows outnumber faders.

## 2. Scope
- **primary_granularity:** H4 (the box is one H4 bar; all logic is evaluated on the H4 frame)
- **context_granularities:** none. The "weekly" grouping is a calendar partition of H4 bars,
  not a W1 frame read; no W1 data is consumed (this also dodges the stale-W1 problem).
- **simulate_on:** H1 (fills, stops, and legs resolved against H1 bars within each H4 span)
- **pairs_requested (verbatim):** `GBP/JPY | EUR/JPY | AUD/JPY | CHF/JPY | CAD/JPY`
- **pairs_available:**
  - GBP_JPY — **pending** (Wave-1 addition; declare, harness skips if backfill incomplete)
  - EUR_JPY — **pending** (Wave-1 addition; same)
- **pairs_missing:** AUD_JPY, CHF_JPY, CAD_JPY — none is live and none is in the Wave-1
  addition list (Wave-1 adds USD_CHF and EUR_CAD/USD_CAD, not the JPY crosses).
  → **DATA-GAP-h4_box_breakout.md** (required). With zero pairs live today, the strategy
  is untestable until at least the Wave-1 GBP_JPY/EUR_JPY backfill lands.
- **Pip convention:** all named pairs are JPY crosses → 1 pip = 0.01 price units. Use
  `get_pip_value(asset)` / `calculate_pips(...)` from the indicator inventory; no literals.

## 3. Indicators
| Indicator | Params | Source |
|---|---|---|
| Weekly box high (`box_high`) | high of the single H4 bar stamped Sunday 21:00 UTC (week's first bar) | Private mechanical construct — specified here in full, see below |
| Weekly box low (`box_low`) | low of the same bar | Private mechanical construct — same |
| Box height `H` | `box_high − box_low` (price units) | Derived from the above |
| `get_pip_value` / `calculate_pips` | per-asset | `indicators.py` inventory (pip-size conversion only) |

**Box construction, fully specified (private helper; no inventory addition needed):**
1. Partition the H4 frame into ISO feed-weeks. The feed week opens Sunday 21:00 UTC and
   closes Friday 21:00 UTC (market closed in between Friday/Sunday).
2. `box_bar` = the first H4 bar of the feed week, i.e. the bar stamped **Sunday 21:00 UTC**
   (it covers Sun 21:00 → Mon 01:00 UTC). If that bar is absent (holiday), skip the week
   entirely — do NOT substitute the next bar (recorded in §10).
3. `box_high = box_bar.High`, `box_low = box_bar.Low`, `H = box_high − box_low`.
   If `H <= 0`, skip the week (degenerate/flat bar).
4. These three scalars are knowable at the **close of the box bar = Monday 01:00 UTC**,
   which is exactly the decision point (see §9).

No other indicators. The source explicitly states "no indicators".

## 4. Entry — long
Evaluated once per week, at the **close of the box bar** (decision_bar = the box bar,
stamped Sunday 21:00 UTC; its close is Monday 01:00 UTC):

1. `box_high`, `box_low`, `H` computed as in §3; `H > 0`.
2. Buffer `B = 20 pips + 1.0 pip = 21 pips` (20 = conservative end of the source's
   "10–20 pip" range — wider trigger = fewer, later entries; 1.0 pip = the cost-model
   spread standing in for the source's "+ spread", see §8/§10 and the DATA-GAP note).
3. Emit a `buy_stop` OrderIntent:
   - **entry type:** `buy_stop`
   - **entry level (exact):** `E_long = box_high + B` = `box_high + 21 × pip_size`
     (absolute price, fully knowable at decision-bar close; satisfies decision-bar anchoring)
   - **expires_after_bars:** `29` H4 bars. Arithmetic: a feed week spans Sun 21:00 →
     Fri 21:00 UTC = 120 h = **30 H4 bars**; the box bar is bar 0 and is also the decision
     bar; fills are eligible from bar 1 (F1); `29` keeps the order live through bar 29,
     stamped Friday 17:00 UTC — the last complete bar of the week — and guarantees expiry
     before the next week's box bar. Harmful cross-week overlap is therefore arithmetically
     impossible for a single side.
   - Emitted together with the §5 short intent as **one weekly setup** (see §10, row 5, for
     the residual both-sides-fill risk: there is no OCO).

No other long conditions. No trend, session, or volatility gate exists in the source.

## 5. Entry — short
Mirror of §4, at the same decision bar:
1. Same box and buffer.
2. Emit a `sell_stop` OrderIntent:
   - **entry type:** `sell_stop`
   - **entry level (exact):** `E_short = box_low − B` = `box_low − 21 × pip_size`
     (spread buffer applied symmetrically — conservative reading, §10 row 6)
   - **expires_after_bars:** `29` (same arithmetic as §4).

## 6. Stop
- **Initial stop (exact formula):**
  - Long: `stop = box_low` (the opposite side of the box, literally as sourced — no buffer)
  - Short: `stop = box_high`
  Both are absolute prices knowable at the decision bar.
  Declared risk per unit = `|E − stop| = H + 21 pips`.
- **move_to_breakeven_on:** `none` (the source never moves the stop; adding breakeven-on-TP1
  would be an invention, and a breakeven move only *improves* outcomes — rejected in §10).
- **trail:** `none` (static stop for the life of the trade; source has no trailing rule).

## 7. Exit legs
Box height `H`; entry level `E` as declared in §4/§5 (TP geometry anchored to the **declared
entry level**, which is knowable at emission — the fill-anchored reading is inexpressible
under contract v2 and is rejected in §10, row 4).

Long (short mirrors with `E_short − k × H`):

| Label | Fraction | Kind | Level formula |
|---|---|--:|---|---|
| TP1 | 0.25 | take_profit | `E_long + 1 × H` |
| TP2 | 0.25 | take_profit | `E_long + 2 × H` |
| TP3 | 0.25 | take_profit | `E_long + 3 × H` |
| TP4 | 0.25 | take_profit | `E_long + 4 × H` |

Fractions sum to **1.0** (0.25 × 4). Equal weighting is the conservative reading of the
ladder; the OP's stated preference for "holding toward 2x+ and not banking at 1x" implies
tail-weighting, which produces **larger** winners and is rejected (§10, row 3). Note TP1
sits at `+1 × H` from entry while risk is `H + 21 pips`, so declared TP1 is slightly **less
than 1R** — an honest consequence of the buffer, kept as written.

Open legs at end-of-data close per F11 (`END_OF_DATA`, flagged).

## 8. Filters
- **Breakout noise buffer (the only filter in the source):** the 21-pip trigger offset
  (`20 pips + 1.0-pip spread proxy`). Evaluated on H4 at the decision bar; knowable at the
  box bar's close (Mon 01:00 UTC).
  **FLAG (proxy, per fleet rule 5):** the source's "+ spread" means the live spread at
  trigger time; no historical spread series exists in the data. The 1.0-pip cost-model
  constant (F10) is used as the proxy. JPY-cross spreads frequently exceed 1.0 pip, so the
  proxy **understates** the real trigger distance → this filter is *less* conservative than
  the source intended; recorded in §10 row 2 and in the DATA-GAP.
- **One-setup-per-week gate:** intents are emitted only at the box bar's close, and
  `expires_after_bars = 29` guarantees death before the next box bar. Enforced by emission
  schedule + expiry, knowable at the decision bar.
- **No trend filter, no session filter, no volatility filter, no news filter.** None appear
  in the source; none are added. (There is no news/calendar feed to gate on anyway —
  DATA_AVAILABILITY §"Non-price data".)

## 9. Causality audit
| Rule | Inputs | Bar at which inputs are fully known | Lag |
|---|---|---|---|
| Box construction (§3) | OHLC of the H4 bar stamped Sun 21:00 UTC | **Close of that same bar = Mon 01:00 UTC** | Zero extra bars: the box is one *completed* bar, not a swing/pivot; no confirmation lag exists. The decision_bar IS the box bar; F1 then forbids fills until the next H1/H4 bar, so the box can never act before it is closed. |
| Long trigger (§4) | `box_high`, `H`, pip size | Mon 01:00 UTC (box-bar close) | As above; fill eligibility from the next bar (F1) |
| Short trigger (§5) | `box_low`, `H`, pip size | Mon 01:00 UTC | Same |
| Stop (§6) | `box_low` / `box_high` | Mon 01:00 UTC | Static absolute level; never updated |
| TP legs (§7) | `E`, `H` | Mon 01:00 UTC (all four levels are constants declared at emission) | None |
| Weekly partition | Calendar (UTC) | Exogenous | None |
| Spread proxy (§8) | Constant 1.0 pip | At emission | None |

No swing points, ZigZag, pivots, or fractals are used — the banned `detect_swing_points`
is irrelevant here and no causal_structure function is needed. No multi-timeframe context
is read, so the §4 MTF causality rule is vacuously satisfied (single frame: H4 decisions,
H1 fill resolution only — the strategy never sees H1 data).

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "First 4H candle of the week (00:00 EST Monday)" — no such candle boundary exists in this feed (OANDA week opens Sun 21:00 UTC; an EST boundary drifts with DST) | Box = the single H4 bar stamped **Sunday 21:00 UTC** (the feed's actual week-open bar); knowable Mon 01:00 UTC | Source-broker 00:00 EST Monday candle — **unobtainable** in this feed; also rejected: "first H4 bar of Monday UTC" (stamped Mon 01:00), which discards Sunday-night price action and narrows/changes the box arbitrarily |
| 2 | Buffer "10–20 pips + spread" | **20 pips** (wider trigger = fewer, later entries = conservative) **+ 1.0-pip cost-model spread proxy = 21 pips total**, flagged as proxy (§8) | 10 pips (more, earlier, noisier entries); a variable/estimated live spread series (does not exist — would be invented data) |
| 3 | TP ladder weighting — OP "prefers holding toward 2x+, not banking at 1x" | **Equal 0.25 × 4** (sums to 1.0; smaller winners than the OP's preference) | Tail-weighting (e.g. 0.10/0.20/0.30/0.40) per the OP's stated preference — produces larger winners, inflates r-multiples; also rejected: front-weighting — not in the prose at all, pure invention |
| 4 | TP/risk measured from entry — source prose implies the actual fill | All geometry anchored to the **declared entry level** `E = box edge ± 21 pips` (knowable at emission, fleet rule 8); realized R ≠ declared R when the fill gaps through the stop level (F3/F6 resolve honestly) | Fill-anchored TP ladder — **inexpressible** under contract v2 (fill price unknowable at OrderIntent creation), not merely less conservative |
| 5 | "One trade per week per pair" vs contract v2 having **no OCO / cancel-on-fill** | Both pendings emitted simultaneously with `expires_after_bars = 29`; cross-week overlap arithmetically impossible (30-bar week, box bar = bar 0, order dies after bar 29 = Fri 17:00 UTC, before the next box bar). **Residual risk recorded:** within a whipsaw week BOTH sides can fill (F12 caps positions, does not gate pending fills — §3.2 step 5). Direction: the second fill is a stop-and-reverse the strategy never intended, doubling weekly exposure in exactly the weeks the method does worst → makes results *worse* than the "one trade" intent, i.e. conservative, accepted. | "The first fill cancels the other order" — mechanism does not exist, forbidden to write; shortening expiry to avoid same-week double-fill — would gut the strategy (breakouts often come mid-week) |
| 6 | Does "+ spread" apply to the short side (source mentions spread only on the long entry)? | **Symmetric** 21-pip buffer both sides (consistent, and wider = more conservative for shorts) | Asymmetric (spread on buys only) — literal but inconsistent, and cheaper shorts = more trades |
| 7 | SL "opposite side of the box" — with or without buffer? | **Exactly** `box_low` / `box_high`, no buffer (literal; a buffered stop would *widen* risk and improve TP-to-risk optics — flattering) | Stop beyond the box edge by the buffer (invents room the source never gave) |
| 8 | Missing week-open bar (rare holidays, e.g. New Year's week) | **Skip the week entirely** | Substitute the next available H4 bar as the box (arbitrary redefinition; the "opening range" meaning is lost) |

## 11. Expected behaviour
- **Frequency:** one setup (two pendings) per pair per week → at most ~52 trades/pair/year;
  realistically ~20–40 filled trades/pair/year (weeks where the 21-pip-beyond-box trigger
  is never reached produce no trade; when a fill happens it typically comes in the first
  1–3 days). With only the two pending pairs (GBP_JPY, EUR_JPY), expect ~40–80 trades/year
  across the fleet — adequate for gates over a 10-year lookback, thin per 6-month OOS fold
  (~10–20 trades/cell/fold; per-cell `low_confidence` flags are likely).
- **What would make it fail the gates:** (a) whipsaw weeks triggering both sides with the
  static opposite-side stop — full −1R on the first leg plus a degraded second entry;
  (b) F5 (stop-before-target within an H1 bar) punishing the tight TP1-at-≲1R geometry;
  (c) JPY-cross weekend gaps blowing through `box_low`/`box_high` stops (F6, losses > 1R);
  (d) large box heights on GBP_JPY making the 21-pip buffer irrelevant as a noise filter.
- **Is the author's MODERATE conviction justified by the rules as written?** Marginally.
  The structural logic (weekly opening-range resolution on volatile crosses) is coherent and
  the rules are fully mechanical, but the only performance claim is an unverified forum
  report of "700+ pips in one month (May 2009)" with no systematic backtest, and the honest
  implementation here is strictly harder than the source's (wider buffer, equal-weighted
  ladder, no breakeven, both-sides-fill risk retained, 1.0-pip spread proxy understating
  real JPY-cross spreads). MODERATE is defensible; anything higher would not be.
