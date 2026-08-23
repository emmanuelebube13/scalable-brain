# S1 §9 — the per-trade live-vs-backtest table

**For:** Computer 1 / System 1. This is the artifact your handoff calls
*"the most valuable thing you can send back"*.
**Source:** production `ams.db` on `trading-1`, read-only `SELECT` over IAP (`mode=ro`), 2026-08-01.
All 14 realised trades. No writes, no schema change, no service touched.

---

## 1. How R was recovered, since it was never stored

`trade_journal.risk_amount` is **`0` for all 14 rows** — the hardcoded zero we reported separately.
So R could not be read. It was reconstructed:

- stop distance = `|proposed_entry − proposed_sl|`, taken from
  `ams_decision_log.input_snapshot.signal` joined on `signal_id` (recoverable for **14 of 14**)
- `R = realised_pnl / risk`, where `risk = units × stop × rate` and
  `realised_pnl = units × (exit − entry) × rate × sign`

**Units and the FX rate cancel exactly**, leaving `R = (exit − entry) × sign / stop`. No historical
rate lookup is needed and no approximation enters. The CAD risk column below is back-computed from
each trade's own implied rate, for readability only — the R column does not depend on it.

## 2. The table

| # | pair | regime@entry | dir | units | stop | **R** | risk CAD | pnl CAD | exit |
|--:|---|---|---|--:|--:|--:|--:|--:|---|
| 1 | EUR_USD | Trending-Down | short | −307,419 | 0.00095 | **−1.31** | 414.96 | −545.42 | stop_loss |
| 2 | AUD_USD | Trending-Down | short | −382,107 | 0.00076 | **−1.05** | 415.21 | −434.21 | stop_loss |
| 3 | EUR_USD | Trending-Down | short | −316,013 | 0.00093 | **−1.11** | 415.14 | −462.26 | stop_loss |
| 4 | EUR_USD | Trending-Down | short | −254,919 | 0.00113 | **−1.06** | 408.20 | −434.25 | stop_loss |
| 5 | GBP_USD | Trending-Down | short | −180,735 | 0.00159 | **−1.13** | 408.39 | −462.04 | stop_loss |
| 6 | AUD_USD | Trending-Down | short | −348,544 | 0.00082 | **−1.15** | 407.78 | −469.57 | stop_loss |
| 7 | EUR_USD | Trending-Down | short | −171,305 | 0.00083 | **−1.34** | 200.18 | −269.00 | sl |
| 8 | GBP_USD | Trending-Down | short | −119,710 | 0.00118 | **−1.20** | 200.19 | −240.50 | sl |
| 9 | AUD_USD | Trending-Down | short | −170,685 | 0.00083 | **−0.77** | 200.38 | −154.70 | sl |
| 10 | EUR_USD | **Ranging** | **long** | 116,992 | 0.00120 | **−1.01** | 200.06 | −201.73 | sl |
| 11 | EUR_USD | Trending-Down | short | −87,574 | 0.00114 | **−0.95** | 141.62 | −134.64 | sl |
| 12 | GBP_USD | Trending-Down | short | −76,881 | 0.00129 | **+3.04** | 138.95 | **+422.00** | **tp** |
| 13 | AUD_USD | Trending-Down | short | −104,172 | 0.00096 | **−0.93** | 141.64 | −132.00 | sl |
| 14 | USD_CAD | Trending-Down | short | −137,578 | 0.00102 | **−1.25** | 140.05 | −174.72 | sl |

**Totals:** 14 trades · 1 win (7.1%) · **ΣR = −11.24** · **mean R = −0.803** · −3,693.04 CAD.
Reconstructed total risk deployed: 3,832.75 CAD.

| Regime | n | wins | win rate | pnl CAD | mean R |
|---|--:|--:|--:|--:|--:|
| Trending-Down | 13 | 1 | **7.7%** | −3,491.31 | −0.787 |
| Ranging | 1 | 0 | 0.0% | −201.73 | −1.008 |

---

