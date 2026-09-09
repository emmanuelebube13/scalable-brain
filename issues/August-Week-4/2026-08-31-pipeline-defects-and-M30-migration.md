# 2026-08-31 — Pipeline Defects and M30 Strategy Migration Plan

## Goal Description
Address three critical defects in the signal generation pipeline that currently cause missed signals and silent ingest stalls. Simultaneously, migrate four specific research strategies to the `M30` (30-minute) timeframe to enable high-frequency signal generation (multiple runs per day). Finally, outline the end-to-end retraining and verification orchestration needed to put these changes live.

## User Review Required
> [!WARNING]
> **M30 Data Footprint**
> Adding `M30` to the `DEFAULT_GRANULARITIES` in `multi_timeframe_ingest.py` will increase the number of candles downloaded and stored during the daily ingest cron jobs. Please confirm this database growth is acceptable.

> [!IMPORTANT]
> **Heartbeat Tolerance Limits**
> We are tightening the ingest heartbeat check in `heartbeat.py`. H1 and M30 will now fail the health check if data is older than ~2.5 hours and ~1.5 hours respectively. This will make your dashboards more accurate but more sensitive to pipeline delays.

## Open Questions
> [!NOTE]
> Do you want the `M30` data to be backfilled for a specific period (e.g., last 3 years) before running the retrain? Or is standard incremental backfill (which might take a while to cover 3 years for M30) acceptable? *For a 3-year lookback, we may need a manual bulk ingest run via `cron_oanda_ingest_saturday.sh` or a dedicated backfill command.*

## Proposed Changes

---

### Component: Monitoring & Pipeline Heartbeats
Tighten the SLA checks to prevent silent stalls on intraday timeframes.

#### [MODIFY] `src/monitoring/heartbeat.py`
- Refactor `check_prices` to query and evaluate `M30`, `H1`, `H4`, and `D1` freshness independently.
- Apply tighter `grace_hours` for intraday timeframes instead of grouping them under a single blanket 26h threshold.

---

### Component: Signal Watcher & Build Logic
Fix the `rn=1` silent loss and the wrong-clock guard.

#### [MODIFY] `src/signals/watcher.py`
- Add `"M30": timedelta(hours=1, minutes=15)` to `LATENCY_THRESHOLDS`.
- Update `get_new_closed_bars` SQL query to include `f.granularity` in the `SELECT` list to fix the dead wrong-clock guard.
- Change `rn = 1` to `rn <= 100 ORDER BY timestamp ASC` to process all missed bars chronologically during catch-up.
- Update the python loop to properly advance the `new_state` for multiple bars without skipping.

#### [MODIFY] `src/signals/run.py`
- Update `granularities = ["H1", "H4", "D1"]` to include `"M30"`.

---

### Component: Data Ingestion
Enable `M30` data fetching.

#### [MODIFY] `src/ingestion/multi_timeframe_ingest.py`
- Add `"M30"` to `DEFAULT_GRANULARITIES`.

---

### Component: Strategy Metadata (M30 Migration)
Modify the metadata to operate on the 30-minute chart.

#### [MODIFY] `src/layer0/strategies/research/amazing_crossover.py`
- Update `primary_granularity="M30"` and `granularities=["M30"]`.
#### [MODIFY] `src/layer0/strategies/research/xard_ma_cross_daily_open.py`
- Update `primary_granularity="M30"` and `granularities=["M30"]`.
#### [MODIFY] `src/layer0/strategies/research/ema_cross_h4_filter_bot.py`
- Update `primary_granularity="M30"` and keep context granularities (if any).
#### [MODIFY] `src/layer0/strategies/research/adx_trend_pullback_ea.py`
- Update `primary_granularity="M30"` and `granularities=["M30"]`.

---

## Verification Plan

### Automated Tests
Run the unit test suites to ensure health checks and watcher modifications do not break existing invariants:
```bash
python -m pytest src/signals/tests/
python -m pytest src/monitoring/tests/
```

### Manual Verification
1. **Data Ingest**: Run `python -m src.ingestion.multi_timeframe_ingest` to fetch M30 data and verify it populates `fact_market_prices`.
2. **Model Retrain**: Run `shell/cron_system1_retrain.sh` to execute the full orchestrator retrain, ensuring the M30 strategies get qualified and the new `latest.json` model set is successfully published to GCS.
3. **Signal Generation**: Run `python -m src.signals.run --once` to manually evaluate the new bars and ensure M30 signals are built and published correctly.
