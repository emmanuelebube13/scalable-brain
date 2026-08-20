# Strategy card — `nnfx_backtrader`

**For System 2 / System 3 telemetry.** Live as of model set
`2026-08-17T09-28-46Z-d593220a_gk-656f09e2`.

---

## Identity

| | |
|---|---|
| `strategy_id` | **36** (sent on the wire as the string `"36"`) |
| `strategy_key` | `nnfx_backtrader` |
| Display name | NNFX Backtrader |
| `selection_basis` | **`designated`** — published despite failing a gate |
| Family | trend_following |

## Timeframe and universe

| | |
|---|---|
| **Decision timeframe** | **D1 (daily)** — decisions only at the daily close, ~21:00–22:00 UTC |
| Context frames | none |
| Pairs | EUR_USD, GBP_USD, USD_JPY, AUD_USD, USD_CAD |
| Warm-up | 150 daily bars |

## Expected frequency — read this before alerting on silence

**114 out-of-sample trades over ~7 years, across 5 pairs.** That is roughly
**3 trades per pair per year** — one every 2–4 months.

Most recent decisions: GBP_USD 2026-07-22, USD_JPY 2026-07-29.

**Long silences are normal and are not a fault.** A week with no signal is the expected
case, not an outage. Please do not build a staleness alert that treats "no signal today" as
a problem — the correct staleness signal is System 1 failing to *publish an artefact*, not
the absence of a trade.

## What it does

Daily-trend persistence, taken only when several independent measurements agree. A
Butterworth low-pass filter on the mid price provides a smoothed baseline; a close crossing
that baseline arms the trigger, and confirmation indicators plus a volatility filter must
agree before an order is emitted. It is a classic "No Nonsense FX" style rule stack —
one baseline, confirmation, and a volatility gate.

Source: https://github.com/ddm-j/NNFX-Backtrader

## Order shape

| | |
|---|---|
| Entry | **market**, at the open following the signalling daily close |
| Direction | long or short — always explicit on the wire, never inferred |
| Stop | **1.5 × ATR(14)** |
| Take profit | **3.0 × ATR(14)**, single leg, full position |
| Risk:reward | **1 : 2** |
| Breakeven / trailing | none |
| Max concurrent | one position per pair |

Every signal carries `entry`, `stop` and `target` as absolute prices. If any is missing the
producer refuses to emit rather than sending a partial order.

## Measured performance (out-of-sample, 2019-09-18 → 2026-07-30)

| metric | value | gate | pass |
|---|--:|--:|:--:|
| Profit factor | 1.61 | ≥ 1.50 | ✓ |
| Sharpe | 1.22 | ≥ 0.80 | ✓ |
| Max drawdown | 12.4% | ≤ 25% | ✓ |
| Win rate | 44.7% | ≥ 40% | ✓ |
| Recovery factor | 3.64 | ≥ 3.00 | ✓ |
| **OOS coverage** | **46.35 mo** | **≥ 60 mo** | **✗** |

**It fails one gate: evidence duration.** Not measured performance — it has simply not been
observed across a long enough out-of-sample window. That is why it is `designated` and not
`qualified`, and it is the whole reason for System 3's half-size posture.

Robustness figures worth surfacing, because two earlier candidates in this project looked
strong and were a unit bug and a concentration artifact:

- **Mean R** +0.338, bootstrap 95% CI **[+0.049, +0.620]** — clear of zero
- **Tail dependence 18%** — removing the best three trades costs 18% of total R, so the
  result is not carried by a handful of outliers
- **Largest pair 24%** of trades, 4 of 5 pairs profitable — not a single-pair effect

Per-pair OOS mean R: EUR_USD +0.87 · USD_JPY +0.68 · AUD_USD +0.31 · GBP_USD +0.22 ·
USD_CAD −0.14

## Scoring

**Signals arrive `unscored`** — `model_score: null`, `threshold_applied: null`,
`scoring_status: "unscored"`.

The gatekeeper champion was trained on the legacy ten and does not know strategy 36. Policy
is to refuse rather than invent a score. Per System 3's Layer P this is treated as absence
of evidence, not evidence against, and passes unpenalised.

## Status

**Practice account forward test.** This is evidence-gathering to close the OOS-coverage
gap, not a proven edge. Treat it accordingly.
