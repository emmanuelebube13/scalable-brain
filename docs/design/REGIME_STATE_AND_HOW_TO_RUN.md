# The regime system — what it is, where it stands, how to run it

**Written 2026-08-16.** High-level. For the full label mechanics see
`REGIME_LABELS_EXPLAINED.md`; for the trial evidence see
`task/2026-August-week3/regime-aware/STATE.md`.

---

## 1. What a "regime" is here

A label stamped on every bar saying what kind of market it is:
`Trending-Up`, `Trending-Down`, `Ranging`, `High-Vol`, or `UNKNOWN`.

`UNKNOWN` always means **do not trade**. It covers indicator warm-up and any bar with no
label. It is never permissive.

The point of labelling is **routing**: let a trend strategy trade in trends and sit out
elsewhere. A strategy's allowed regimes are its **mask**, and the mask is derived from its
declared family (`trend_following` / `mean_reversion` / `breakout` / `unclassified`) —
never from how it happened to score, which would be fitting.

---

## 2. There are three regime labels. Only one is fit for routing.

| | states emitted | varies on all pairs? | fitted? | use it for routing? |
|---|---|---|---|---|
| `hmm_causal` | all 4 | **no** | yes | no — see below |
| `d1_trend` | Up/Down/UNKNOWN only | yes | no | **no** — see below |
| **`structural`** | **all 4** | **yes** | **no** | **yes** |

**`hmm_causal`** — a 4-state Gaussian HMM fitted to price features. Its coverage is
severely uneven: at H4, EUR_USD, GBP_USD, AUD_USD and USD_CAD each have **exactly 0.0%**
`Trending-Up` bars. Every Trending-Up H4 bar in the database is USD_JPY. Gate a strategy on
it and you have silently built a USD_JPY-only strategy; the "improvement" is pair selection.
Usable at D1, never as an H4 gate.

**`d1_trend`** — `EMA(50)` vs `EMA(200)` on daily closes, shifted one bar. Nothing fitted,
varies healthily everywhere. But it emits **only** Up/Down/UNKNOWN — no `Ranging`, no
`High-Vol`. So a trend or breakout mask enables everything it can produce (the gate does
nothing) and a mean-reversion mask enables nothing it can produce (the strategy is off
forever). Measured 2026-08-16: the `d1_trend` gate was active in **zero of 43 cells**.

**`structural`** — the current answer. Rule-based, causal, `shift(1)`-ed:

```
ADX(14) >  25 and EMA50 > EMA200   -> Trending-Up
ADX(14) >  25 and EMA50 < EMA200   -> Trending-Down
ADX(14) <= 25 and volZ  >  0       -> High-Vol     (volZ = 1-year rolling Z of ATR/Close)
ADX(14) <= 25 and volZ <= 0        -> Ranging
```

Verified coverage, all five pairs:

```
EUR_USD  High-Vol 14.8%  Ranging 39.9%  Trend-Up 14.5%  Trend-Dn 21.0%  UNKNOWN 9.8%
GBP_USD  High-Vol 19.1%  Ranging 37.9%  Trend-Up 13.8%  Trend-Dn 19.5%  UNKNOWN 9.7%
USD_JPY  High-Vol 11.2%  Ranging 44.7%  Trend-Up 12.5%  Trend-Dn 21.8%  UNKNOWN 9.7%
AUD_USD  High-Vol 22.5%  Ranging 36.0%  Trend-Up 16.6%  Trend-Dn 15.1%  UNKNOWN 9.8%
USD_CAD  High-Vol 15.3%  Ranging 40.1%  Trend-Up 16.7%  Trend-Dn 18.3%  UNKNOWN 9.7%
```

Four states everywhere, no pair owning any state, and because it is two indicators and a
comparison there is nothing to overfit and nothing to retrain.

> **Only ever read `fact_market_regime_v2.regime_causal`.** The sibling column
> `regime_smoothed` is fitted forwards *and* backwards over full history and leaks the
> future into past labels.

---

## 3. Does regime routing improve results? Measured: no.

