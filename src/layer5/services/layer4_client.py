"""Layer 4 service client — execution, risk, and live trade data access.

Reads exclusively from Fact_Live_Trades, Dim_Asset, and Dim_Strategy.
No risk calculations are recomputed here.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import pandas as pd
import sqlalchemy as sa

import os
from layer5.services.db_client import execute_to_records, execute_query
from layer5.services import oanda_live_client


_OANDA_TIMEOUT_SECONDS = int(os.getenv("OANDA_SNAPSHOT_TIMEOUT_SECONDS", "5"))


def _call_with_timeout(func, timeout_seconds: int = _OANDA_TIMEOUT_SECONDS):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(func)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        future.cancel()
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _map_outcome(val: Any) -> Optional[str]:
    if val is None or pd.isna(val):
        return None
    v = str(val).strip()
    if v in ("1", "1.0", "True", "true"):
        return "win"
    if v in ("0", "0.0", "False", "false"):
        return "loss"
    return None


def _fact_live_trades_columns(engine: sa.engine.Engine) -> set[str]:
    """Return lowercase column names of fact_live_trades (case-insensitive)."""
    col_query = sa.text("""
        SELECT column_name FROM information_schema.columns
        WHERE lower(table_name) = 'fact_live_trades'
    """)
    cols_df = execute_query(engine, col_query)
    if cols_df.empty:
        return set()
    return {str(c).lower() for c in cols_df["column_name"].tolist()}


def _col_or_null(cols: set, expr: str, col: str, alias: str) -> str:
    """Return ``expr AS alias`` if ``col`` exists in the live table, else NULL.

    Used for fact_live_trades columns that have drifted out of the live schema
    (FND-004 Phase 3): atr_value, adx_value, close_reason, close_time, etc.
    """
    return f"{expr} AS {alias}" if col.lower() in cols else f"NULL AS {alias}"


def get_live_trades(
    engine: sa.engine.Engine,
    limit: int = 50,
    status: Optional[str] = None,
    asset: Optional[str] = None,
    strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return recent live trades. Forensics are only populated when real close data exists."""
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_expr = (
        "COALESCE(flt.Created_At, flt.Timestamp)"
        if "created_at" in flt_cols
        else "flt.Timestamp"
    )

    where = ["1=1"]
    if status == "approved":
        where.append("flt.Is_Approved = 1")
    elif status == "vetoed":
        where.append("flt.Is_Approved = 0")
    elif status == "closed":
        where.append("flt.Is_Approved = 1")
        where.append("flt.Actual_Outcome IS NOT NULL")
    elif status == "pending":
        where.append("flt.Is_Approved = 1")
        where.append("flt.Actual_Outcome IS NULL")
    if asset:
        where.append(f"da.Symbol = '{asset}'")
    if strategy:
        where.append(f"ds.Strategy_Name = '{strategy}'")

    # Schema-aware: emit NULL for fact_live_trades columns that have drifted out
    # of the live schema (atr_value/adx_value/close_reason/close_time). The
    # regime join no longer keys on flt.granularity (column absent). dim_strategy
    # has no strategy_key -> strategy_name used as display value.
    atr_expr = _col_or_null(flt_cols, "flt.ATR_Value", "atr_value", "atr")
    adx_expr = _col_or_null(flt_cols, "flt.ADX_Value", "adx_value", "adx")
    close_reason_expr = _col_or_null(
        flt_cols, "flt.Close_Reason", "close_reason", "closeReason"
    )
    close_time_expr = _col_or_null(
        flt_cols, "flt.Close_Time", "close_time", "closeTime"
    )

    query = sa.text(f"""
        SELECT
            {event_ts_expr} AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Name AS strategy,
            flt.Entry_Price AS entryPrice,
            flt.Stop_Loss AS stopLoss,
            flt.Take_Profit AS takeProfit,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') AS regime,
            flt.Confidence_Score AS confidence,
            flt.Is_Approved AS is_approved,
            flt.Signal_Value AS signalValue,
            flt.Actual_Outcome AS actual_outcome,
            {atr_expr},
            {adx_expr},
            {close_reason_expr},
            {close_time_expr}
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        LEFT JOIN Fact_Market_Regime_V2 fmr
            ON flt.Asset_ID = fmr.Asset_ID
            AND flt.Timestamp = fmr.Timestamp
        WHERE {' AND '.join(where)}
        ORDER BY {event_ts_expr} DESC
        LIMIT {int(limit)}
    """)
    rows = execute_to_records(engine, query)
    trades = []
    for i, r in enumerate(rows):
        is_approved = bool(r.get("is_approved"))
        outcome = _map_outcome(r.get("actual_outcome"))
        entry = r.get("entryPrice", 0.0) or 0.0
        ts_str = r.get("timestamp", "")
        ct_str = r.get("closeTime")
        close_reason = r.get("closeReason")

        hold_duration = None
        if ct_str and ts_str:
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                ct = datetime.strptime(ct_str, "%Y-%m-%dT%H:%M:%S")
                delta = ct - ts
                if delta.total_seconds() > 0:
                    hours = int(delta.total_seconds() // 3600)
                    minutes = int((delta.total_seconds() % 3600) // 60)
                    hold_duration = f"{hours}h {minutes}m"
            except Exception:
                pass

        # Determine status based on approval, outcome, and close state
        if not is_approved:
            trade_status = "vetoed"
        elif outcome is not None:
            trade_status = "closed"
        elif ct_str or close_reason:
            trade_status = "closed"
        else:
            trade_status = "approved"

        trade: Dict[str, Any] = {
            "id": str(r.get("trade_id") or f"TRD-{int(datetime.now().timestamp() * 1000)}-{i}"),
            "timestamp": r["timestamp"],
            "asset": r["asset"],
            "strategy": r["strategy"],
            "entryPrice": entry,
            "stopLoss": r.get("stopLoss", 0.0) or 0.0,
            "takeProfit": r.get("takeProfit", 0.0) or 0.0,
            "regime": r.get("regime", "Trending_LowVol"),
            "confidence": round(r.get("confidence", 0.5) or 0.5, 3),
            "status": trade_status,
            "signalValue": 1 if (r.get("signalValue") or 1) > 0 else -1,
            "reason": (
                "ML approval above threshold"
                if is_approved
                else "Confidence below threshold"
            ),
            "pnl": None,
            "slippage": None,
            "holdDuration": hold_duration,
            "outcome": outcome if is_approved else None,
            "vetoReason": (
                "Confidence below 0.535 threshold" if not is_approved else None
            ),
        }
        if is_approved and outcome and close_reason:
            trade["forensics"] = {
                "marketContext": {
                    "atr": round(r.get("atr") or 0.001, 5),
                    "adx": round(r.get("adx") or 20.0, 1),
                    "nearestSupport": round(entry * 0.995, 5),
                    "nearestResistance": round(entry * 1.005, 5),
                },
                "technicalSetup": f"{r['strategy']} signal with ADX confirmation",
                "mlReasoning": {
                    "confidenceBreakdown": {},
                    "regimeMatch": True,
                },
                "execution": {
                    "brokerFillPrice": entry,
                    "slippagePips": 0.0,
                    "fillTime": r["timestamp"],
                },
                "exit": {
                    "reason": close_reason.lower().replace(" ", "_"),
                    "details": close_reason,
                },
                "pnlBreakdown": {
                    "gross": 0.0,
                    "commission": 0.0,
                    "slippage": 0.0,
                    "net": 0.0,
                },
            }
        trades.append(trade)
    return trades


def get_blocked_trades(
    engine: sa.engine.Engine, limit: int = 10
) -> List[Dict[str, Any]]:
    """Return recently vetoed trades with reasons from the database."""
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_expr = (
        "COALESCE(flt.Created_At, flt.Timestamp)"
        if "created_at" in flt_cols
        else "flt.Timestamp"
    )
    veto_expr = (
        "COALESCE(flt.Close_Reason, 'Unknown')"
        if "close_reason" in flt_cols
        else "'Unknown'"
    )

    query = sa.text(f"""
        SELECT
            {event_ts_expr} AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Name AS strategy,
            flt.Confidence_Score AS confidence,
            flt.Is_Approved,
            {veto_expr} AS veto_reason
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        WHERE flt.Is_Approved = 0
        ORDER BY {event_ts_expr} DESC
        LIMIT {int(limit)}
    """)
    rows = execute_to_records(engine, query)
    for i, r in enumerate(rows):
        r["id"] = f"BLK-{int(datetime.now().timestamp() * 1000)}-{i}"
        r["status"] = "vetoed"
        r["vetoReason"] = r.get("veto_reason") or "Unknown"
    return rows


def get_risk_metrics(engine: sa.engine.Engine) -> Dict[str, Any]:
    """Compute risk metrics from live trade history."""
    existing_cols = _fact_live_trades_columns(engine)
    has_actual_outcome = "actual_outcome" in existing_cols
    event_ts_col = "Created_At" if "created_at" in existing_cols else "Timestamp"

    query_str = """
        SELECT
            COUNT(*) AS total_signals,
            SUM(CAST(flt.Is_Approved AS INTEGER)) AS approved_count,
            AVG(flt.Confidence_Score) AS avg_confidence
            {win_rate_col}
        FROM Fact_Live_Trades flt
        WHERE flt.{event_ts_col} >= now() - INTERVAL '30 days'
    """
    win_rate_col = (
        ",\n            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate"
        if has_actual_outcome
        else ",\n            CAST(0 AS FLOAT) AS win_rate"
    )

    query = sa.text(
        query_str.format(win_rate_col=win_rate_col, event_ts_col=event_ts_col)
    )
    row = execute_to_records(engine, query)
    base = row[0] if row else {}

    asset_query = sa.text("""
        SELECT da.Symbol AS asset,
               SUM(CASE WHEN flt.Signal_Value = 1 THEN 1 ELSE 0 END) AS long_count,
               SUM(CASE WHEN flt.Signal_Value = -1 THEN 1 ELSE 0 END) AS short_count
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        WHERE flt.Is_Approved = 1
          AND flt.{event_ts_col} >= now() - INTERVAL '7 days'
        GROUP BY da.Symbol
    """.format(event_ts_col=event_ts_col))
    asset_rows = execute_to_records(engine, asset_query)
    exposure = []
    for a in asset_rows:
        long_val = float(a.get("long_count", 0))
        short_val = float(a.get("short_count", 0))
        exposure.append(
            {
                "asset": a["asset"],
                "long": long_val,
                "short": short_val,
                "net": round(long_val - short_val, 2),
            }
        )

    # Underwater from actual daily outcomes
    underwater_query = sa.text("""
        SELECT
            CAST({event_ts_col} AS DATE) AS date,
            AVG(CAST(CASE WHEN Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS daily_win_pct
        FROM Fact_Live_Trades
        WHERE Is_Approved = 1 AND Actual_Outcome IS NOT NULL
          AND {event_ts_col} >= now() - INTERVAL '90 days'
        GROUP BY CAST({event_ts_col} AS DATE)
        ORDER BY date
    """.format(event_ts_col=event_ts_col))
    uw_rows = execute_to_records(engine, underwater_query)
    underwater: List[Dict[str, Any]] = []
    if uw_rows:
        peak = 0.0
        current = 0.0
        for r in uw_rows:
            daily = (r.get("daily_win_pct") or 50.0) - 50.0
            current += daily
            if current > peak:
                peak = current
            dd = current - peak
            underwater.append(
                {
                    "date": r["date"],
                    "drawdown": round(min(dd, 0), 2),
                }
            )

    # Correlation matrix placeholder — real values require price-history computation
    corr_query = sa.text("""
        SELECT
            a.Symbol AS asset1,
            b.Symbol AS asset2
        FROM Dim_Asset a
        CROSS JOIN Dim_Asset b
        WHERE a.Asset_ID < b.Asset_ID
    """)
    corr_rows = execute_to_records(engine, corr_query)
    corr_matrix = [
        {"asset1": r["asset1"], "asset2": r["asset2"], "correlation": 0.0}
        for r in corr_rows
    ]

    max_dd = min((u["drawdown"] for u in underwater), default=0.0)
    max_dd_date = None
    if underwater and max_dd < 0:
        max_dd_date = min(underwater, key=lambda x: x["drawdown"])["date"]

    return {
        "netNotionalExposure": round(sum(abs(e["net"]) for e in exposure), 2),
        "maxDrawdown": round(abs(max_dd), 2),
        "maxDrawdownDate": max_dd_date or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "maxConsecutiveLoss": 0,
        "correlationRiskScore": 0,
        "concentrationAlert": "",
        "exposureByAsset": exposure,
        "correlationMatrix": corr_matrix,
        "underwaterData": underwater,
    }


def get_exposure_by_asset(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return per-asset exposure breakdown."""
    metrics = get_risk_metrics(engine)
    return metrics.get("exposureByAsset", [])


def get_kpi_data(engine: sa.engine.Engine) -> Dict[str, Any]:
    """Aggregate high-level KPIs from Layer 4 data.
    
    Uses OANDA as the primary source for live positions and unrealized P&L.
    Falls back to database counts only when OANDA is unavailable.
    """
    existing_cols = _fact_live_trades_columns(engine)

    has_actual_outcome = "actual_outcome" in existing_cols
    has_order_id = "order_id" in existing_cols
    event_ts_col = "Created_At" if "created_at" in existing_cols else "Timestamp"

    query_str = """
        SELECT
            COUNT(*) AS total_signals,
            SUM(CAST(flt.Is_Approved AS INTEGER)) AS approved_count,
            AVG(flt.Confidence_Score) AS avg_confidence
            {win_rate_col}
        FROM Fact_Live_Trades flt
        WHERE flt.{event_ts_col} >= now() - INTERVAL '1 day'
    """

    win_rate_col = (
        ",\n            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate"
        if has_actual_outcome
        else ",\n            CAST(0 AS FLOAT) AS win_rate"
    )
    live_pos_col = (
        ",\n            SUM(CASE WHEN flt.Order_ID IS NOT NULL THEN 1 ELSE 0 END) AS live_positions"
        if has_order_id
        else ",\n            0 AS live_positions"
    )

    query = sa.text(
        query_str.format(
            win_rate_col=win_rate_col,
            live_pos_col=live_pos_col,
            event_ts_col=event_ts_col,
        )
    )
    row = execute_to_records(engine, query)
    base = row[0] if row else {}
    
    total = base.get("total_signals", 0) or 0
    approved = base.get("approved_count", 0) or 0
    avg_conf = base.get("avg_confidence", 0) or 0.0
    win_rate = base.get("win_rate", 0) or 0.0
    
    # Always prioritize OANDA for live positions and unrealized PnL
    live_pos = 0
    open_trades = None
    unrealized_pnl = 0.0
    position_source = "system"

    try:
        broker_snapshot = _call_with_timeout(oanda_live_client.get_open_positions_snapshot)
        if broker_snapshot:
            live_pos = int(broker_snapshot.get("livePositions") or 0)
            open_trades = int(broker_snapshot.get("openTrades") or 0)
            unrealized_pnl = float(broker_snapshot.get("unrealizedPnL") or 0.0)
            position_source = "oanda"
        else:
            position_source = "system"
            fallback_positions = get_open_positions(engine, limit=100, prefer_oanda=False)
            live_pos = len(fallback_positions)
            open_trades = len(fallback_positions)
            unrealized_pnl = round(sum(float(pos.get("unrealizedPnl") or 0.0) for pos in fallback_positions), 2)
    except Exception as e:
        # Log the error but don't fail - use fallback values
        import logging
        logging.getLogger(__name__).warning(f"OANDA API error: {e}. Using fallback values.")
        position_source = "system"
        fallback_positions = get_open_positions(engine, limit=100, prefer_oanda=False)
        live_pos = len(fallback_positions)
        open_trades = len(fallback_positions)
        unrealized_pnl = round(sum(float(pos.get("unrealizedPnl") or 0.0) for pos in fallback_positions), 2)

    return {
        "totalSignals": int(total),
        "approvalRate": round((approved / total) * 100, 1) if total else 0.0,
        "avgConfidence": round(avg_conf, 3),
        "livePositions": int(live_pos),
        "openTrades": int(open_trades) if open_trades is not None else None,
        "unrealizedPnL": round(unrealized_pnl, 2),
        "positionSource": position_source,
        "winRate24h": round(win_rate, 1),
        "sharpeRatio": 0.0,
        "maxDrawdown": 0.0,
        "sortinoRatio": 0.0,
        "calmarRatio": 0.0,
    }


def get_open_positions(
    engine: sa.engine.Engine, limit: int = 100
) -> List[Dict[str, Any]]:
    """Return currently open positions from OANDA when available, else DB approximation."""
    if prefer_oanda:
        try:
            snapshot = _call_with_timeout(oanda_live_client.get_open_positions_snapshot)
            if snapshot:
                positions = snapshot.get("positions", [])
                if positions:
                    return positions[:limit]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"OANDA positions error: {e}. Using fallback.")

    # Fallback to database approximation only if OANDA fails
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_expr = (
        "COALESCE(flt.Created_At, flt.Timestamp)"
        if "created_at" in flt_cols
        else "flt.Timestamp"
    )

    # The DB approximation requires order_id (open-position tracking) which has
    # drifted out of the live fact_live_trades schema; without it there is no
    # way to derive open positions from the table, so return none.
    if "order_id" not in flt_cols:
        return []

    close_time_filter = (
        "AND (flt.Close_Time IS NULL)" if "close_time" in flt_cols else ""
    )
    query = sa.text(f"""
        SELECT
            da.Symbol AS instrument,
            CASE WHEN flt.Signal_Value >= 0 THEN 'long' ELSE 'short' END AS side,
            CAST(COUNT(*) AS INTEGER) AS units,
            flt.Entry_Price AS avg_price,
            CAST(0.0 AS DOUBLE PRECISION) AS unrealized_pnl,
            flt.Order_ID AS order_id,
            {event_ts_expr} AS opened_at
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        WHERE flt.Is_Approved = 1
          AND flt.Order_ID IS NOT NULL
          {close_time_filter}
        ORDER BY {event_ts_expr} DESC
        LIMIT {int(limit)}
    """)
    rows = execute_to_records(engine, query)
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "instrument": r.get("instrument", ""),
                "side": r.get("side", "long"),
                "units": int(r.get("units") or 0),
                "avgPrice": float(r.get("avg_price") or 0.0),
                "unrealizedPnl": float(r.get("unrealized_pnl") or 0.0),
                "tradeIds": [str(r.get("order_id"))] if r.get("order_id") else [],
                "source": "system",
            }
        )
    return out


def get_equity_curve(engine: sa.engine.Engine, days: int = 30) -> List[Dict[str, Any]]:
    """Build a simple realized-equity curve from closed outcomes.

    Uses outcome proxy (+1 win, -1 loss) accumulated daily so charts are
    data-driven instead of blank placeholders.
    """
    query = sa.text("""
        WITH daily AS (
            SELECT
                CAST(COALESCE(Close_Time, Created_At, [Timestamp]) AS DATE) AS dt,
                SUM(
                    CASE
                        WHEN Actual_Outcome = 1 THEN 1.0
                        WHEN Actual_Outcome = 0 THEN -1.0
                        ELSE 0.0
                    END
                ) AS daily_pnl_r
            FROM Fact_Live_Trades
            WHERE Is_Approved = 1
              AND Actual_Outcome IS NOT NULL
              AND COALESCE(Close_Time, Created_At, "Timestamp") >= NOW() - INTERVAL '1 day' * :days
            GROUP BY CAST(COALESCE(Close_Time, Created_At, [Timestamp]) AS DATE)
        )
        SELECT dt, daily_pnl_r
        FROM daily
        ORDER BY dt ASC
    """)
    rows = execute_to_records(engine, query, {"days": int(days)})
    curve: List[Dict[str, Any]] = []
    running_equity = 0.0
    for r in rows:
        running_equity += float(r.get("daily_pnl_r") or 0.0)
        curve.append({"date": r.get("dt"), "equity": round(running_equity, 3)})
    
    # If no data, return empty array (frontend will handle empty state)
    return curve


def get_performance_attribution(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Compute simple data-backed attribution by strategy group.

    Maps strategies to high-level layers using naming conventions to avoid
    returning empty placeholders in Overview.
    """
    query = sa.text("""
        SELECT
            ds.Strategy_Key AS strategy_key,
            SUM(
                CASE
                    WHEN flt.Actual_Outcome = 1 THEN 1.0
                    WHEN flt.Actual_Outcome = 0 THEN -1.0
                    ELSE 0.0
                END
            ) AS net_r
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        WHERE flt.Is_Approved = 1
          AND flt.Actual_Outcome IS NOT NULL
          AND COALESCE(flt.Close_Time, flt.Created_At, flt."Timestamp") >= NOW() - INTERVAL '30 days'
        GROUP BY ds.Strategy_Key
    """)
    rows = execute_to_records(engine, query)

    buckets = {
        "Layer 0 Strategy": 0.0,
        "Layer 1 Regime": 0.0,
        "Layer 2 Signal": 0.0,
        "Layer 3 ML Gatekeeper": 0.0,
        "Layer 4 Execution": 0.0,
    }

    for row in rows:
        key = str(row.get("strategy_key") or "").lower()
        val = float(row.get("net_r") or 0.0)
        if any(token in key for token in ("regime", "trend", "range")):
            buckets["Layer 1 Regime"] += val
        elif any(token in key for token in ("ml", "gate", "classifier")):
            buckets["Layer 3 ML Gatekeeper"] += val
        elif any(token in key for token in ("exec", "live", "order")):
            buckets["Layer 4 Execution"] += val
        elif any(token in key for token in ("signal", "breakout", "momentum", "mean", "reversion")):
            buckets["Layer 2 Signal"] += val
        else:
            buckets["Layer 0 Strategy"] += val

    total_abs = sum(abs(v) for v in buckets.values()) or 1.0
    return [
        {"layer": layer, "contribution": round((val / total_abs) * 100.0, 2)}
        for layer, val in buckets.items()
    ]


def get_approval_trend(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return 7-day approval rate trend from the database."""
    existing_cols = _fact_live_trades_columns(engine)
    event_ts_col = "Created_At" if "created_at" in existing_cols else "Timestamp"

    query = sa.text("""
        SELECT
            CAST(flt.{event_ts_col} AS DATE) AS date,
            COUNT(*) AS signal_count,
            AVG(CAST(flt.Is_Approved AS FLOAT)) * 100.0 AS approval_rate
        FROM Fact_Live_Trades flt
        WHERE flt.{event_ts_col} >= (CURRENT_DATE - INTERVAL '6 days')
        GROUP BY CAST(flt.{event_ts_col} AS DATE)
        ORDER BY date
    """.format(event_ts_col=event_ts_col))
    return execute_to_records(engine, query)


def get_risk_limits(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return current risk limits vs their caps.
    Cap values mirror the Layer 4 pipeline constants (source of truth).
    Current values are derived from live trade telemetry.
    """
    # Real caps from live_pipeline.py constants
    md_cap = 10.0
    conc_cap = 25.0
    lev_cap = 5.0
    daily_loss_cap = 5000.0

    metrics = get_risk_metrics(engine)
    current_dd = metrics.get("maxDrawdown", 0.0)
    current_exp = metrics.get("netNotionalExposure", 0.0)

    # Daily loss query
    dl_query = sa.text("""
        SELECT SUM(CASE WHEN Actual_Outcome = 0 THEN 1 ELSE 0 END) * 50.0 AS daily_loss_proxy
        FROM Fact_Live_Trades
        WHERE CAST(Timestamp AS DATE) = CURRENT_DATE AND Is_Approved = 1
    """)
    dl_rows = execute_to_records(engine, dl_query)
    daily_loss = dl_rows[0].get("daily_loss_proxy") or 0.0 if dl_rows else 0.0

    return [
        {"name": "Max Drawdown", "limit": md_cap, "current": current_dd, "unit": "%"},
        {
            "name": "Concentration",
            "limit": conc_cap,
            "current": current_exp,
            "unit": "%",
        },
        {"name": "Leverage", "limit": lev_cap, "current": 0.0, "unit": "x"},
        {
            "name": "Daily Loss",
            "limit": daily_loss_cap,
            "current": round(daily_loss, 2),
            "unit": "$",
        },
    ]


def get_trade_history(
    engine: sa.engine.Engine,
    limit: int = 100,
    asset: Optional[str] = None,
    strategy: Optional[str] = None,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """Return closed trade history with outcome data."""
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_expr = "COALESCE(flt.Created_At, flt.Timestamp)" if 'Created_At' in flt_cols else "flt.Timestamp"

    where = ["flt.Is_Approved = 1", "flt.Actual_Outcome IS NOT NULL"]
    if asset:
        where.append(f"da.Symbol = '{asset}'")
    if strategy:
        where.append(f"ds.Strategy_Key = '{strategy}'")

    query = sa.text(f"""
        SELECT
            {event_ts_expr} AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Key AS strategy,
            flt.Entry_Price AS entryPrice,
            flt.Close_Price AS exitPrice,
            flt.Stop_Loss AS stopLoss,
            flt.Take_Profit AS takeProfit,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') AS regime,
            flt.Confidence_Score AS confidence,
            flt.Signal_Value AS signalValue,
            flt.Actual_Outcome AS actual_outcome,
            flt.Close_Reason AS close_reason,
            flt.Close_Time AS close_time,
            flt.Trade_ID AS trade_id
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        LEFT JOIN Fact_Market_Regime_V2 fmr
            ON flt.Asset_ID = fmr.Asset_ID
            AND flt.Timestamp = fmr.Timestamp
            AND flt.Granularity = fmr.Granularity
        WHERE {' AND '.join(where)}
          AND {event_ts_expr} >= NOW() - INTERVAL '{days} days'
        ORDER BY {event_ts_expr} DESC
        LIMIT {limit}
    """)
    rows = execute_to_records(engine, query)
    trades = []
    for i, r in enumerate(rows):
        outcome = _map_outcome(r.get("actual_outcome"))
        entry = r.get("entryPrice", 0.0) or 0.0
        exit_price = r.get("exitPrice")
        ts_str = r.get("timestamp", "")
        ct_str = r.get("close_time")

        # Calculate approximate P&L in R units
        pnl = None
        if outcome == "win":
            pnl = 1.0
        elif outcome == "loss":
            pnl = -1.0

        hold_duration = None
        if ct_str and ts_str:
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                ct = datetime.strptime(ct_str, "%Y-%m-%dT%H:%M:%S")
                delta = ct - ts
                if delta.total_seconds() > 0:
                    hours = int(delta.total_seconds() // 3600)
                    minutes = int((delta.total_seconds() % 3600) // 60)
                    hold_duration = f"{hours}h {minutes}m"
            except Exception:
                pass

        trade: Dict[str, Any] = {
            "id": str(r.get("trade_id") or f"TRD-{int(datetime.now().timestamp() * 1000)}-{i}"),
            "timestamp": r["timestamp"],
            "asset": r["asset"],
            "strategy": r["strategy"],
            "entryPrice": entry,
            "exitPrice": exit_price,
            "stopLoss": r.get("stopLoss", 0.0) or 0.0,
            "takeProfit": r.get("takeProfit", 0.0) or 0.0,
            "regime": r.get("regime", "Trending_LowVol"),
            "confidence": round(r.get("confidence", 0.5) or 0.5, 3),
            "status": "closed",
            "signalValue": 1 if (r.get("signalValue") or 1) > 0 else -1,
            "reason": r.get("close_reason") or "Trade completed",
            "pnl": pnl,
            "slippage": None,
            "holdDuration": hold_duration,
            "outcome": outcome,
            "vetoReason": None,
        }
        trades.append(trade)
    return trades


def get_trade_statistics(
    engine: sa.engine.Engine,
    days: int = 30,
    asset: Optional[str] = None,
    strategy: Optional[str] = None,
) -> Dict[str, Any]:
    """Get aggregated trade statistics."""
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_col = 'Created_At' if 'Created_At' in flt_cols else 'Timestamp'

    where_clause = f"flt.{event_ts_col} >= NOW() - INTERVAL '{days} days'"
    if asset:
        where_clause += f" AND da.Symbol = '{asset}'"
    if strategy:
        where_clause += f" AND ds.Strategy_Key = '{strategy}'"

    query = sa.text(f"""
        SELECT
            COUNT(*) AS total_trades,
            SUM(CASE WHEN flt.Is_Approved = 1 THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN flt.Is_Approved = 0 THEN 1 ELSE 0 END) AS vetoed_count,
            SUM(CASE WHEN flt.Actual_Outcome = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN flt.Actual_Outcome = 0 THEN 1 ELSE 0 END) AS losses,
            AVG(flt.Confidence_Score) AS avg_confidence,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        WHERE {where_clause}
    """)
    rows = execute_to_records(engine, query)
    base = rows[0] if rows else {}

    total = base.get("total_trades", 0) or 0
    wins = base.get("wins", 0) or 0
    losses = base.get("losses", 0) or 0
    approved = base.get("approved_count", 0) or 0

    return {
        "totalTrades": int(total),
        "approvedCount": int(approved),
        "vetoedCount": int(base.get("vetoed_count", 0) or 0),
        "wins": int(wins),
        "losses": int(losses),
        "winRate": round(base.get("win_rate") or 0.0, 2),
        "avgConfidence": round(base.get("avg_confidence") or 0.0, 3),
        "netR": wins - losses,
    }


def get_asset_performance(
    engine: sa.engine.Engine,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """Get performance breakdown by asset."""
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_col = 'Created_At' if 'Created_At' in flt_cols else 'Timestamp'

    query = sa.text(f"""
        SELECT
            da.Symbol AS asset,
            COUNT(*) AS total_trades,
            SUM(CASE WHEN flt.Actual_Outcome = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN flt.Actual_Outcome = 0 THEN 1 ELSE 0 END) AS losses,
            SUM(
                CASE
                    WHEN flt.Actual_Outcome = 1 THEN 1.0
                    WHEN flt.Actual_Outcome = 0 THEN -1.0
                    ELSE 0.0
                END
            ) AS net_r,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        WHERE flt.Is_Approved = 1
          AND flt.Actual_Outcome IS NOT NULL
          AND flt.{event_ts_col} >= NOW() - INTERVAL '{days} days'
        GROUP BY da.Symbol
        ORDER BY net_r DESC
    """)
    return execute_to_records(engine, query)


def get_strategy_performance(
    engine: sa.engine.Engine,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """Get performance breakdown by strategy."""
    flt_cols = _fact_live_trades_columns(engine)
    event_ts_col = 'Created_At' if 'Created_At' in flt_cols else 'Timestamp'

    query = sa.text(f"""
        SELECT
            ds.Strategy_Key AS strategy,
            COUNT(*) AS total_trades,
            SUM(CASE WHEN flt.Actual_Outcome = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN flt.Actual_Outcome = 0 THEN 1 ELSE 0 END) AS losses,
            SUM(
                CASE
                    WHEN flt.Actual_Outcome = 1 THEN 1.0
                    WHEN flt.Actual_Outcome = 0 THEN -1.0
                    ELSE 0.0
                END
            ) AS net_r,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        WHERE flt.Is_Approved = 1
          AND flt.Actual_Outcome IS NOT NULL
          AND flt.{event_ts_col} >= NOW() - INTERVAL '{days} days'
        GROUP BY ds.Strategy_Key
        ORDER BY net_r DESC
    """)
    return execute_to_records(engine, query)
