# System 1 — "The Brain" — How It Works, How to Run It, and Results

*Analysis date: 2026-07-01 · Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain` · Code under test: `src/system1/`*

---

## 1. What System 1 is

System 1 is the **model-building brain** of the Scalable Brain trading platform. In the
3-computer evolution, it is the *training* computer: it turns raw OANDA price history into a
**published, versioned model bundle** that the execution engine (System 2, "The Hand")
downloads and trades.

Its guiding rule is enforced in code, not just docs: *no strategy is promoted until it proves
out-of-sample edge, and every artifact is checksummed, lineage-tracked, and gated.*

> ⚠️ **Note:** `CLAUDE.md` documents the **legacy 8-layer** system (`src/layer0…layer7`). The
> code analysed here lives in **`src/system1/`** — a newer, cleaner rewrite organized as tasks
> **MODEL-001 … MODEL-010**. It *reuses* some layer0 primitives (indicators, OANDA ingest) but
> is otherwise self-contained. That is why there is no `system1` section in `CLAUDE.md`.

---

## 2. The pipeline — module by module

Each module is a `python -m` entry point, separates pure math (calendar/metrics) from I/O for
testability, and registers to MLflow. Data flows top-to-bottom:

| #   | Module | Role (business rule) | Key output |
|-----|--------|----------------------|------------|
| 001 | `ingestion/multi_timeframe_ingest.py` + `dq.py` | Ingest OANDA prices at multiple timeframes with **data-quality checks** | `fact_market_prices` |
| 002 | `features/feature_pipeline.py` + `definitions.py` | Build a **versioned Parquet feature store**. All features are *trailing-only* (no look-ahead): `returns_1, atr_14, adx_14, price_position_20, volatility_20`. Deterministic → byte-identical partitions | `feature-store/{version}/…` |
| 003 | `regime/hmm_regime.py` | **4-state Gaussian HMM** regime engine (D1/H4/H1). Maps states → `{Trending-Up, Trending-Down, Ranging, High-Vol}`. Falls back to K-Means if HMM fails a convergence/accuracy gate (≥0.70). Emits both a reporting label and a **causal walk-forward label** | `fact_market_regime_v2` + `models/hmm_model.joblib` |
| 004 | `attribution/attribute.py` + `metrics.py` | Point-in-time join of every trade to the **causal** regime at entry, then per (strategy × regime × granularity) metrics (Sharpe, PF, drawdown…) on **OOS trades only**, with Bayesian shrinkage for thin cells | `fact_strategy_regime_attribution` |
| 005 | `vetting/vet.py` + `gates.py` | Apply **strict gates** (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo), rank survivors, emit the **regime→strategy map + weights** (schema-validated) | `regime_strategy_map.json`, `strategy_weights.json` |
| 006 | `gatekeeper/train.py` + `thresholds.py` | Train an **XGBoost signal gatekeeper** on causal-regime features; expanding-window walk-forward calibrates per-regime thresholds and measures **bootstrap-significant OOS uplift** | `champion_model.pkl` (+ manifest) |
| 007 | `serializer/serialize.py` | **Serialize + publish** the bundle to a storage backend (local/GCS) with SHA256 round-trip verify, secret-scan, atomic `latest.json` pointer flip, retention | published bundle |
| 008 | `queue_producer/producer.py` | Publish **scored signals** to `Scored_Signal_Queue` — schema-validated, idempotent, backpressure + DLQ | queue messages |
| 009 | `scheduler/orchestrator.py` + `triggers.py` | **Retrain orchestrator**: triggers (Sunday 00:00 UTC / low Sharpe / circuit breaker) → single-flight lock → gated pipeline → **atomic promote only if it clears gates and beats the incumbent** | `retrain_log_*.json` |
| —   | `validation/walk_forward.py` | Shared, pure **walk-forward fold generator** (min_train=36mo, step=6mo, OOS=6mo, anchored) used by 003/004/006 | — |

---

## 3. How to run it

Everything runs from the repo root with the project venv:

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate

# Canonical order (each is idempotent / re-runnable):
python -m src.system1.features.feature_pipeline --version 1.0.0   # MODEL-002
python -m src.system1.regime.hmm_regime                           # MODEL-003 (multi-minute on H1)
python -m src.system1.attribution.attribute                       # MODEL-004
python -m src.system1.vetting.vet --live                          # MODEL-005 (omit --live = log-only proposal)
python -m src.system1.gatekeeper.train --dry-run                  # MODEL-006 (dry-run = proposed_champion_*)
python -m src.system1.serializer.serialize                        # MODEL-007
python -m src.system1.scheduler.orchestrator                      # MODEL-009 evaluate triggers
python -m src.system1.scheduler.orchestrator --force              # force a full gated retrain+promote
```