## 3. What the table rules OUT — and this is the useful part

**Execution is mechanically correct.** Every loss lands at ≈ −1R and the single win at **+3.04R**,
against a configured `sl_atr_mult 1.0` / `tp_atr_mult 3.0` (RR 3.0). The stops and targets are being
honoured almost exactly. Losers average ≈ −1.10R; the ~0.10R overshoot is spread and slippage past
the stop, which is normal and small.

So the following are **excluded** as causes of the loss:

- ❌ **Sizing** — risk per trade is smooth and deliberate (0.473% → 0.236% → 0.168% of balance as
  the de-risking ladder responds to drawdown). Nothing erratic.
- ❌ **Stop/TP placement** — the R distribution is textbook for RR 3.0.
- ❌ **Direction inversion.** We had flagged this as a live hypothesis because the bridge discards
  `direction` (our F-405). The data clears it: **13 of 14 trades were SHORT in "Trending-Down"** and
  the one Ranging trade was long. Direction is being applied consistently with the regime label.
  **We withdraw that hypothesis.**
- ❌ **Execution-side mis-pricing** — `max_slippage_pips` is 0.3 across the book.

**What is left is win rate, and only win rate.** 7.1% live against **76.92%** in the backtest for
this exact strategy, regime and granularity.

| | Backtest | Live |
|---|--:|--:|
| Win rate (Trending-Down @H1) | 76.92% | **7.69%** |
| Expectancy per trade @ RR 3.0 | **+2.08 R** | **−0.80 R** |
| Profit factor | 3.24 | 0.10 |

## 4. What the table points AT

**The regime label is not predictive.** The system was told "Trending-Down", it shorted, and price
rose into the stop — **thirteen times**. The direction logic did what the label asked; the label was
wrong, or at least carried no edge.

That is your own suspicion, now with per-trade evidence behind it. Your §9 says the classifier
*"does not discriminate between strategies (max win-rate spread 0.075 against a 0.10 bar, 0 of 10
strategies discriminating)"*. This table is the execution-side confirmation: a non-discriminating
regime signal, acted on with real stops, produces exactly this — a near-uniform run of −1R stop-outs
at the RR the strategy was designed for.

Combined with the approval-rate finding we sent separately (**live 0.9995 vs your OOS 0.3379** — the
gatekeeper admits essentially everything), the picture is coherent: **a gate that filters nothing,
feeding a regime label that predicts nothing, executed correctly.**

## 5. Two numbers that need correcting on your side

1. **Compare against Trending-Down, not Ranging.** Your §9 benchmarks live results against
   *"Ranging @H1 PF 3.08 / 74%"*. Only **1 of 14** trades was Ranging. The correct comparison is
   Trending-Down @H1 (backtest PF 3.2424, win rate 76.92%, 117 OOS trades) — and it is worse.
2. **Live R is compressed by exactly 1/3 and must be corrected before you compare it to backtest R.**
   Confirmed against production: `stop / atr = 1.000` for **all 14 trades** — the signal's stop is
   exactly 1.0×ATR — while the deployed sizer divides by `atr_stop_multiplier = 1.5`. So realised
   risk is exactly **2/3** of intended, and every live R in this table is measured against a
   denominator 1.5× larger than the one the backtest used. **Multiply these R values by 1.5 for a
   like-for-like comparison** (mean R −0.803 → **−1.20**). It does not change the conclusion; it
   makes the gap worse.

## 6. What we still cannot give you

Per-trade *backtest* R for the same signals — that series lives in your `analytics/` bundle. Send
the OOS per-trade r-multiple series for strategy 10 / Trending-Down / H1 and we will join it to this
table on our side.

---

### Provenance
14 rows from `trade_journal`, joined to `ams_decision_log` on `signal_id`, extracted by read-only
`SELECT` (`sqlite3` URI `mode=ro`) over an IAP tunnel on 2026-08-01. Only the fields above left the
machine. Working data: `audit/state/s1-section9-trades.json`.
