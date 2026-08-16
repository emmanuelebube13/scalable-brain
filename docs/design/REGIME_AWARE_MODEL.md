# Regime-Aware Trial: Model & Architecture

This document serves as the technical reference for the August 2026 regime-aware trial. It covers what the model is, the labels used, training protocols, sampling methodology, and its limitations.

## 1. What the regime-aware model is

The regime-aware intervention in this trial is a **gate**, not a re-tuning. It determines *whether* a strategy is allowed to trade in the current market environment, rather than *how* it trades. 

It is implemented as a `ParamBlock` per regime, where the `enabled` boolean selects if the strategy should participate. 

**Continuous Indicator Computation:**
Crucially, all strategy indicators are computed continuously over the *entire* price frame, regardless of the active regime. The regime label only acts as a mask on the decision bar itself. Segmenting the data into regime-specific chunks before computing indicators destroys the continuity of the time series, corrupting long-lookback indicators (like EMAs) and introducing gaps that invalidate the signal.

## 2. The models used

There are two regime labels available. They are not interchangeable.

### D1 Trend Label
- **Mechanism:** `EMA(50)` vs `EMA(200)` on daily closes.
- **Properties:** Applied with `shift(1)` to ensure strict causality. The first 200 bars (the slow EMA warm-up) are labeled `UNKNOWN`.
- **Fitted State:** **Nothing is fitted.** There is no training phase, no scaler, no versioning, and no published artifact. It is a deterministic rule. This simplicity and lack of overfitting surface is the primary reason it was chosen as the routing instrument.

### HMM Causal Label
- **Mechanism:** 4-state Gaussian HMM.
- **Parameters:** `LABEL_ORDER="trend_first"`, `CAUSAL_SMOOTHING=True`, `TAU_BY_GRANULARITY {D1:0.25, H4:0.25, H1:0.10}`. It includes a K-Means fallback if accuracy drops below the 0.70 gate.
- **Fitted State:** Fitted, versioned, and walk-forward refitted to produce the causal label column (`regime_causal`). 

### Why D1 Trend is the Routing Instrument (and HMM is not)
The HMM label is severely uneven at lower granularities. Gating on the HMM `Trending-Up` label at H4 silently converts any strategy into a USD_JPY-only strategy. The zeros in the table below are literal, not rounding.

**HMM Causal Label Occupancy (2026-08-16):**
```
D1  AUD_USD  n=  4891 | Up 11.4%  Dn  5.3%  Rng 78.8%  HV  4.4%
D1  EUR_USD  n=  4911 | Up 16.7%  Dn  3.3%  Rng 79.4%  HV  0.7%
D1  GBP_USD  n=  4904 | Up 12.4%  Dn  5.5%  Rng 78.3%  HV  3.8%
D1  USD_CAD  n=  4916 | Up 15.4%  Dn  3.7%  Rng 78.0%  HV  2.8%
D1  USD_JPY  n=  4921 | Up 20.3%  Dn 23.7%  Rng  4.3%  HV 51.7%
H4  AUD_USD  n= 28185 | Up  0.0%  Dn  4.0%  Rng 90.5%  HV  5.5%
H4  EUR_USD  n= 28222 | Up  0.0%  Dn  1.7%  Rng 93.5%  HV  4.9%
H4  GBP_USD  n= 28164 | Up  0.0%  Dn  3.5%  Rng 91.1%  HV  5.4%
H4  USD_CAD  n= 28172 | Up  0.0%  Dn  1.3%  Rng 95.0%  HV  3.8%
H4  USD_JPY  n= 28187 | Up 23.9%  Dn 14.0%  Rng 10.9%  HV 51.2%
```
Because of this collapse at H4, the deterministic **D1 trend label** is used as the routing instrument for the trial.

## 3. Training and refitting

Only the HMM label is trained. It uses a walk-forward, fold-fit methodology to generate forward-only inference labels.
- **Folds:** Supplied by `src/system1/validation/walk_forward.py`. Min_train is 36 months, step is 6 months, and OOS is 6 months (anchored).
- **Consistency:** We use the exact same fold implementation as the rest of the system because maintaining two fold implementations is a guaranteed defect.
- **Validation:** The walk-forward fits are gated by a Cohen's kappa requirement of `≥0.40`.

## 4. Sampling

- **Attribution:** Trades are attributed to folds, and only the OOS segments of each walk-forward step count toward the causal record.
- **Join Semantics:** The regime label is joined point-in-time to the **decision bar**, using a backward merge (`merge_asof(direction="backward")`). This ensures no look-ahead bias. We join on the decision bar rather than the fill bar because the regime informs the *intent* to trade, not the execution latency.
- **Trade Floor:** The R3 runner enforces a minimum trade floor. Metrics derived from starvation cells (e.g., fewer than 30 trades) are ignored because a metric computed from 6 trades is statistical noise.

## 5. Parameter tuning — and why there was none

This week, the blind arm and the regime-aware arm differ **only** in their `enabled` state. There are no parameter or risk differences. 

**Reasoning:** Per-regime parameter tuning multiplies the search space by four across confidence intervals that already straddle 1.0. This project has previously produced a significant-looking result that turned out to be an artifact of pair selection (T3). Introducing tuning before establishing the validity of the gate itself is a direct path to overfitting. If per-regime tuning is ever justified and added, it must happen strictly inside the walk-forward **train** fold.

## 6. The pre-registration

To prevent overfitting, every strategy's regime mask was assigned based on its **declared strategy family**, not its empirical performance.

- **Hypothesis vs. Fit:** Masking a `trend_following` strategy to only trade in trending markets is a testable hypothesis. Adjusting a strategy's mask because it happened to perform poorly in a specific regime during backtesting is an overfit.
- **Pre-registration:** Masks were frozen and recorded in `PREREGISTRATION.md` (SHA256: `ce6bd8100ccccdfe18990a8daff24e85fb6c6349ffe8c64c5d06e8038f9c7fec`) *before* the R3 runner executed any regime-aware backtests.

## 7. Limitations

Future consumers of this trial must be aware of the following limitations:
1. **Statistical Insignificance:** One week of execution is not statistical evidence. The results of this trial are operational proofs of concept, not conclusive validation of the regime-gating hypothesis.
2. **HMM H4 Usability:** The HMM label is unusable as an H4 gate due to its collapse into `Ranging` on four out of five pairs.
3. **No Live Path:** Nothing in this trial is promoted to the live model set. The pipeline to move v2 strategies into live execution does not exist.
4. **Multiple Comparisons:** The R3 runner executed comparisons across 52 strategies (43 v2, 9 legacy). Running this many parallel comparisons guarantees false positives by chance. Any "winning" strategy must be evaluated with a severe penalty for multiple comparisons.
