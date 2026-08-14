# SPEC-double_bottom_measured_move

**Source:** row 47 of forex_swing_strategies.csv · https://tradeciety.com/bottom-fishing-trading-how-to-find-reversals
**Conviction (author's):** MODERATE

## 1. Hypothesis

A double bottom in which the second low holds meaningfully above the first — but not so far above that the market never really retested it — is the footprint of sellers failing twice at roughly the same level: the first flush found committed buyers, and the retest demonstrated that supply at that zone is exhausted rather than merely paused. When price then closes above the intervening reaction high, the last cohort of shorts is underwater and must cover while sidelined breakout buyers chase, producing a self-reinforcing repricing toward the measured-move objective (the pattern height projected upward — the distance bears forced price down, refunded). The edge should persist because it rests on a behavioural asymmetry (trapped sellers + failed retest = one-sided order flow at a known reference level) rather than on a fitted parameter, and because the 5–20% offset window specifically selects the retests that are shallow enough to show seller weakness yet deep enough to be a genuine test.

## 2. Scope

- **primary_granularity:** D1 (source: "D1 (swing; examples GBP/JPY and AUD/CAD daily)")
- **context_granularities:** none (the source defines no higher-timeframe trend filter; adding one would be an invented rule — §10 #9)
- **simulate_on:** H1 (contract v2 §5: decisions on the D1 frame only, fills resolved on H1 bars; run both ways and report the delta)
- **pairs_requested (verbatim):** "FX pairs - majors and crosses (GBP/JPY|AUD/CAD examples on page)"
- **pairs_available:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD (live); GBP_JPY, EUR_JPY, NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD (**pending** — Wave-1 additions; harness skips pairs with insufficient history rather than failing). GBP_JPY — one of the two documented example pairs — is covered by the Wave-1 batch.
- **pairs_missing:** **AUD_CAD** — the second documented example pair. It is absent from the 5 live pairs AND absent from the 8 Wave-1 additions → genuine gap, see `DATA-GAP-double_bottom_measured_move.md`. All other "majors and crosses" language maps to the 13-pair universe per CONTRACT Part F.

**D1 primary, no alternatives offered:** the source is explicitly daily-swing; the worked examples are daily charts; and the pattern (decline → two confirmed swing lows + intervening high → breakout close) needs D1-scale swings for the 5–20% offset to be meaningful. No H4 variant is specified — inventing one would be a different strategy.

## 3. Indicators

All computed on the D1 decision frame. `t` = decision bar (a closed bar). Occurrence bars are denoted k; a swing occurring at k is knowable at k+5.

| Indicator | Params | Source |
|---|---|---|
| Confirmed swing highs/lows | `confirmed_swing_points(high, low, period=5)`; swing at occurrence bar k stamped at confirmation bar k+5, carrying the level set at k | `causal_structure.confirmed_swing_points` — **mandatory substitute** for the CSV pseudocode's `scipy.argrelextrema(order=10)`, a CENTERED extremum detector (10 bars each side), the same look-ahead class as banned `detect_swing_points`. Substitution recorded §10 #1. |
| ATR | `atr(High, Low, Close, period=14)` — Wilder, completed bars only | `indicators.atr` |
| Pip conventions (stop buffer) | `get_pip_value(pair)` / `calculate_pips(...)` | `indicators` (inventory) |
| Pattern geometry — A / C / B levels, height, offset, windows (private, fully specified in §4–§5; NOT added to shared inventory) | For candidate A at kA: `LA = Low[kA]`; decline gate over `High[kA-10..kA-1]`; C = the unique swing high in (kA, kB), `LC = High[kC]`, `H = LC − LA`; B at kB: `LB = Low[kB]`; offset `(LB − LA)/H`. All inputs knowable at activation bar s = kB+5. | private, defined in this spec (§10 #1, #3, #5) |

No other indicators. No EMA/ADX/session/volume/news gates — none are in the source ("OHLCV only (swing-point pattern recognition)") and no non-price feeds exist anyway (DATA_AVAILABILITY).

## 4. Entry — long

**Definitions.** A candidate pattern is scanned from confirmed swings only. For a swing low occurring at bar kA (confirmed at kA+5), `LA = Low[kA]`.

**Setup qualification** — evaluated once, at the activation bar s = kB+5 (every input below is knowable at s; kB > kC > kA by construction):

1. **A is a confirmed swing low** at occurrence bar kA (period=5; knowable at kA+5 ≤ s).
2. **Decline gate ("after a decline"):** `max(High[kA−10 .. kA−1]) − LA ≥ 1.5 × ATR14[kA]` (ATR14 evaluated at kA; knowable at s). Mechanization of "after a decline" — §10 #2.
3. **Exactly one confirmed swing high occurs in the open interval (kA, kB);** that is C, occurrence kC, `LC = High[kC]`. If zero or ≥2 swing highs occur between A and B, no pattern (pattern-purity gate — §10 #5).
4. **Minimum height:** `H = LC − LA ≥ 1.0 × ATR14[kC]` (excludes flat noise patterns; conservative filter — §10 #3).
5. **B is the FIRST confirmed swing low occurring after kC** (the second bottom; if this first post-C swing low fails condition 6, the pattern is dead — no scanning forward for a better B — §10 #4).
6. **Offset window (exact):** `LB > LA` AND `0.05 ≤ (LB − LA) / H ≤ 0.20` — bounds inclusive, matching the pseudocode's `>= 0.05` / `<= 0.20`.
7. **Formation integrity:** `min(Low[kA+1 .. kB]) ≥ LA` — price never traded below A while the pattern formed (§10 #6).
8. **Formation window:** `kB − kA ≤ 40` D1 bars (source is silent; declared conservative bound — §10 #7).

**Trigger** — evaluated at the close of each decision bar t with s ≤ t ≤ s+19 (20-bar trigger window from activation; §10 #8):

9. **No invalidation since activation:** `min(Low[s .. t]) ≥ LA` — if any completed bar since activation has traded below A, the setup is cancelled (the source's own "SL below A cancels the pattern if violated", applied pre-entry).
10. **Level break:** `Close[t] > LC` (strict).
11. **First signal only:** t is the FIRST bar of the trigger window on which conditions 9–10 hold; the setup is then consumed (no re-emission from the same pattern — §10 #11).

- **entry type:** `market` (the source trigger is the *close* of the candle closing above C; OrderIntent emitted at decision_bar = t, fills at the open of t+1 per F1/F2 — §10 #10).
- **entry level:** n/a for market. All stop/TP geometry is anchored to prices knowable at decision bar t: `LA`, `LC`, `H` are frozen at s ≤ t; the realized fill gap is resolved honestly by F2/F6 and realized R ≠ declared R when the fill gaps (fleet rule 8).
- **expires_after_bars:** null (market order — no pending lifetime exists).

## 5. Entry — short

**Symmetric adaptation.** The source article is a bottom-fishing (long) method; the CSV's `entry_logic_short` field documents the short side as the symmetric adaptation of the W rule ("double top with second peak 5-20% lower than first"). Both sides are kept, as the CSV documents them; the short side is an adaptation, recorded here and §10 #12.

Mirror of §4. Candidate A′ = confirmed swing high at kA′, `LA′ = High[kA′]`; activation s = kB′+5:

1. A′ is a confirmed swing high (period=5).
2. **Advance gate:** `LA′ − min(Low[kA′−10 .. kA′−1]) ≥ 1.5 × ATR14[kA′]`.
3. Exactly one confirmed swing low occurs in (kA′, kB′): C′ at kC′, `LC′ = Low[kC′]`.
4. `H′ = LA′ − LC′ ≥ 1.0 × ATR14[kC′]`.
5. B′ is the FIRST confirmed swing high occurring after kC′.
6. `LB′ < LA′` AND `0.05 ≤ (LA′ − LB′) / H′ ≤ 0.20` (bounds inclusive).
7. `max(High[kA′+1 .. kB′]) ≤ LA′`.
8. `kB′ − kA′ ≤ 40`.

Trigger, s ≤ t ≤ s+19: no completed bar since activation with `High > LA′` (else cancelled); `Close[t] < LC′` (strict); first qualifying bar consumes the setup.

Entry type `market`, expires_after_bars null, geometry anchored to decision-bar-knowable prices as in §4.

## 6. Stop

- **Initial stop (long):** `stop = LA − 1.0 pip`, where LA is the pattern low A and 1.0 pip uses `get_pip_value(pair)` conventions. **(short):** `stop = LA′ + 1.0 pip`.
  This is the **wider** of the source's two readings ("SL below A (invalidation) or tighter below B"). Wider stop ⇒ same pip reward ÷ larger initial risk ⇒ smaller reported winner r-multiples — the conservative direction for gate-reported performance. The below-B variant is rejected and recorded (§10 #13). The 1.0-pip buffer mechanizes "below"; it coincidentally equals the cost-model spread and is flagged (§10 #14).
  Validation: for longs, entry ≈ Close[t] > LC > LA > stop — stop strictly below entry by construction; absolute price declarable at OrderIntent creation (LA frozen at s ≤ t).
- **move_to_breakeven_on:** none (single take-profit leg; nothing to trigger it — and the source's "raise SL toward B/breakeven at the 100% target zone" is post-fill management, inexpressible in the declarative contract and moot under a single leg placed at exactly 100% — §10 #15).
- **trail:** none.

## 7. Exit legs

| Label | Fraction | Kind | Level formula |
|---|---|---|---|
| TP1 | 1.0 | take_profit | long: `price = LC + 1.00 × H = 2·LC − LA` · short: `price = LC′ − 1.00 × H′ = 2·LC′ − LA′` |

Fractions sum to 1.0. One leg, full position — the source's measured-move objective taken at the documented **100%** multiple. The "75% multiple acceptable" variant is rejected and recorded (§10 #16): a lower target fills more often and flatters hit rate; the documented primary rule is 100%. F11 handles end-of-data.

## 8. Filters

| Filter | Timeframe | When knowable |
|---|---|---|
| Decline/advance gate (§4 #2, §5 #2) — the only trend-context condition in the strategy; enforces that the pattern corrects a real move | D1 | inputs complete at kA−1 / kA′−1; evaluated at activation s |
| Pattern-quality gates: height ≥ 1.0×ATR, offset ∈ [5%, 20%], single-intervening-swing purity, formation integrity, 40-bar formation window | D1 | activation bar s = kB+5 (every input is a completed swing or bar by then) |
| Pre-entry invalidation (no trade below A / above A′ since activation) | D1 | close of each decision bar t (completed-bar Low/High) |
| Session/news/calendar filters | — | **None exist in the source and no such data exists** (DATA_AVAILABILITY: no calendar, no news, no rates). No proxy substituted. |

No volatility/session gates beyond the above. The 1.0-pip stop buffer uses the pip-convention helper; the mandated F10 cost model (1.0-pip spread, 0.5-pip entry slippage) is applied by the engine, not the strategy. Note for reporting: real GBP/JPY retail spreads are typically 1.5–3 pips vs the modelled 1.0 — against D1-scale stops (often 100+ pips) this bias is small but must be stated for JPY crosses.

## 9. Causality audit

| Rule | Inputs fully known at | Confirmation lag |
|---|---|---|
| Swing detection (A, C, B — all pattern points) | A swing extreme occurring at bar k is knowable only at **k+5** (period=5 subsequent bars failing to exceed/undercut it). All pattern points come from `causal_structure.confirmed_swing_points(period=5)`. The CSV pseudocode's `argrelextrema(order=10)` — knowable only with 10 FUTURE bars, i.e. look-ahead at k — is **replaced**; this is a mandatory substitution (§10 #1). | 5 D1 bars |
| A level LA / decline gate (High[kA−10..kA−1], ATR14[kA]) | Knowable at kA; evaluated at s. | 5 bars (via kA), consumed at s |
| C level LC, uniqueness count in (kA, kB) | kC < kB ⇒ confirmed at kC+5 < s; the count over (kA, kB) is final once B is confirmed, since any swing occurring ≤ kB is confirmed by kB+5 = s. | 5 bars (via kC/kB) |
| B level LB, offset test, formation integrity `min(Low[kA+1..kB])` | All knowable exactly at **s = kB+5** — B's own confirmation bar. The setup cannot activate before s even though B's *level* was set at kB; acting at s on the level set at kB is the legitimate causal reading (contract §6). | 5 bars (dominant lag of the pattern) |
| Height gate ATR14[kC] | Close of kC; evaluated at s. | consumed at s |
| Trigger `Close[t] > LC` (t ≥ s) and pre-entry invalidation (`Low[s..t]` vs LA) | Close of bar t — completed-bar data only. The trigger can legitimately fire ON the activation bar s itself if Close[s] > LC (fully knowable at s's close). | 0 beyond activation |
| Entry fill | OrderIntent emitted at decision_bar t; eligible from t+1 (F1); market fill at open of t+1 (F2). | 1 bar execution lag |
| Stop and TP | Absolute prices (`LA ∓ 1.0 pip`, `2·LC − LA`) declarable at OrderIntent creation; LA, LC frozen at s ≤ t. Stops never move (no trail, no breakeven). | 0 |
| MTF | None — single decision frame (D1); simulate_on H1 is fill *resolution* only; the strategy never sees H1 data (contract §5), so no MTF alignment rule is invoked. D1 bars are stamped at their open and are used only after their close. | n/a |

No rule reads bar t+1 or later at decision time; no centered windows anywhere; the strategy never observes fills, P&L, or pending state.

## 10. Ambiguities resolved

| # | Ambiguity | Conservative reading taken | Alternative rejected |
|---|---|---|---|
| 1 | CSV pseudocode finds pattern points with `scipy.argrelextrema(order=10)` — a CENTERED detector needing 10 bars on EACH side: at bar k it reads k+10, the same look-ahead class as banned `detect_swing_points` | `causal_structure.confirmed_swing_points(period=5)`; patterns act from k+5 onward using the level set at k. **Mandatory substitution, explicitly recorded.** Period=5 follows the assignment directive and the fleet-standard confirmation lag; the trade-count inflation vs the source's order=10 is bounded by the downstream gates (offset window, purity, height) that most period-5 candidates fail. | (a) Literal `argrelextrema` semantics — rejected: look-ahead; contaminated the only production strategy (INDICATOR_INVENTORY). (b) period=10 (the literal source parameter, fewer/later patterns — the MORE conservative trade-count direction) — recorded, not taken: the assignment fixes period=5 for fleet uniformity. |
| 2 | "After a decline" is qualitative | Mechanized: `max(High[kA−10..kA−1]) − LA ≥ 1.5 × ATR14[kA]` (mirror for shorts). A genuine prior leg down of ≥1.5 ATR over the 10 bars into A; evaluated only at s, costs no look-ahead. | No decline gate (literal minimal reading) — rejected: admits flat-range "double bottoms", more trades, less faithful to the reversal premise. |
| 3 | "Rally to swing high C" — any height qualifies? | Require `H = LC − LA ≥ 1.0 × ATR14[kC]` so the pattern has meaningful scale relative to volatility. Fewer, larger patterns — conservative. | No minimum height — rejected: micro-patterns on quiet D1 stretches produce coin-flip breakouts with tiny geometry; an invented-free reading but noise-dominated. |
| 4 | Which low is "the second low B" if several swing lows form after C? | B = the FIRST confirmed swing low occurring after kC; if it fails the 5–20% offset, the pattern is dead. | Scan forward for a later swing low that satisfies the offset — rejected: cherry-picking the qualifier = selection ambiguity and more trades. |
| 5 | Which high is C if multiple swing highs occur between A and B? | Require EXACTLY ONE swing high in (kA, kB) — pattern purity; that high is C. Fully knowable at s (every swing occurring ≤ kB is confirmed by s). | (a) "Last swing high before B" and (b) "highest high between A and B" — rejected: both legitimize multi-peak messes the article would not draw as a W, and (b) can silently promote a stale high as the trigger level. |
| 6 | May price dip below A while the pattern forms (between kA and kB)? | No: `min(Low[kA+1..kB]) ≥ LA` required, and post-activation any completed-bar Low < LA cancels the setup (source: "SL below A cancels the pattern if violated"). Fewer patterns — conservative. | Literal pseudocode reading (offset constrains only the swing-low B itself; intervening pokes below A allowed) — rejected: keeps patterns the article calls failed; more trades. |
| 7 | B's validity window — how many bars after A may B form? Source is silent. | `kB − kA ≤ 40` D1 bars (~2 months) — a declared bound, on the tighter side of typical daily W formations. | Unbounded — rejected: stale A-levels anchor patterns months later; more trades from a meaningless level. |
| 8 | Trigger window — how long after activation may the breakout close occur? Source is silent. | 20 D1 bars from activation (s … s+19); then the setup expires. | Unbounded ("until invalidated below A") — rejected: entries months after the retest on a decayed level; more trades. |
| 9 | Higher-timeframe trend context? | None added — the source defines none and the pattern IS the trend-reversal signal; adding a W1/EMA gate would be an invented rule. | W1 or D1-EMA regime gate — rejected: zero source support, untraceable flattery, plus needless MTF surface. |
| 10 | "Enter LONG at the close of the candle that closes above C" — market-on-close vs resting buy stop | `market` emitted at the close of the qualifying bar (fills open t+1, F1/F2). This is the source text literally, and is the later/conservative fill: a resting buy_stop at LC+ε would fill intrabar on a touch, earlier and without the close confirmation the rule demands. | `buy_stop` at LC + buffer emitted at activation — rejected: earlier fills, admits intrabar pokes that close back below C (false breakouts the close-filter exists to exclude), and adds pending-order lifecycle surface for no source support. |
| 11 | Pseudocode signal can re-fire across bars (`cond.shift(1) & (close > C)`) | First qualifying close consumes the setup (§4 #11). Fewer entries; deterministic rather than dependent on engine concurrency state. | Re-emit every qualifying bar — rejected: admission then depends on F12 concurrency state, an implicit channel the declarative contract forbids relying on. |
| 12 | The article is long-only bottom-fishing; the CSV documents a symmetric short | Both sides implemented; the short is flagged as the CSV's documented symmetric adaptation (§5), not an invented rule and not the article's own text. | Long-only — rejected: the CSV row (the source of record for this build) specifies the short; dropping it halves the sample. |
| 13 | "SL below A (invalidation) **or tighter below B**" — two widths | **Below A** (wider). R-multiple direction: wider stop ⇒ smaller reported winner r-multiples — conservative for gates. Also matches the source's own invalidation language ("SL below A cancels the pattern"). | Below B (tighter) — rejected for the declared rule: inflates winner r-multiples; recorded as a sensitivity reviewers may rerun. |
| 14 | "Below A" implies a buffer of unspecified size | 1.0 pip, matching the cost-model spread scale (F10); fixed, pair-adjusted via pip conventions. **Flag:** convention proxy, not source data. | 0.1×ATR buffer — rejected: a second invented parameter where a fixed pip suffices. |
| 15 | "Once price reaches 100% target zone raise SL toward B/breakeven" | **Dropped — inexpressible.** The declarative contract has no channel to observe price relative to fill and re-declare stops mid-trade, and under the single TP leg placed at exactly the 100% objective the rule is moot (reaching the zone ≈ TP fill). Recorded, not approximated. | Modelling it as `move_to_breakeven_on` TP1 — rejected: F8 moves the stop only AFTER the sole leg fills (i.e., on a flat book) — a no-op masquerading as fidelity. |
| 16 | "TP = C + 100% of (C−A); 75% multiple acceptable" | **100%** as documented. A lower target would raise hit rate and flatter the win-rate column; taking the documented primary rule yields the lower hit rate / harsher expectancy estimate — the conservative gate-reporting direction per the assignment. | 75% multiple — rejected: softer test than the documented rule; recorded as a sensitivity. |
| 17 | Structural note, resolved here so no implementer rediscovers it: with entry at a close strictly above C and stop below A, declared RR = (TP−entry)/(entry−stop) is **necessarily < 1** (reward < H, risk > H). | Kept as-is — this IS the documented geometry; no re-anchoring of TP/SL to manufacture RR ≥ 1. The expectancy burden (win rate > 50%) is the strategy's own claim to test. | Anchoring entry at C exactly (ignoring the close-above premium) — rejected: misstates realized geometry and inflates declared R; F2/F6 resolve the fill honestly. |

## 11. Expected behaviour

- **Trade frequency:** the gate stack is strict — confirmed W with exactly one intervening swing high, first-post-C low landing in a 15%-of-height offset band, ≥1.5×ATR prior decline, ≥1×ATR height, 40-bar formation and 20-bar trigger windows, first-signal-only. Expect roughly **1–3 trades per pair per year** on D1 (a qualifying double bottom/top is a several-times-a-year event at best, and the offset band discards most of them). Across 13 pairs: ~15–40 trades/year system-wide; per-cell (pair × D1) 10-year counts of ~10–30 trades — many cells will carry `low_confidence`; the pooled verdict is the meaningful one and even pooled 10-year samples (~150–400 trades) must be read with per-cell dispersion (contract §8).
- **Likely failure modes at the gates:** (a) **structural RR < 1** (§10 #17) — every winner pays less than 1R while every loser costs ~1R+, so the strategy must win materially more than 50% to post positive expectancy; measured-move folklore claims exactly that, but it is the claim under test, not a given; (b) the 5-bar confirmation lag means B is known only after price has already left the second low — breakouts that run immediately are entered near the trigger window's edge with slippage, or missed (conservative by construction, but it caps win rate); (c) weekend gaps through the wide below-A stop fill at open (F6) producing losses > 1R on a wide D1 base; (d) F5 at H1 resolution: H1 bars spanning both the (far) TP and the (near) stop resolve stop-first — with TP ≈ 2×H away this is rare but pessimistic when it occurs; (e) JPY-cross cost understatement (§8) slightly flatters GBP_JPY results.
- **Is the author's MODERATE conviction justified by the rules as written?** Yes — and MODERATE is if anything generous. The rules are genuinely mechanical (exact offset band, close-above-C trigger, measured-move target), which is more than most rows offer; but the source provides three worked chart examples and no statistical sample, the short side is an adaptation rather than the article's own method, and the geometry forces RR < 1, so everything rides on an unverified high win rate. The conservative readings taken here (5-bar confirmation lag replacing the centered detector, purity and integrity gates, first-signal-only, wide below-A stop, 100% target, market-on-close entry) all push reported performance DOWN, not up: a pooled pass under these readings would be meaningful evidence for the measured-move claim; a failure most likely reflects the true RR<1 burden rather than spec harshness, since each rejected alternative in §10 was the flattering one.