The 2026-08-16 trial ran 43 v2 strategies and the 9 legacy ports, blind vs gated, over
three label sources, on out-of-sample walk-forward trades.

```
comparisons run                                126
aware better on the point estimate              18
aware better with a 95% CI clear of zero         1   <- and that one is an artifact
```

The single "significant" cell (`three_candle_swing_reversal` @ `hmm_causal`) changed
nothing except deleting USD_JPY — EUR_USD and USD_CAD came through with identical means.
That is pair selection, not regime edge.

**The apparatus is trustworthy**: `unclassified` strategies get an all-permissive mask and
came out a no-op in 11/11 cells under every label source, so the rig invents no differences
of its own. That is what makes the null believable rather than merely disappointing.

**What this does not say:** that regime information is worthless, or that a different
taxonomy would fail. It says the pre-registered family→regime routing does not improve
these strategies. Changing masks now to chase a number is the overfit the pre-registration
exists to prevent.

---

## 4. What is published, and what System 2 actually receives

**Published and live** — `gs://scalable-brain-artifacts/system1/regime_status/latest.json`

Current regime per (strategy × granularity × pair), including whether each strategy is
gated on or off right now. Version `2026-08-16T23-15-30Z-4a82a457`, 151 entries, source
`structural`, 75 trading / 76 gated off. Contract:
`contracts/regime-status-contract.json`.

**Not published** — the model-set pointer is `status: withdrawn` and stays that way. See §6.

---

## 5. How to run it

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

**Refresh the HMM labels in the database** (only needed after new price data; multi-minute):

```bash
python -m src.regime.hmm_regime
```

`d1_trend` and `structural` are computed on the fly from D1 prices — nothing to refresh.

**Publish the regime status artifact** (what System 2 reads):

```bash
python -m src.analytics.publish_regime --dry-run   # prints the document, no writes
python -m src.analytics.publish_regime             # verify -> then flip the pointer
```

**Re-run the trial** (blind vs gated, all strategies, all three labels):

```bash
python -m src.regime_aware.v2.runner        # the 43 v2 strategies -> fact_regime_trial_outcomes
python -m src.regime_aware.v1_trial --write # the 9 legacy ports (omit --write for a dry run)
python -m src.regime_aware.v2.report        # the comparison: CIs, per-pair, comparison count
```

Report lands in `results/regime_aware/R3/COMPARISON.md`.

**Check a label's coverage before trusting it** — the check that caught the HMM:

```bash
python -c "
from src.regime_aware.context import build_structural_labels
from src.layer0.strategies.v2_harness import build_frames
import collections
for p in ['EUR_USD','GBP_USD','USD_JPY','AUD_USD','USD_CAD']:
    lab = build_structural_labels(build_frames(p,'D1',(),lookback_years=10)['D1'])
    c = collections.Counter(lab['regime']); n = sum(c.values())
    print(p, {k: f'{100*v/n:.1f}%' for k,v in c.most_common()})
"
```

**Tests:**

```bash
pytest src/regime_aware/ -q     # 41 tests
```

---

## 6. Two things that do not exist, and both matter for go-live

**There is no route from a research strategy to a published model set.**
`publish_model_set.py` packages the existing System-1 bundle plus gatekeeper pointers, and
reads its map from `vet.py` — which builds only from `fact_strategy_regime_attribution`,
i.e. the ten legacy integer-keyed strategies. The 43 research strategies are string-keyed
and have no path in. Naming one a "champion" is not a labelling decision; **there is no
command that does it.** Scoped as nine gaps in
`docs/design/systems/CONTRACT_V2_AND_POSITION_ENGINE.md` §11.3.

**Nothing produces live signals.** `ScoredSignalProducer` exists but has no caller;
System 2 deleted its `live_signal_producer/` on 2026-08-02 at System 1's request (commit
`b3b0abc`); `QUEUE_PROVIDER=local`, and Pub/Sub is unprovisioned. So a published model set
would still generate **zero orders** at market open.

Consequence: the regime status artifact is real and useful — System 2 can render it and
reason about it from the next bar. It is **not** an execution path, and publishing it does
not create one.
