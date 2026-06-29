# FIX-S1-003 — Regimes do not discriminate strategy performance (the map's core premise is failing)

**Severity:** P1 (the regime→strategy map's central value-add is currently inert)
**Status:** Proposed (investigation)
**Author:** Claude (surfaced when the owner questioned one strategy qualifying in multiple regimes)
**Date raised:** 2026-06-26
**Scope:** `src/system1/attribution/attribute.py` (regime tagging), Layer 1 regime model / labels,
Layer 0 backtests (whether strategies are regime-filtered), MODEL-004/005 premise.
**Risk to live trading:** Low to investigate. But it means the regime structure in
`regime_strategy_map.json` is currently **cosmetic**, not functional.

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
