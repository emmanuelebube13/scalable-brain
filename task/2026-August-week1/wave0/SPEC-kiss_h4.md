# SPEC-kiss_h4
**Source:** row 11 of forex_swing_strategies.csv · https://www.forexstrategiesresources.com/trend-following-forex-strategies/90-4h-kiss/
**Conviction (author's):** MODERATE

## 1. Hypothesis
In an established H4 trend, pullbacks to a rising (falling) 20-period linearly weighted moving average attract trend-following re-entry from traders who missed the initial move and from breakout sellers/buyers closing at a loss, so price tends to resume the trend from that dynamic support/resistance zone. Candlestick rejection patterns (engulfing, pin bar, tweezers) at the zone are evidence that the counter-trend move has been absorbed, and a rising positive MACD histogram confirms momentum has already turned back with the trend. The edge should persist because moving-average pullback levels are self-reinforcing focal points for a large population of discretionary and systematic trend followers, and entering only after rejection + momentum confirmation filters out the pullbacks that become reversals. The author's stated aim is a high win rate from small ADR-scaled targets rather than large R multiples.

## 2. Scope
- **primary_granularity:** H4
- **context_granularities:** none (all logic on H4)
- **simulate_on:** H1
- **pairs_requested (verbatim):** "Majors" — the exit_logic field enumerates: GBP/USD, EUR/JPY, GBP/JPY (high-ADR) and EUR/USD, AUD/USD (low-ADR)
- **pairs_available:** EUR_USD (live), GBP_USD (live), AUD_USD (live), EUR_JPY (pending, Wave-1 addition), GBP_JPY (pending, Wave-1 addition)
- **pairs_missing:** none of the five named pairs is a gap. USD_JPY and USD_CAD are live majors but are NOT traded by this strategy — the CSV's TP table does not classify them, so they are excluded (see §10 #1). No DATA-GAP file is required.

## 3. Indicators
All indicators computed on the H4 frame only. Notation: O/H/L/C = Open/High/Low/Close of the H4 bar; subscript t = decision bar (a completed bar); pip = 0.0001 for EUR_USD/GBP_USD/AUD_USD, 0.01 for EUR_JPY/GBP_JPY (via `get_pip_value`).

| Indicator | Params | Source |
|---|---|---|
| LWMA (linearly weighted MA) | period 20 on Close | **Private function (NOT in inventory).** Exact formula: `LWMA_t = ( Σ_{i=0}^{19} (20 − i) · C_{t−i} ) / 210` where 210 = Σ_{j=1}^{20} j. Uses only bars ≤ t. "Rising" means `LWMA_t > LWMA_{t−1}`; "falling" means `LWMA_t < LWMA_{t−1}`. |
| MACD histogram | fast=24, slow=52, signal=18 on Close | Inventory `macd(close, fast=24, slow=52, signal=18)` → use the `hist` output only. |
| ATR | period 14 on H4 H/L/C | Inventory `atr(high, low, close, 14)`. Used ONLY for the support/tweezer tolerances below. |
| Confirmed swing highs/lows | period=5 on H4 H/L | `causal_structure.confirmed_swing_points(high, low, period=5)` |
| Last 2 confirmed swing highs and lows | n=2, period=5 | `causal_structure.last_n_confirmed_highs(high, low, n=2, period=5)` (and its swing-low analogue) |

Candlestick patterns are NOT indicators; they are exact boolean tests on bars t and t−1, defined in §4/§5. `detect_swing_points` is BANNED and is not used.

## 4. Entry — long
Decision bar t is any completed H4 bar. ALL of the following must hold at the close of bar t:

1. **Trend (higher highs/lows):** the last two confirmed swing highs (via `last_n_confirmed_highs`, period=5) satisfy `SH_recent > SH_prior`, AND the last two confirmed swing lows satisfy `SL_recent > SL_prior`.
2. **Rising LWMA:** `LWMA_t > LWMA_{t−1}`.
3. **At support near the LWMA (mechanical touch tolerance):** `Low_t ≤ LWMA_t + 0.25 · ATR14_t` (the bar reached the LWMA zone) AND `Close_t > LWMA_t` (the bar closed back above it — support held). Tolerance `TOL = 0.25 · ATR14_t` on H4.
4. **Bullish PA signal — at least one of (exact inequalities; body_t = |C_t − O_t|, etc.):**
   a. **Bullish engulfing:** `C_t > O_t` AND `C_{t−1} < O_{t−1}` AND `O_t ≤ C_{t−1}` AND `C_t ≥ O_{t−1}`.
   b. **Bullish pin bar (hammer):** `C_t > O_t` AND `lower_wick_t = min(O_t, C_t) − Low_t ≥ 2 · body_t` AND `upper_wick_t = High_t − max(O_t, C_t) ≤ 0.5 · lower_wick_t` AND `(High_t − Low_t) ≥ 0.25 · ATR14_t` (bar must be material, not a doji-range artifact).
   c. **Bullish tweezer bottom:** `C_{t−1} < O_{t−1}` AND `C_t > O_t` AND `|Low_t − Low_{t−1}| ≤ 0.1 · ATR14_t`.
5. **MACD histogram rising AND above zero (conservative reading of "rising and preferably above zero"):** `hist_t > hist_{t−1}` AND `hist_t > 0`.

- **Entry type:** `market` (fill at open of H1-resolution bar following decision bar, per F1/F2).
- **Entry level:** n/a for market; all exit/stop geometry is anchored to `Close_t` (decision-bar close), NOT to the fill — see §6/§7 and §10 #6.
- **expires_after_bars:** null (market order; no pending lifecycle).

## 5. Entry — short
Full mirror of §4; the strategy is two-sided:

1. **Downtrend:** last two confirmed swing highs `SH_recent < SH_prior` AND last two confirmed swing lows `SL_recent < SL_prior`.
2. **Falling LWMA:** `LWMA_t < LWMA_{t−1}`.
3. **At resistance near the LWMA:** `High_t ≥ LWMA_t − 0.25 · ATR14_t` AND `Close_t < LWMA_t`.
4. **Bearish PA — at least one of:**
   a. **Bearish engulfing:** `C_t < O_t` AND `C_{t−1} > O_{t−1}` AND `O_t ≥ C_{t−1}` AND `C_t ≤ O_{t−1}`.
   b. **Bearish pin bar (shooting star):** `C_t < O_t` AND `upper_wick_t = High_t − max(O_t, C_t) ≥ 2 · body_t` AND `lower_wick_t = min(O_t, C_t) − Low_t ≤ 0.5 · upper_wick_t` AND `(High_t − Low_t) ≥ 0.25 · ATR14_t`.
   c. **Bearish tweezer top:** `C_{t−1} > O_{t−1}` AND `C_t < O_t` AND `|High_t − High_{t−1}| ≤ 0.1 · ATR14_t`.
5. **MACD:** `hist_t < hist_{t−1}` AND `hist_t < 0`.

Entry type `market`; entry level n/a; expires_after_bars null. Stop/TP mirrored in §6/§7.

## 6. Stop
- **Initial stop (exact formula):** long: `StopRule.price = Close_t − 100 · pip`. Short: `StopRule.price = Close_t + 100 · pip`. This is the CSV's fixed "Emergency SL 100 pips", anchored to the decision-bar close (fill-anchored is inexpressible — see §10 #6). `trail_atr_multiple = None` (static stop).
- **move_to_breakeven_on:** none. The source mentions no breakeven move.
- **trail:** none.
- The source's "expected loss ~60 pips or less on proper entries" is a description of typical outcomes, not a declared stop level; it is NOT implemented as a stop (see §10 #7).

## 7. Exit legs
Fractions sum to 1.0. TP distance uses the CSV's FIXED pair classification (not a computed ADR): high-ADR pairs {GBP_USD, EUR_JPY, GBP_JPY} → 75 pips; low-ADR pairs {EUR_USD, AUD_USD} → 50 pips.

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 0.5 | take_profit | long: `Close_t + D · pip`; short: `Close_t − D · pip`, where D = 75 for {GBP_USD, EUR_JPY, GBP_JPY}, 50 for {EUR_USD, AUD_USD} |
| TIME1 | 0.5 | time | `bars = 12` H4 bars (≈ 2 trading days) from the decision bar; proxy for the inexpressible "first H4 close on the opposite side of the entry candle" signal exit (see §10 #5) |

Rationale for the 0.5/0.5 split: contract v2 requires fractions to sum to 1.0, so a full-size TP leg cannot coexist with a fallback time leg; splitting 50/50 is the minimal symmetric distortion that preserves both exit channels. Whichever trigger fires first closes its half; the remainder rides to the other leg or the stop.

## 8. Filters
- **Trend filter (conditions §4.1 / §5.1):** H4 frame, knowable at the close of decision bar t (swing confirmation lag included — see §9).
- **LWMA slope filter (§4.2 / §5.2):** H4, knowable at close of t.
- **MACD histogram gate (§4.5 / §5.5):** H4, knowable at close of t.
- **Support/resistance proximity gate (§4.3 / §5.3):** H4, knowable at close of t.
- **No session, volatility-regime, spread, or news filters** are declared in the source and none are added. Costs are the engine's fixed model (F10: 1.0 pip spread + 0.5 pip entry slippage); no real spread series exists and none is proxied.
- **Concurrency (F12):** `max_concurrent_positions = 1` per (strategy, pair, granularity). Opposite-direction signals that fire while a position is open are emitted as intents but blocked by F12 at admission; they do NOT close or reverse the open position (no such mechanism exists in contract v2).

## 9. Causality audit
| Rule | Inputs | Fully knowable at |
|---|---|---|
| LWMA(20) value and slope | Closes of bars t−20 … t | Close of bar t |
| MACD(24,52,18) hist and its slope | Closes up to t (EMA recursion) | Close of bar t |
| ATR(14) | H/L/C of bars t−13 … t | Close of bar t |
| Swing highs/lows, period=5 | A swing high at bar k is confirmed only when 5 subsequent H4 bars fail to exceed it → **confirmation lag = 5 H4 bars (20 hours)**; knowable at close of bar k+5 | Close of bar t, using only swings confirmed at or before t |
| Trend condition (last 2 confirmed swings each side) | As above; the most recent usable swing occurred at least 5 H4 bars before t | Close of bar t |
| PA patterns (engulfing / pin bar / tweezers) | OHLC of bars t−1 and t only | Close of bar t |
| Support/resistance proximity | OHLC of bar t + LWMA_t + ATR_t | Close of bar t |
| Market entry fill | — | Open of the first bar after t (F1/F2); the strategy never assumes the fill price |
| Stop and TP levels | `Close_t` ± fixed pip distances | Close of bar t (declarable absolute values at OrderIntent creation) |
| TIME1 leg | Bar counter from decision bar | Deterministic |

No multi-timeframe context is used, so the §4 MTF close-before-use rule is not implicated. No centred windows, no `detect_swing_points`, no `shift(-1)`.

## 10. Ambiguities resolved
| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | "Majors" — the TP table names only 5 pairs; USD_JPY/USD_CAD are unclassified | Trade ONLY the 5 named pairs; USD_JPY/USD_CAD excluded (no TP distance declarable) | Treat all 7 majors as traded with a guessed 50- or 75-pip TP for USD_JPY/USD_CAD — invents parameters the author never stated |
| 2 | "MACD histogram rising and **preferably** above zero" | Require `hist_t > 0` (long) / `< 0` (short) — hard gate, fewer trades | Treat "above zero" as optional (slope only) — more trades, weaker momentum confirmation; also contradicts the row's own pseudocode `(h>h.shift())&(h>0)` |
| 3 | "at support **near** a rising 20 LWMA" — "near" is undefined | Touch tolerance `0.25 · ATR14` on H4 plus a close back on the trend side of the LWMA (support must have held on the decision bar) | Define support via last confirmed swing-low level — adds a second, correlated structure dependency and does not match the prose, which names the LWMA as the reference; rejected as less faithful |
| 4 | "Uptrend (higher highs/lows)" — over what window? | Last 2 confirmed swing highs AND last 2 confirmed swing lows, period=5 (causal_structure), each strictly rising | LWMA-slope-only proxy for trend — double-counts condition §4.2 and drops the structural HH/HL requirement, admitting shallower trends |
| 5 | "If TP not hit, exit on first H4 close on the opposite side of the entry candle" — a signal exit with no declarative mechanism | TIME leg: fraction 0.5, `bars = 12` H4 (≈2 trading days), paired 50/50 with the TP leg so fractions sum to 1.0 | (a) Drop the exit entirely — lets dead trades ride to the 100-pip emergency SL, mismeasuring the author's high-win-rate design; (b) model as stop-tightening — not sanctioned by the prose and StopRule has no such trigger. Residual mismatch: a real reversal close usually occurs within 1–3 bars, so the proxy holds losers longer — direction of error is **pessimistic** |
| 6 | Source measures SL/TP "from entry" (fill) | All geometry anchored to decision-bar `Close_t` (fill-anchored stops are inexpressible under decision-bar anchoring; this is not merely a conservatism choice). Realized R ≠ declared R when the t+1 open gaps; F3/F6 resolve fills honestly | Fill-anchored 100-pip SL / 50–75-pip TP — rejected as inexpressible in contract v2 |
| 7 | "Expected loss ~60 pips or less on proper entries" — is there a tighter tactical stop? | No tactical stop; only the declared 100-pip emergency SL (wider stop = worse fills = conservative) | Stop below the signal bar's low (~60 pips typical) — plausible live-trader reading but never stated as a rule; rejected |
| 8 | Tweezer "equal lows/highs" — exact equality never occurs in float prices | Equality tolerance `0.1 · ATR14` on H4 | Exact `Low_t == Low_{t−1}` — would fire ~never; rejected as degenerate rather than conservative |
| 9 | Entry timing after PA confirmation | Market entry at the next bar open (matches the row's pseudocode, which enters immediately on the signal bar's conditions) | `buy_stop` 1 pip above the signal-bar high with short expiry — arguably stricter, but adds a pending lifecycle the source never describes and can miss valid pullback entries; rejected |
| 10 | TIME1 `bars` counted in which frame | Bars counted in the primary H4 frame (12 × 4h = 48h); the H1-resolution engine maps this to 48 H1 bars internally | Counting in H1 simulation bars (12 H1 = 12h) — would cut the proxy exit to a quarter of the intended horizon; rejected |

**Residual multi-fill risk:** none. Entries are market orders only; there are no pending orders to overlap, so the F12 pending-fill gap is not implicated. F12 = 1 position caps concurrent positions; surplus intents while a position is open are simply unadmitted.

## 11. Expected behaviour
- **Trade frequency:** each entry requires 5 simultaneous conditions including a strict two-swing structural trend and a specific candle pattern within 0.25·ATR of the LWMA. Expect roughly 1–3 entries per pair per month → ~40–100 trades per pair over the ~20-year H4 history, ~120–300 trades across the 3 live pairs (plus EUR_JPY/GBP_JPY once Wave-1 backfill lands). Per-cell counts should clear low-confidence thresholds on long folds but may go thin in 6-month OOS windows.
- **Asymmetry warning:** declared reward:risk is 0.50–0.75R on the TP leg (50–75 pips vs a 100-pip stop), with the TIME1 leg's outcome uncontrolled. Breakeven needs a TP-leg win rate above ~57–67%. The source's own claim of "TP:SL roughly 1:1 to 1:1.5" contradicts its stated 50/75-pip TP vs 100-pip SL — the rules as written demand a genuinely high win rate, and the author's consistency claims are unbacktested.
- **What makes it fail the gates:** if the mechanized PA+structure checklist does not deliver ≥60% winners at sub-1R targets, expectancy goes negative; H1-resolution (vs native-bar) will sharpen the F5 stop-first penalty on the 50-pip-TP pairs where a 100-pip stop and 50-pip TP often sit inside a few H1 bars' combined range; weekend gap-throughs (F6) on the thin TIME1 remnants add tail losses.
- **Conviction check:** MODERATE is defensible as documented prose but NOT justified by the rules as written — the author documents no backtest, the R:R arithmetic is adverse by construction, and the strategy's viability rests entirely on the unverified high-win-rate assumption. Expect qualification only if the pullback-at-LWMA entry timing genuinely produces the claimed hit rate.
