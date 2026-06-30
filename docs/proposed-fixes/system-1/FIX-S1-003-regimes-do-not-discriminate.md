# FIX-S1-003 — Regimes do not discriminate strategy performance (the map's core premise is failing)

**Severity:** P1 (the regime→strategy map's central value-add is currently inert)
**Status:** VERIFIED (documented finding) — discrimination measured on **causal** labels (FIX-S1-005)
under both entry-only and dominant-over-trade-life tagging: **0 of 10 strategies discriminate.** The
regime dimension is confirmed cosmetic; recommendation below. Live map untouched.
**Author:** Claude (surfaced when the owner questioned one strategy qualifying in multiple regimes)
**Date raised:** 2026-06-26
**Scope:** `src/system1/attribution/attribute.py` (regime tagging), Layer 1 regime model / labels,
Layer 0 backtests (whether strategies are regime-filtered), MODEL-004/005 premise.
**Risk to live trading:** Low to investigate. But it means the regime structure in
`regime_strategy_map.json` is currently **cosmetic**, not functional.

> **Finding note (2026-06-30):** Resolved on branch `fix/s1-003-regime-discrimination` (stacked on
> FIX-S1-005) as a **documented finding + one targeted experiment**, not a signal-gen build. The fix
> doc's §2 evidence was on the *leaked* smoothed labels; FIX-S1-005 then made the labels causal, so
> the open question was whether the leak was what made regimes look degenerate. It was not.
>
> **New additive measurement module** `src/system1/attribution/discrimination.py` (+10 pure unit
> tests, `tests/test_discrimination.py`) computes, per strategy, the win-rate-by-regime **spread** and
> a **chi-square** test of regime↔win/loss independence on the **causal** label (`regime_causal`),
> under two tagging schemes — production **entry-only** and **dominant-regime-over-trade-life** (modal
> causal regime over `[entry, entry+holding_bars]`, addressing hypothesis #1). It is a **post-hoc
> diagnostic only** — it does NOT change production attribution, and the over-life tag would be
> look-ahead if used to *gate* trades. A strategy "discriminates" only if `chi2_p < 0.05` **and**
> spread `≥ 0.10` (a material gap; huge-n trivial spreads don't count). The "gate can fire" principle
> is honored: a test proves the measurement flags a synthetically-discriminating strategy `True`.
>
> **Log-only run on 134,520 trades (report `regime_discrimination_20260630T225156Z.json`):**
>
> | tagging | strategies discriminating | max spread | median spread |
> |---|---|---|---|
> | entry-only (production) | **0 / 10** | 0.075 (strat 10) | 0.031 |
> | dominant-over-trade-life | **0 / 10** | 0.097 (strat 10) | 0.028 |
>
> The entry-only table reproduces §2 (strat 1 spread 0.007, strat 10 0.075). **Hypothesis #1 is
> closed:** tagging the dominant regime over the whole trade life did **not** rescue discrimination —
> spreads stay 0.7–9.7%, and no strategy clears both the significance and materiality bars. The two
> "significant" cells (strat 6, 9) are huge-n artifacts with ~3–4% spreads and strat 6 is a ~20%-win
> loser — significance ≠ usable specialization. **Strat 10** (the *only* gate-passing strategy) shows
> **anti**-specialization: as a mean-reversion strategy it wins *least* in Trending-Up (0.67–0.68) and
> *most* in Trending-Down/High-Vol — the opposite of a coherent regime edge (chi2_p 0.36–0.61, n.s.).
>
> **Conclusion (see §7 below):** removing the FIX-S1-005 leak did not change the verdict — the regime
> label carries no discriminating information for the current strategy roster. The corrected map is
> mathematically honest but is **one regime-agnostic strategy wearing a regime costume.** Do **not**
> build regime-filtering at signal generation (hypothesis #2): it would enforce a specialization the
> data does not support. The real levers are (a) a feature set with demonstrated discrimination and
> (b) a broader strategy roster (only 1 of 10 has a genuine edge). Any promotion of
> `regime_strategy_map.json` should be made *knowing* the regime structure is not yet functional.
> The one narrow place regime still does real work is the gatekeeper's per-regime *threshold*
> calibration (`gatekeeper/train.py`), which is not the map's specialization premise.

---

## 1. The question that surfaced it

The whole point of a regime→strategy map is **specialization**: different strategies should win in
different market regimes (trend strategies in trends, mean-reversion in ranges). The owner asked the right
question: how can a single **mean-reversion** strategy (`Range_Stochastic_Divergence`) qualify in
**Trending-Up, Trending-Down, and Ranging** at once? A range strategy should not thrive in trends.

## 2. Evidence (corrected-metrics run, H1, 134,520 trades)

Win-rate **spread across regimes** per strategy (max − min over the 4 regimes):

| strategy | win-rate min | max | spread |
|---|---|---|---|
| 1 (Trend EMA) | 0.318 | 0.330 | **0.012** |
| 2 (Trend EMA) | 0.329 | 0.366 | 0.038 |
| 5 | 0.305 | 0.331 | 0.025 |
| 7/8 | 0.462 | 0.503 | 0.041 |
| 10 (Range Stoch) | 0.667 | 0.737 | **0.070** |

Strategy 1, a **trend** strategy, wins **31.8%** in Trending-Up and **32.1%** in Ranging — essentially
identical. If regimes were meaningful, a trend strategy would win materially more in trends than in
ranges. It does not. **Every** strategy's performance is nearly flat across regimes. So:

- Good strategies (strat 10) are good in *every* regime; bad strategies are bad in *every* regime.
- The regime dimension adds almost no discriminating information.
- Strategy 10 "qualifies for everything" not because it's a magical all-weather strategy, but because
  **its edge is regime-independent and it is the only strategy clearing the gates** — so it appears in
  each regime it passes (3 of 4; High-Vol fails on Sharpe 0.79 < 0.80).

**Important clarification for the owner:** the qualifier's *logic* is correct — it evaluates each
strategy independently per regime and only lists it where it passes; it does **not** blanket-approve one
strategy for all regimes. The problem is upstream: the regimes themselves aren't separating behavior, so
per-regime evaluation produces near-identical verdicts. The map is *honest* but *degenerate*.

## 3. Hypotheses for root cause (to investigate, not yet confirmed)

1. **Entry-only regime tag vs. multi-bar trades.** Regime is tagged at entry, but a trade plays out over
   many bars and may span several regimes; the entry label is weakly related to the outcome.
2. **Strategies are not regime-filtered.** Layer 0 strategies trade whenever their own setup appears,
   regardless of regime; attribution then just buckets the same behavior by an unrelated label.
3. **Regime labels may not capture what strategies care about.** The HMM/K-means regimes (ATR/ADX-based)
   may not align with the conditions that make a given strategy win or lose.
4. **Regime persistence vs. trade horizon mismatch** (regimes flip faster/slower than trades last).

## 4. Proposed investigation / fix (high level)

- **Quantify discrimination:** formal test that per-regime metric distributions differ (e.g. per strategy,
  is win-rate-by-regime significantly non-uniform?). If not, the regime feature is not earning its place.
- **Tag regime over the trade's life,** not just entry (e.g. dominant regime held during the trade), and
  re-measure discrimination.
- **Regime-filter at signal generation:** consider only allowing a strategy to trade in regimes where it
  has a tested edge, then re-attribute — this is the design the map *assumes* but isn't enforced.
- **Sanity-check strat 10 standalone:** a 67–74% win-rate mean-reversion strategy over 119 months is
  plausible (mean-reversion wins often, small) and costs *are* modelled (1pip spread, 0.5pip slippage),
  but confirm no look-ahead in the stochastic signal and that exits are realistic before trusting it live.

## 5. Implication for promotion (FIX-S1-001 map)

The corrected map is mathematically trustworthy, but it is **one regime-agnostic strategy wearing a
regime costume.** Promoting it ships a system that effectively trades one mean-reversion strategy
regardless of regime. That may be an acceptable **v1** — but the owner should promote it *knowing* the
regime structure is not yet doing real work, and that the real lever is (a) this investigation and
(b) a broader strategy roster (only 1 of 10 strategies has a genuine edge).

## 6. One-paragraph summary for a fast reviewer

A mean-reversion strategy qualifying in trending regimes looked wrong — and it is symptomatic: across all
10 strategies, win rate barely moves between regimes (spreads 1–7%; a trend strategy wins 31.8% in trends
vs 32.1% in ranges). The regime label is not discriminating performance, so the regime→strategy map is
currently cosmetic. The qualifier's per-regime logic is correct; the upstream regime signal isn't earning
its keep. Investigate entry-only tagging, lack of regime-filtering at signal generation, and label
relevance; meanwhile treat the promoted map as effectively one regime-agnostic strategy.

---

## 7. Conclusion — measured on causal labels (2026-06-30)

The §1–§6 evidence was computed on the **leaked smoothed** labels. After FIX-S1-005 made the regime
label **causal**, the discrimination study was re-run on `regime_causal` via the new
`src/system1/attribution/discrimination.py` (log-only, 134,520 trades). The verdict is unchanged and
now leak-free:

- **Entry-only tagging (production):** 0 / 10 strategies discriminate (spread+significance bar);
  max spread 0.075, median 0.031 — reproduces §2.
- **Dominant-regime-over-trade-life tagging (hypothesis #1):** 0 / 10 discriminate; max spread 0.097,
  median 0.028. **Tagging over the trade's full life did not change the answer.**

So the three leading hypotheses resolve as:

1. **Entry-only vs multi-bar tagging** — *tested and rejected as the cause.* Dominant-over-life
   tagging leaves spreads flat (≤ 9.7%) and still 0/10 discriminating.
2. **No regime-filtering at signal generation** — *confirmed absent* (Layer-2/Layer-0 never filter by
   regime; the map is read only by the serializer's non-empty check). But building it now is **not
   recommended** — it would enforce a specialization the data does not support.
3. **Label relevance / feature set** — *the live suspect.* The ATR/ADX/vol regime features do not
   separate the conditions these strategies win/lose under. This is where future work should go.

**Recommendation:** The corrected `regime_strategy_map.json` is mathematically trustworthy but
functionally regime-agnostic — promote it (if at all) as a v1 single-strategy artifact, *knowing* the
regime structure is cosmetic. The real levers are a discriminating feature set (item 3) and a broader
roster with more than one edge-bearing strategy. The only place regime currently earns its keep is the
gatekeeper's per-regime threshold calibration, which is orthogonal to the map's specialization premise.

**Standalone strat-10 sanity (open):** a 67–75% win-rate mean-reversion strategy over 119 months is
plausible (small frequent wins; costs modelled), but its **anti-specialization** (wins least in
Trending-Up) warrants the §4 standalone look-ahead/exit-realism check before any live trust — tracked
as a follow-up, not a blocker for this finding.

**Artifacts:** `results/reports/regime_discrimination_<ts>.json`;
module `src/system1/attribution/discrimination.py`; tests
`src/system1/attribution/tests/test_discrimination.py` (10, green).
