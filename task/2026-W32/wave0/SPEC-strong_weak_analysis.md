# SPEC-strong_weak_analysis
**Source:** row 50 of forex_swing_strategies.csv · https://forums.babypips.com/t/trading-the-trend-with-strong-weak-analysis/77959
**Conviction (author's):** EXPERIMENTAL

## 1. Hypothesis

Currency strength differentials driven by diverging central-bank policy, growth expectations, and the resulting institutional capital re-allocation persist for weeks to months, because large allocators cannot re-weight portfolios in a single session and because macro regimes change slowly. Ranking the 8 major currencies by recent relative performance and concentrating exposure in the single pair that combines the strongest currency against the weakest maximises the exploited differential per trade, while a D1 trend filter and entries at structural support/resistance avoid buying exhaustion. **The entire edge claim rests on a proprietary strength formula that the author never disclosed; this spec implements the CSV pseudocode's reconstruction and the backtest verdict applies to that reconstruction, not to the author's method (see §10 #1).**

## 2. Scope

- **primary_granularity:** D1 (all decisions on closed D1 bars; source: "D1 (trades held days to months)")
- **context_granularities:** none — every input is computed on the D1 frame
- **simulate_on:** H1 (fills/stops/legs resolved on H1 bars per contract §5)
- **pairs_requested (verbatim):** "All 28 pairs from 8 majors (trade strongest currency vs weakest)"
- **pairs_available (13):** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions; harness skips pairs with insufficient history). These 13 instruments touch all 8 majors (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF), but thinly for CHF (1 cross: USD_CHF) and NZD (2 crosses).
- **pairs_missing (15 of the 28-cross matrix):** AUD_CAD, AUD_CHF, AUD_JPY, CAD_CHF, CAD_JPY, CHF_JPY, EUR_CHF, EUR_NZD, GBP_AUD, GBP_CAD, GBP_CHF, GBP_NZD, NZD_CAD, NZD_CHF, NZD_JPY → see **DATA-GAP-strong_weak_analysis.md**. These are missing from both roles: as inputs to the per-currency strength sums and as candidate tradeable instruments.

## 3. Indicators

All series computed per pair on D1 bars, evaluated at decision bar *t* (a closed bar).

| Indicator | Params | Source |
|---|---|---|
| Simple moving average of close | period=50 | inventory `sma` |
| Average True Range | period=14 | inventory `atr` |
| Rolling z-score | period=20 | inventory `zscore` (rolling, causal) |
| 20-bar return | `ret20_p(t) = Close_p(t) / Close_p(t−20) − 1` | private — trivial transform, not in inventory; specified here fully |
| Per-currency strength | formula below | private — reconstruction of the proprietary formula; specified here fully |
| Confirmed swing points | period=5 | `causal_structure.confirmed_swing_points` (occurrence at *k*, knowable at *k+5*) |

**Private strength reconstruction (exact):**
1. Tradeable universe U = the 13 available pairs. Currency set C = {USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF}.
2. For each pair p in U compute `z_p(t) = zscore(ret20_p, period=20)(t)` — i.e. `(ret20_p(t) − mean(ret20_p[t−19..t])) / std(ret20_p[t−19..t])`, sample std, requiring the full 20-value window (first valid at the 40th D1 bar of history).
3. Orient per currency c: for each pair p containing c, `contrib_{p→c}(t) = z_p(t)` if c is the **base** of p, else `−z_p(t)`.
4. `strength_c(t) = Σ contrib_{p→c}(t)` over all pairs p ∈ U containing c. A currency with **zero** available crosses at *t* (data outage) is excluded from that bar's ranking; a currency with exactly one cross is retained (CHF's normal state) — see §10 #7.
5. `best(t) = argmax_c strength_c(t)`; `worst(t) = argmin_c strength_c(t)`. Ties broken by alphabetical currency code (deterministic; ties are measure-zero in practice).
6. Candidate instrument: the unique pair in U whose two currencies are {best(t), worst(t)}. If no such instrument exists in U, **no signal this bar** (no synthetic USD-leg construction — §10 #4).

## 4. Entry — long

At the close of D1 decision bar *t*, all conditions must hold:

1. Candidate instrument P exists in U for {best(t), worst(t)} and **best(t) is the base of P**.
2. Trend filter: `Close_P(t) > sma50_P(t)`.
3. Structure: let S = level of the most recent confirmed D1 swing low on P (`confirmed_swing_points`, period=5) whose confirmation bar ≤ t and whose occurrence bar k satisfies `k ≥ t − 60` (staleness guard, §10 #6). At least one such swing low must exist.
4. Pullback: `Low_P(t) ≤ S + 0.25 × atr14_P(t)` **and** `Close_P(t) > S` (bar dipped into the support zone and closed above it — both knowable at the close of *t*).

- **Entry type:** `market`
- **Entry level:** n/a (fills at open of first H1 bar after the D1 close, per F1/F2)
- **expires_after_bars:** null (market intent, never pending)
- **Stop / exits:** as §6–§7, anchored to decision-bar values (S, atr14_P(t)).
- Re-emission: conditions may hold on consecutive D1 bars and the strategy cannot observe its own open position; `max_concurrent_positions = 1` (F12, §3.2 step 6) blocks admission of a second intent on P while one is open. No pending orders exist in this strategy, so the no-OCO/no-cancel lifecycle problem does not arise (fleet rule 7 satisfied by construction).

## 5. Entry — short

Mirror of §4 (this is exactly the CSV's "go short the pair combining the weakest base against the strongest quote"):

1. Candidate instrument P exists in U for {best(t), worst(t)} and **worst(t) is the base of P** (equivalently best(t) is the quote).
2. Trend filter: `Close_P(t) < sma50_P(t)`.
3. Structure: R = level of the most recent confirmed D1 swing **high** on P (period=5, confirmation ≤ t, occurrence `k ≥ t − 60`).
4. Pullback: `High_P(t) ≥ R − 0.25 × atr14_P(t)` **and** `Close_P(t) < R`.

Entry type `market`, expires_after_bars null. Note §4 and §5 are mutually exclusive per bar (best ≠ worst), so at most one intent per decision bar across the whole strategy.

## 6. Stop

- **Initial stop (long):** `stop = S − 1.0 × atr14_P(t)` where S is the swing-low level from §4.3 and atr14 is the D1 ATR at decision bar *t* — both knowable at emission (decision-bar anchoring, fleet rule 8; the source's "risk from the entry" reading is rejected as inexpressible, §10 #5).
- **Initial stop (short):** `stop = R + 1.0 × atr14_P(t)`.
- **move_to_breakeven_on:** none
- **trail (StopRule.trail_atr_multiple):** none — trailing is expressed as the exit leg in §7 (single trailing mechanism; stacking both would be redundant).

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|--:|---|---|
| TRAIL | 1.0 | trailing | atr_multiple = 3.0 (engine-computed trail on the resolution frame per F9; initial trail anchor is the §6 stop — the trail only improves it) |

Fractions sum to 1.0. There is **no take-profit** — the source is a hold-for-weeks-to-months trend ride. The source's actual exit ("trend ends / rank reversal") is a **signal exit and is inexpressible in contract v2** (exits are take_profit | trailing | time only); the 3×ATR trail is the expressible proxy for "trend termination". The fidelity loss is material and recorded in §10 #3. No time leg: the source holds for months and a time cap would fabricate a rule; open trades at fold end close END_OF_DATA per F11 and are flagged.

## 8. Filters

| Filter | Rule | Timeframe | Knowable when |
|---|---|---|---|
| Trend (direction gate) | Long only if Close > sma50; short only if Close < sma50 | D1 | At close of decision bar *t* |
| Strength-rank gate | Trade only the single {best, worst} instrument; no instrument in U → flat | D1 | At close of *t* (all inputs are D1 closes ≤ t) |
| Structural entry gate | Pullback to most recent confirmed swing level | D1 | At close of *t*; swing level itself knowable since its confirmation bar (occurrence + 5 bars) |
| Over-concentration | Source: "avoids over-concentration on correlated strength themes". **Not expressible** — contract v2 has no cross-pair concurrency cap. Partial mitigation by construction: exactly one candidate instrument per decision bar, and F12 caps 1 position per (strategy, pair). Two positions in correlated pairs (e.g. yesterday's EUR_USD still open, today's GBP_JPY emitted) CAN coexist. Recorded in §10 #8; not a data proxy. | — | — |

No session, volatility, news, or calendar gates exist in the source, and no non-price data is used. The engine's standard cost model (1.0-pip spread, 0.5-pip entry slippage, F10) is the only execution assumption; no real-spread series exists or is proxied.

## 9. Causality audit

| Rule | Inputs | Fully known at |
|---|---|---|
| ret20_p(t) | D1 closes of pair p at t−20..t | close of bar t |
| z_p(t) | ret20_p at t−19..t ⇒ closes t−39..t | close of bar t |
| strength_c(t), best/worst | z_p(t) across U | close of bar t |
| sma50_P(t) | D1 closes t−49..t | close of bar t |
| atr14_P(t) | D1 OHLC t−13..t | close of bar t |
| Swing low/high level S/R | occurrence bar k, **confirmation lag = 5 bars** (`confirmed_swing_points`, period=5): knowable from k+5 onward; spec requires k+5 ≤ t | close of bar t (level itself set at k) |
| Pullback condition | Low/High/Close of bar t only | close of bar t |
| Entry fill | — | first H1 bar after the D1 close (F1/F2) — never on bar t |
| Stop price | S/R and atr14 at t | declared at OrderIntent creation, bar t close |
| Trailing leg | engine ATR on resolution bars, updated at bar close (F9), never widens | each H1 bar close after entry |
| MTF rule | decisions on D1, fills on H1: the D1 bar stamped at its open is acted on only after it closes (contract §4); the strategy never reads H1 data | — |

**Confirmation-lag statement (mandatory):** the only swing/pivot structure in this strategy is `causal_structure.confirmed_swing_points` with period=5: a swing low occurring at D1 bar k is used from bar k+5 onward, with the level recorded at k. The banned `detect_swing_points` is not used.

**Cross-pair alignment:** D1 bars of different pairs share UTC open-stamps (21:00Z) but individual pairs can miss bars (rare holidays/outages). Alignment rule: for pair p at bar t, use the close at the exact stamp t if present, else the most recent prior close at most **2** D1 bars stale; if none exists within 2 bars, that pair is dropped from the strength sums at t (and cannot be the trade instrument at t). Under this rule every input still reflects only information available at the close of t — a stale close is old information, not future information.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | **The strength formula is proprietary and undisclosed** — the entire edge claim rests on it | Adopt the CSV pseudocode's reconstruction verbatim-mechanized: per-pair time-series `zscore(pct_change(close,20))` (rolling 20-bar window, inventory default) summed over each currency's crosses | (a) Declaring the strategy unimplementable — discards a testable skeleton the CSV itself supplies; (b) cross-sectional z-score across the 8 currencies per bar — equally plausible, different numbers, not what the pseudocode says. **Flag: the backtest validates the reconstruction, not the author's claimed 3-year track record** |
| 2 | "Low-risk technical entries (double bottoms, cleared resistance)" — a discretionary overlay | Mechanized as: pullback of the decision bar into ±0.25×ATR of the most recent confirmed D1 swing level, close back outside it, then **market** entry (later entry, worse fill than a resting limit) | (a) Dropping the overlay entirely (pure strength+trend market entry — more trades, less faithful to "low-risk entries"); (b) `buy_limit`/`sell_limit` resting at the swing level — fills at the level exactly with no price improvement modelled, i.e. a *better* fill than a discretionary trader achieves; less conservative |
| 3 | Exit "when trend ends / rank reversal" — a signal exit | 3.0×ATR trailing leg (only expressible trend-termination proxy); stop never widens (F9) | Rank-flip or SMA50-cross exit orders — **inexpressible in contract v2** (ExitLeg kinds are take_profit/trailing/time; the strategy cannot emit exit-on-condition orders). Fidelity loss is material for a hold-weeks-to-months system and is stated here rather than hidden |
| 4 | Best/worst combination with no instrument in U (e.g. best=NZD, worst=CAD → NZD_CAD missing) | Skip the bar; no trade | Synthesising the position via two USD legs (long NZD_USD + short USD_CAD) — doubles spread/slippage costs, changes the risk profile, and exceeds the one-instrument OrderIntent model |
| 5 | Stop distance measured from the (unknowable) fill price | Anchored to decision-bar values: stop = S/R ∓ 1.0×ATR14(t), an absolute price declarable at emission | Fill-anchored stop/R measurement — inexpressible for `market` entries (fleet rule 8); realized R ≠ declared 1R when the fill gaps, which F3/F6 resolve honestly |
| 6 | Age of the swing level used as support/resistance | Staleness guard: occurrence bar k ≥ t−60 (≈3 months of D1 bars) | No guard — a 2-year-old swing level would qualify as "support", which is not what a discretionary trader means |
| 7 | Currency coverage is thin (CHF has 1 cross, NZD 2, until the DATA-GAP is filled) | Strength = sum over available crosses only, min 1 cross, no normalisation by cross count | (a) Excluding thin currencies (changes the universe vs the author's 8); (b) mean instead of sum — reweights thin currencies *up* relative to the author's equal-sum idea. Known bias: CHF's rank is driven entirely by USD_CHF until the missing crosses land — flagged in the DATA-GAP |
| 8 | "Avoids over-concentration on correlated strength themes" | Only the by-construction mitigation (one candidate instrument per bar; F12 = 1 position per pair) | A cross-pair exposure cap — inexpressible in contract v2 (no portfolio-level order gating); recorded as residual risk: two correlated positions can coexist, direction of bias = larger effective exposure than the author intends |
| 9 | Re-emission on consecutive bars while a position is open | Emit on every qualifying bar; F12 (max_concurrent_positions=1) blocks admission while a position is open; no pendings exist, so no multi-fill risk | Suppress-after-signal state machines — the strategy cannot observe fills/positions (declarative contract), so any such rule would be unimplementable |

## 11. Expected behaviour

- **Trade frequency:** low. The {best, worst} pair at 20-day horizon turns over every few weeks at most; the trend + pullback-to-structure gates cut that further. Expect roughly **4–15 entries per year** across the whole universe, with holds of weeks to months (trail at 3×ATR on D1 scale). Walk-forward folds (36mo train / 6mo OOS) will see single-digit to low-double-digit trades per OOS window — per-cell `low_confidence` flags are likely, and that is arithmetic, not a bug.
- **What would make it fail the gates:** (a) the reconstructed strength formula not capturing whatever the proprietary formula captures — the single largest risk, by construction unmeasurable here; (b) the 3×ATR trail strangling trends the author would have held (or holding through rank reversals the author would have exited); (c) degraded rankings from the 15 missing crosses, especially for CHF/NZD, until the DATA-GAP is resolved; (d) weekend-gap losses through the wide stop (F6) on a strategy with few trades — one bad gap can dominate a fold.
- **Is the author's EXPERIMENTAL conviction justified by the rules as written?** Yes — arguably generous. The mechanism (persistent macro-driven currency momentum differentials) is economically plausible and matches the published currency-momentum literature, but the undisclosed formula, the discretionary entry overlay, and the signal-based exit are all replaced here by reconstructions/proxies. What this backtest measures is a *specific mechanical relative-strength trend follower inspired by* Dennis3450, not the author's method; the report must say exactly that.