**Safety design:** log-only/dry-run is the *default* for the two promotion-capable stages.
`vet` writes to `results/reports/proposed_*` unless `--live`; `gatekeeper.train --dry-run`
writes `proposed_champion_*` and never touches the live champion (global rule #1).

---

## 4. Results — code-level testing

Full suite:

```
125 passed in 7.77s   (14 test files across all 10 modules)
```

Coverage is meaningful — e.g. `test_no_smoothed_leak.py` asserts attribution never consumes the
leaked reporting label; `test_walk_forward.py` covers fold-boundary math; `test_serialize.py`
covers the checksum-mismatch abort path. All green.

Orchestrator run live (safe path, no trigger fired):

```
No retrain: no triggers → outcome: no_trigger_or_cooldown   ✅
(correct; today is not Sunday 00:00 UTC and metrics are healthy)
```

---

## 5. Results — business/logical level (live data)

The pipeline **has run end-to-end on real data**:

| Table | Rows |
|-------|------|
| `fact_market_prices` | 4,682,503 |
| `fact_market_regime_v2` | 842,241 (H1 HMM, H4 HMM, **D1 fell back to K-Means**) |
| `fact_trade_outcomes` | 134,520 |
| `fact_strategy_regime_attribution` | 640 |

**Final promoted output (2026-07-01):** of **10 strategies × 4 regimes = 80 candidate cells,
only 4 qualified**, and all four belong to a **single strategy** — `Range_Stochastic_Divergence`
(id 10):

| Regime | Variant | Sharpe | PF | Weight |
|--------|---------|--------|----|--------|
| Trending-Up | Range_Stochastic_Divergence@H1 | 1.01 | 1.84 | 1.0 |
| Trending-Down | Range_Stochastic_Divergence@H1 | 2.58 | 3.24 | 1.0 |
| Ranging | Range_Stochastic_Divergence@H1 | 3.80 | 2.94 | 0.99999992 |
| Ranging | Range_Stochastic_Divergence@H4 | 1.74 | 3.06 | **0.00000008** |
| High-Vol | *(none — STARVATION)* | — | — | — |

The retrain then promoted this bundle (all 4 gates passed: `regime_accuracy_ok`,
`non_empty_map`, `oos_uplift_ok`, `beats_incumbent`). The machinery works and is currently
shipping a live model.

---

## 6. Findings worth attention

### A. Weight-normalization starves the 2nd-best qualifier (likely a real bug)
`gates.normalized_weights` does `shifted = score − min(scores) + 1e-6`. The lowest-scoring
qualifier in a regime is *always* driven to ≈0 weight regardless of its own merit. Verified
against the live artifact: in **Ranging**, the H4 variant (Sharpe 1.74, PF 3.06 — genuinely
good) received weight **0.00000008**, i.e. it is published as "qualified" but gets effectively
no capital. With only 2 qualifiers this is winner-takes-all. Softmax or rank-based weighting
would fix it. **This is a logical flaw in the sizing contract handed to System 2.**

### B. Semantic mismatch: a *range* strategy is the sole winner in *trending* regimes
`Range_Stochastic_Divergence` qualifies as rank-1 in Trending-Up **and** Trending-Down. Either
the strategy is genuinely regime-robust, or the causal regime labels are not discriminating the
way their names imply — consistent with the prior finding that regimes are "cosmetic." Worth a
targeted look before trusting the regime→strategy routing.

### C. Concentration risk
The entire live model rests on one strategy at essentially one granularity (H1). Robust from a
*gate-strictness* standpoint, fragile from a portfolio standpoint. High-Vol has no coverage.

### D. D1 regime silently fell back to K-Means
The HMM failed its quality/accuracy gate on daily bars. That is the fallback working as
designed, but it means the "Gaussian HMM regime" claim only holds for H1/H4; daily regimes are
K-Means one-hot.

### E. The heavy remediation history is real and closed
The code carries `FIX-S1-001…006` guards (metrics sanity bounds, OOS gate made non-inert,
causal-vs-leaked labels, weight-collision post-condition, uplift gate now fails-closed). Each
has a matching test. Those bugs are fixed and defended, not lurking.

---

## 7. Recommended next step

The most actionable item is **Finding A** (weight-starvation math): trace it end-to-end and
replace the shift-by-floor normalization with softmax or rank-based weighting, with a test
asserting no qualified variant receives a near-zero allocation.

---

## 8. Due-diligence Q&A (2026-07-01)

Seven pointed questions about the regime→strategy mapping, answered against the code and the
latest artifacts (`results/reports/regime_discrimination_20260630T225156Z.json`). Every claim
below is cited to `file:line`.

> **Reframing first.** The latest discrimination run reports **`n_discriminating: 0` of 10
> strategies** on *both* the entry-only and dominant-over-life labels. The largest per-strategy
> win-rate spread across regimes is 0.075, below the `MATERIAL_SPREAD = 0.10` bar
> (`src/system1/attribution/discrimination.py:54`). So the regime→strategy mapping **is not a
> proven edge — it is cosmetic.** This directly reframes Q5 and Q6. Note this is a *different*
> question from vetting (§5): a cell can pass absolute gates (PF/Sharpe/DD) while its win rate
> does *not* vary by regime. Both facts hold simultaneously.

### Q1 — How was training data isolated from validation for this mapping?
Two mechanisms with **materially different rigor**:
- **Regime labels (`regime_causal`) are properly walk-forward.** Each fold fits a *fresh* HMM on
  train-only bars with a train-only scaler (`src/system1/regime/hmm_regime.py:326`
  `_fit_causal_model`), and inference is forward-only filtered `P(state_t | x_first..x_t)` over
  the fold-visible prefix (`filtered_posteriors`, `src/system1/regime/mapping.py:58-98`). No
  full-history fit leaks into a past label. This is FIX-S1-005.
- **Strategy parameters are NOT refit per fold.** They are fixed full-history at *default* values
  (no optimization — `src/layer0/persist_trade_outcomes.py:7`). Per
  `src/system1/validation/walk_forward.py:5-13`, "out-of-sample" here means only *the subset of
  trades whose metrics were not used in selection*. Because nothing was optimized there is no
  parameter overfit to leak — but this is a **weaker** sense of OOS than a re-optimized
  walk-forward. Do not describe the system as fully walk-forward-optimized.

### Q2 — Strictly-OOS walk-forward metrics the model has never seen?
Design is locked at `walk_forward.py:42-45`: `min_train = 36mo`, `step = 6mo`, `oos_window = 6mo`,
`mode = anchored`. A trade is OOS iff `entry_time >= series_start + 36mo` (`assign_oos`,
`walk_forward.py:156`). Attribution computes every gate metric on the OOS subset only
(`_oos_cell_metrics`, `attribute.py:167`). **Caveat:** the discrimination report (`n_trades:
134520`) is computed on **all** regime-tagged trades, *not* the OOS subset — the discrimination
path does not apply the OOS gate. So there is currently **no clean per-regime OOS win-rate
artifact on disk**. The OOS-only metrics live in
`results/state/strategy_regime_attribution.parquet` (per strategy × regime × granularity).

### Q3 — Exact spread / slippage / commission values?
The 134,520 outcomes were produced via `layer0/backtest_engine.py` (through
`persist_trade_outcomes.py`), so the applicable values are the `BacktestConfig` defaults
(`src/layer0/backtest_engine.py:41-43`):
- **spread = 1.0 pip** → subtracted as `spread_pips * 10.0` = $10/standard lot per trade
  (`_apply_friction`, `backtest_engine.py:121`)
- **slippage = 0.5 pip** → applied to the entry price, **entry only** (`backtest_engine.py:226`)
- **commission = 0.0**

Two caveats: commission is zero, and slippage is applied on entry but **not on exit**. A second,
**unused** cost model exists in `src/research/config.py` (ATR-fraction: spread 0.12–0.18 ATR,
slippage 0.05–0.20 ATR, commission 0.03 ATR round-turn) via `research/trade_simulator.py` — it
did **not** generate these outcomes. Do not conflate the two.

### Q4 — How does the strategy handle order execution at regime-transition boundaries?
It doesn't, and by design. System 1 (this repo, the Brain) **does not place orders** — execution
is System 2 (the Hand). Here, regime is only a *point-in-time tag at entry*:
`merge_asof(..., direction="backward")` assigns the causal label of the most recent bar
`<= entry_time` (`attribute.py:139`). `persistence_smooth` (3-bar debounce, `mapping.py:101`)
applies to the *reporting* label only; attribution uses raw `regime_causal`. Since 0/10
strategies discriminate by regime, **no regime-transition execution logic was built** — there is
nothing to gate on.

### Q5 — Why does range-bound Strategy 10 outperform trend strategies in Trending regimes?
It doesn't — that reading is an artifact. Strategy 10's win rates (report lines 131–143) are
**High-Vol 0.75, Ranging 0.72, Trending-Down 0.74, Trending-Up 0.67** — it wins ~70% in *every*
regime, with `chi2_p = 0.611` and spread 0.075 (no statistically or economically significant
difference across regimes). Its high *absolute* win rate is a property of the strategy (a
tight-target / low-RR profile — **win rate ≠ PnL**), not evidence of trend-following skill. It is
computed on **N = 892 trades** (~0.7% of the dataset), so cell-level regime differences are noise.
Ranking it above trend strategies 7–9 (~0.47–0.49 win rate) conflates win rate with expectancy.

### Q6 — Total trade count N per regime?
Per-strategy totals (all entry-tagged trades) from the report sum exactly to 134,520:

| Strategy | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|----------|---|---|---|---|---|---|---|---|---|----|
| N | 13,128 | 6,299 | 6,299 | 24,131 | 17,315 | 11,146 | 13,942 | 13,942 | 27,426 | 892 |

The report gives win-rate *by* regime but **not the per-regime cell N** (the denominators). Those
live in the attribution parquet / `regime_distribution` field of the attribution report, and the
OOS-gated counts differ from these totals. The per-(strategy × regime) N — including how thin the
trend cells are for S10 — is the number that determines whether any win-rate spread is
trustworthy; it must be pulled from the parquet or DB.

### Q7 — Exact lines where data leakage is prevented in the feature store?
- **Trailing-only feature construction** — `src/system1/features/definitions.py`:
  `returns_1 = log(close/close.shift(1))` (line 69); ATR/ADX warm-up regions explicitly nulled
  (lines 73, 78); rolling channel/vol use `min_periods == window` so no partial-window peeking
  (lines 82-90). Contract at lines 1-6: "Every feature at bar `t` depends only on bars `<= t`."
- **Per-instrument windows** — `feature_pipeline.py:88-97` (`_compute_all`) groups by `asset_id`
  so rolling windows never cross instruments.
- **Causal regime inference** — `mapping.py:58-98` (`filtered_posteriors`), forward-only
  recursion; docstring lines 66-71 explain it deliberately avoids `predict_proba`/Viterbi
  smoothing "which leak the future into a past bar's label."
- **Walk-forward train/OOS split** — `walk_forward.py:156` (`assign_oos`) and the train-only
  refit at `hmm_regime.py:326`.

There is **no explicit anti-leakage guard in `services/`** — Layer 5 services are read-only
telemetry. Leakage prevention lives entirely in the feature-definition and regime-inference layer.

### Bottom line
The regime-conditioning mapping is not backed by discriminating evidence (0/10, consistent with
prior FIX-S1-003 / FIX-S1-005 findings); the "OOS" is trade-subset OOS on *unoptimized* params
rather than a re-optimized walk-forward; and the Strategy 10 comparison is a win-rate artifact on
892 trades. The honest next step is to extract the true per-(strategy × regime) OOS counts and
metrics from `strategy_regime_attribution.parquet`.

---

# Appendix — Whole-Repo Folder Overview (2026-07-01)

*Verified against the actual on-disk filesystem, not solely `CLAUDE.md`. Added to complement
the System-1 deep-dive above with a broad map of every folder in the repo.*

## Project overview

**Scalable Brain** is an institutional-grade quantitative Forex trading pipeline. It qualifies
strategies against historical data, detects market regimes, generates signals, filters them
through an ML gatekeeper, and executes trades via OANDA — with full auditability. Stack: Python
3.12, PostgreSQL 16 + TimescaleDB (`ForexBrainDB` on `localhost:5432`), XGBoost/LightGBM, FinBERT
NLP, FastAPI + React dashboard.

**Key finding:** the repo is mid-migration between **two architectures** — the legacy **8-layer**
model documented in `CLAUDE.md` (`src/layer0…layer7`), and the newer **System 1 / 2 / 3** model
(the active work; current branch `fix/s1-integration`, commits `FIX-S1-*`), which `CLAUDE.md`
does not document.

## Source folders (`src/`)

| Folder | Role | Produces |
|--------|------|----------|
| `layer0/` | Strategy qualification / backtesting | `results/reports/*.json+md`, `results/sql/layer2_*.sql`, `results/state/qualification_progress.json` |
| `layer1_regime/` | K-Means market regime detection | `Fact_Market_Regime_V2` rows |
| `layer2_signals/` | Vectorized signal engine | `Fact_Signals` rows |
| `layer3_ml/` | XGBoost/LightGBM gatekeeper training | `models/champion_*.pkl`, `champion_manifest.json` |
| `layer4_executor/` | Live execution orchestrator | `Fact_Live_Trades`, `Fact_Execution_Log` |
| `layer5/` | Telemetry API (FastAPI) + React dashboard | Read-only observability (port 8001 / Vite 5173) |
| `layer6_auditor/` | Post-trade outcome reconciliation | Patches `Actual_Outcome` in `Fact_Live_Trades` |
| `layer7/` | OANDA broker executor (Kelly sizing) | Live orders |
| `nlp/` | FinBERT macro sentiment | `Fact_Macro_Events` |
| **`common/`** | **Shared infra (undocumented in CLAUDE.md):** `db.py` (canonical SQLAlchemy engine), `storage/` (local_fs + GCS backends), `queue/` (durable local queue) | — |
| **`system1/`** | **New "System 1 — Model Building" pipeline (undocumented in CLAUDE.md).** MODEL-001…010 (see deep-dive above) | `model-artifacts/` bundles, scored-signal queue messages |
| `research/` | Backtesting research (Monte Carlo, walk-forward, multi-asset) | Ad-hoc analysis |
| `sql/` | Migrations, TimescaleDB setup, cleanup | Schema DDL |
| `todo/` | Notes (`layer0-3.txt`) | — |

Note: `system1/` uses an **HMM regime model** (`hmm_model.joblib`) — a different approach from
`layer1`'s K-Means, another sign of the architecture transition.

## Top-level folders

### Documented / expected

- `docs/` — design, database, reference, research + `implementation-roadmap/` (system-1/2/3) and
  `proposed-fixes/` (audit prompts per system)
- `frontend/` — static HTML documentation portal
- `results/` — run artifacts (reports, sql, state)
- `models/` — ML artifacts (champion + legacy + `proposed_champion_*` + `hmm_model.joblib`)
- `shell/`, `init-db/`, `logs/`, `testing/`, `archieved/`

### Undocumented in CLAUDE.md (verified present)

- `contracts/` — **JSON-Schema contracts** between systems: `regime-map-contract.json`,
  `signal-message-contract.json` (System 1 → System 3), `weights-contract.json`
- `feature-store/` — **versioned Parquet feature store**
  (`1.0.0/granularity=D1|H4|W1/year=YYYY/…`) with `lineage.json` + `schema.json`
- `model-artifacts/` — **timestamped, checksummed model bundles** (HMM model, regime→strategy
  map, strategy weights; each with `.sha256` + `.meta.json`) plus `latest.json` promotion pointer
- `mlruns/` — **MLflow** experiment tracking
- (`contracts/`, `feature-store/`, `model-artifacts/`, `mlruns/` are all part of the System-1
  build pipeline)
- `secrets/` — `system1-rw.json` (service credentials — handle with care)
- `configuration/` — `postgresql_connection_details.txt`
- `backups/` — DB dumps (`ForexBrainDB_pre_timescaledb_*.dump`, phase2 tarballs)
- `proposedchanges/` — migration prompt docs (Phase 2/3)
- `localhost/` — a stray `localhost.sqlproj` (leftover SQL Server project file)

## Observations worth flagging

1. **CLAUDE.md is stale** — it describes only the 8-layer architecture and omits the entire
   `system1/`, `common/`, `contracts/`, `feature-store/`, `model-artifacts/`, and `mlruns/`
   build system, which is where the current branch's active work lives.
2. **Two parallel regime approaches** coexist: K-Means (`layer1`) vs HMM (`system1/regime`).
3. `localhost/localhost.sqlproj` and `backups/phase2/*sqlserver*` are SQL-Server leftovers from
   the completed PostgreSQL migration — candidate cleanup. The honest next step for these questions is to extract the true per-(strategy ×
regime) OOS counts and metrics from `strategy_regime_attribution.parquet`.
