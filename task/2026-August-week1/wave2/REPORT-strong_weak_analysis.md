# REPORT — strong_weak_analysis

**Spec:** `task/2026-August-week1/fleet/upload/wave2/specs/SPEC-strong_weak_analysis.md`
(row 50 of `forex_swing_strategies.csv`) · **Batch:** 3 · **Written:** 2026-08-16

## Implemented

The single-pair-reachable half of the spec, on the D1 frame:

- **§4.2/§5.2 trend gate** — long only above SMA(50), short only below.
- **§4.3/§5.3 structure** — the most recently *confirmed* swing low/high from
  `causal_structure.confirmed_swing_points(period=5)`, with §10 #6's staleness guard
  measured on the **occurrence** bar (`confirmation - 5 >= t - 60`), not the confirmation
  bar. The banned `detect_swing_points` is not used anywhere.
- **§4.4/§5.4 pullback** — the bar's Low reached into `S + 0.25 x ATR(14)` (mirror: High
  into `R - 0.25 x ATR`) and its Close finished back outside the level.
- **§6 stop** — `S - 1.0 x ATR(14)` / `R + 1.0 x ATR(14)`, anchored to decision-bar values.
- **§7 exit** — one `ExitLeg(fraction=1.0, kind="trailing", atr_multiple=3.0)`; no
  take-profit, no time leg.
- Market entries, `expires_after_bars=None`, `max_concurrent_positions = 1` (§10 #9).

The cross-sectional half (§3) is implemented as three **public pure functions** —
`twenty_bar_return`, `currency_strength`, `candidate_instrument` — carrying the full
13-pair universe, the base/quote orientation, the per-currency sums, the best/worst
ranking and §10 #4's "no synthetic USD legs" rule. They are pinned by the golden fixture
and are **not reachable** from `generate_orders`.

## Deviations

1. **The strength-rank gate is not applied.** This is the §6.2 case the brief names.
   `generate_orders` is handed one pair at a time with no pair identity and no access to
   the other 12 series, so §3's ranking and §4.1/§5.1's "is this the {best, worst}
   instrument?" cannot be evaluated inside the strategy. Rather than load another pair —
   forbidden, and a database read from inside a strategy — the module emits the remaining
   gates on whatever pair it is handed, tagging every trade `sw_trend_pullback_norank`.
   **Direction of the error: this trades far more than the spec.** §4.1 selects at most
   one instrument out of 13 per bar; this takes every qualifying setup on all five pairs.
   The measurement below is therefore evidence about the trend-plus-pullback skeleton and
   says nothing about the ranking — which is the part the author claimed the edge for.
   Precedent: `currency_momentum_factor` (row 43) resolved the identical problem the same
   way, and the audit accepted it.
2. **`pairs` declares the five live instruments**, not the 13 of §2. The eight Wave-1
   additions never landed, so declaring them would only produce skipped cells.

## Uncertainties

- **DECISION — which end of a tie is "worst".** §3.5 fixes the tie-break as alphabetical
  but only names it for the ranking as a whole. The implementation builds one ranking
  (descending by strength, alphabetical within a tie) and takes `best` = first,
  `worst` = last, so of two currencies tied at the bottom the alphabetically *last* is
  worst. The symmetric alternative (alphabetically first at both ends) is equally
  readable. §3.5 calls exact ties measure-zero on float sums; the fixture pins whichever
  convention a reviewer rules for.
- **DECISION — the reconstruction is not the author's formula, and cannot be.** §10 #1
  already says this: the proprietary strength formula is undisclosed, so even a
  multi-pair harness would be measuring the CSV pseudocode's stand-in. A reviewer should
  not read any verdict on this id as a verdict on the author's method.
- **The 15 missing crosses would degrade the ranking even if it were reachable.** §10 #7:
  CHF's strength would be driven entirely by USD_CHF and NZD's by two crosses. This does
  not affect the measured path (which has no ranking at all) but it does mean that
  wiring the helpers into a future multi-pair harness would not yet reproduce §3.
- §7's trailing leg replaces a signal exit ("trend ends / rank reversal") that contract v2
  cannot express (§10 #3). For a hold-for-months strategy that is a material fidelity
  loss, and it cuts in the pessimistic direction.

## Coverage

- **Declared:** EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD.
- **Wanted by the spec but absent:** the other eight of §2's 13 (GBP_JPY, EUR_JPY,
  NZD_USD, USD_CHF, EUR_GBP, EUR_AUD, AUD_NZD, EUR_CAD) plus the 15 crosses of
  `DATA-GAP-strong_weak_analysis.md`. Every currency except USD, EUR, GBP, JPY, AUD and
  CAD is therefore untouched, and CHF/NZD do not appear at all.
- **Skipped by the harness:** none. All five cells produced trades.

## Verdict

Harness run 2026-08-16T07:09:31Z — **FAIL**.

| metric | pooled |
|---|--:|
| OOS trades | 295 |
| profit factor | 1.24 |
| Sharpe | 0.36 |
| max drawdown | 7.94% |
| win rate | 35.2% |
| recovery factor | 1.30 |
| OOS months | 83.9 |
| cells passed | 0 of 5 |

Four gates fail. What limited it is the win rate against the payoff: 35% of trades win and
the 3×ATR trail does not stretch the winners far enough to carry the other 65% to PF 1.50.
Drawdown is the mildest in the batch (7.9%), so the failure is one of insufficient edge,
not of risk. Dispersion is wide and directionless — AUD_USD PF 2.03 against USD_CAD
PF 0.55 on comparable trade counts (65 vs 75) — which is what one expects from a signal
with no cross-sectional selection behind it. Run once; no code changed after the result.
