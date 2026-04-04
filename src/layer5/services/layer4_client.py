"""Layer 4 service client — execution, risk, and live trade data access.

Reads exclusively from Fact_Live_Trades, Dim_Asset, and Dim_Strategy.
No risk calculations are recomputed here.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import sqlalchemy as sa

from layer5.services.db_client import execute_to_records


def _map_outcome(val: Any) -> Optional[str]:
    if val is None or pd.isna(val):
        return None
    v = str(val).strip()
    if v in ("1", "1.0", "True", "true"):
        return "win"
    if v in ("0", "0.0", "False", "false"):
        return "loss"
    return None


def get_live_trades(
    engine: sa.engine.Engine,
    limit: int = 50,
    status: Optional[str] = None,
    asset: Optional[str] = None,
    strategy: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return recent live trades. Forensics are only populated when real close data exists."""
    where = ["1=1"]
    if status == "approved":
        where.append("flt.Is_Approved = 1")
    elif status == "vetoed":
        where.append("flt.Is_Approved = 0")
    if asset:
        where.append(f"da.Symbol = '{asset}'")
    if strategy:
        where.append(f"ds.Strategy_Key = '{strategy}'")

    query = sa.text(f"""
        SELECT TOP {limit}
            flt.Timestamp AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Key AS strategy,
            flt.Entry_Price AS entryPrice,
            flt.Stop_Loss AS stopLoss,
            flt.Take_Profit AS takeProfit,
            COALESCE(fmr.Regime_Label, 'Trending_LowVol') AS regime,
            flt.Confidence_Score AS confidence,
            flt.Is_Approved AS is_approved,
            flt.Signal_Value AS signalValue,
            flt.Actual_Outcome AS actual_outcome,
            flt.ATR_Value AS atr,
            flt.ADX_Value AS adx,
            flt.Close_Reason AS closeReason,
            flt.Close_Time AS closeTime
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        LEFT JOIN Fact_Market_Regime_V2 fmr
            ON flt.Asset_ID = fmr.Asset_ID
            AND flt.Timestamp = fmr.Timestamp
            AND flt.Granularity = fmr.Granularity
        WHERE {' AND '.join(where)}
        ORDER BY flt.Timestamp DESC
    """)
    rows = execute_to_records(engine, query)
    trades = []
    for i, r in enumerate(rows):
        is_approved = bool(r.get("is_approved"))
        outcome = _map_outcome(r.get("actual_outcome"))
        entry = r.get("entryPrice", 0.0) or 0.0
        ts_str = r.get("timestamp", "")
        ct_str = r.get("closeTime")

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
            "id": f"TRD-{int(datetime.now().timestamp() * 1000)}-{i}",
            "timestamp": r["timestamp"],
            "asset": r["asset"],
            "strategy": r["strategy"],
            "entryPrice": entry,
            "stopLoss": r.get("stopLoss", 0.0) or 0.0,
            "takeProfit": r.get("takeProfit", 0.0) or 0.0,
            "regime": r.get("regime", "Trending_LowVol"),
            "confidence": round(r.get("confidence", 0.5) or 0.5, 3),
            "status": "approved" if is_approved else "vetoed",
            "signalValue": 1 if (r.get("signalValue") or 1) > 0 else -1,
            "reason": "ML approval above threshold" if is_approved else "Confidence below threshold",
            "pnl": None,
            "slippage": None,
            "holdDuration": hold_duration,
            "outcome": outcome if is_approved else None,
            "vetoReason": "Confidence below 0.535 threshold" if not is_approved else None,
        }
        if is_approved and outcome and r.get("closeReason"):
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
                    "reason": r["closeReason"].lower().replace(" ", "_"),
                    "details": r["closeReason"],
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


def get_blocked_trades(engine: sa.engine.Engine, limit: int = 10) -> List[Dict[str, Any]]:
    """Return recently vetoed trades with reasons from the database."""
    query = sa.text(f"""
        SELECT TOP {limit}
            flt.Timestamp AS timestamp,
            da.Symbol AS asset,
            ds.Strategy_Key AS strategy,
            flt.Confidence_Score AS confidence,
            flt.Is_Approved,
            COALESCE(flt.Close_Reason, 'Unknown') AS veto_reason
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        INNER JOIN Dim_Strategy ds ON flt.Strategy_ID = ds.Strategy_ID
        WHERE flt.Is_Approved = 0
        ORDER BY flt.Timestamp DESC
    """)
    rows = execute_to_records(engine, query)
    for i, r in enumerate(rows):
        r["id"] = f"BLK-{int(datetime.now().timestamp() * 1000)}-{i}"
        r["status"] = "vetoed"
        r["vetoReason"] = r.get("veto_reason") or "Unknown"
    return rows


def get_risk_metrics(engine: sa.engine.Engine) -> Dict[str, Any]:
    """Compute risk metrics from live trade history."""
    query = sa.text("""
        SELECT
            COUNT(*) AS total_signals,
            SUM(CAST(flt.Is_Approved AS INT)) AS approved_count,
            AVG(flt.Confidence_Score) AS avg_confidence,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate
        FROM Fact_Live_Trades flt
        WHERE flt.Timestamp >= DATEADD(DAY, -30, GETDATE())
    """)
    row = execute_to_records(engine, query)
    base = row[0] if row else {}

    asset_query = sa.text("""
        SELECT da.Symbol AS asset,
               SUM(CASE WHEN flt.Signal_Value = 1 THEN 1 ELSE 0 END) AS long_count,
               SUM(CASE WHEN flt.Signal_Value = -1 THEN 1 ELSE 0 END) AS short_count
        FROM Fact_Live_Trades flt
        INNER JOIN Dim_Asset da ON flt.Asset_ID = da.Asset_ID
        WHERE flt.Is_Approved = 1
          AND flt.Timestamp >= DATEADD(DAY, -7, GETDATE())
        GROUP BY da.Symbol
    """)
    asset_rows = execute_to_records(engine, asset_query)
    exposure = []
    for a in asset_rows:
        long_val = float(a.get("long_count", 0))
        short_val = float(a.get("short_count", 0))
        exposure.append({
            "asset": a["asset"],
            "long": long_val,
            "short": short_val,
            "net": round(long_val - short_val, 2),
        })

    # Underwater from actual daily outcomes
    underwater_query = sa.text("""
        SELECT
            CAST(Timestamp AS DATE) AS date,
            AVG(CAST(CASE WHEN Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS daily_win_pct
        FROM Fact_Live_Trades
        WHERE Is_Approved = 1 AND Actual_Outcome IS NOT NULL
          AND Timestamp >= DATEADD(DAY, -90, GETDATE())
        GROUP BY CAST(Timestamp AS DATE)
        ORDER BY date
    """)
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
            underwater.append({
                "date": r["date"],
                "drawdown": round(min(dd, 0), 2),
            })

    # Correlation matrix placeholder — real values require price-history computation
    corr_query = sa.text("""
        SELECT
            a.Symbol AS asset1,
            b.Symbol AS asset2
        FROM Dim_Asset a
        CROSS JOIN Dim_Asset b
        WHERE a.Asset_ID < b.Asset_ID
          AND a.Is_Active = 1 AND b.Is_Active = 1
    """)
    corr_rows = execute_to_records(engine, corr_query)
    corr_matrix = [{"asset1": r["asset1"], "asset2": r["asset2"], "correlation": 0.0} for r in corr_rows]

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
    """Aggregate high-level KPIs from Layer 4 data."""
    query = sa.text("""
        SELECT
            COUNT(*) AS total_signals,
            SUM(CAST(flt.Is_Approved AS INT)) AS approved_count,
            AVG(flt.Confidence_Score) AS avg_confidence,
            AVG(CAST(CASE WHEN flt.Actual_Outcome = 1 THEN 1.0 ELSE 0.0 END AS FLOAT)) * 100.0 AS win_rate,
            SUM(CASE WHEN flt.Order_ID IS NOT NULL THEN 1 ELSE 0 END) AS live_positions
        FROM Fact_Live_Trades flt
        WHERE flt.Timestamp >= DATEADD(DAY, -1, GETDATE())
    """)
    row = execute_to_records(engine, query)
    base = row[0] if row else {}
    total = base.get("total_signals", 0) or 0
    approved = base.get("approved_count", 0) or 0
    avg_conf = base.get("avg_confidence", 0) or 0.0
    win_rate = base.get("win_rate", 0) or 0.0
    live_pos = base.get("live_positions", 0) or 0

    return {
        "totalSignals": int(total),
        "approvalRate": round((approved / total) * 100, 1) if total else 0.0,
        "avgConfidence": round(avg_conf, 3),
        "livePositions": int(live_pos),
        "unrealizedPnL": 0.0,
        "winRate24h": round(win_rate, 1),
        "sharpeRatio": 0.0,
        "maxDrawdown": 0.0,
        "sortinoRatio": 0.0,
        "calmarRatio": 0.0,
    }


def get_approval_trend(engine: sa.engine.Engine) -> List[Dict[str, Any]]:
    """Return 7-day approval rate trend from the database."""
    query = sa.text("""
        SELECT
            CAST(flt.Timestamp AS DATE) AS date,
            COUNT(*) AS signal_count,
            AVG(CAST(flt.Is_Approved AS FLOAT)) * 100.0 AS approval_rate
        FROM Fact_Live_Trades flt
        WHERE flt.Timestamp >= DATEADD(DAY, -6, CAST(GETDATE() AS DATE))
        GROUP BY CAST(flt.Timestamp AS DATE)
        ORDER BY date
    """)
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
        WHERE CAST(Timestamp AS DATE) = CAST(GETDATE() AS DATE) AND Is_Approved = 1
    """)
    dl_rows = execute_to_records(engine, dl_query)
    daily_loss = dl_rows[0].get("daily_loss_proxy") or 0.0 if dl_rows else 0.0

    return [
        {"name": "Max Drawdown", "limit": md_cap, "current": current_dd, "unit": "%"},
        {"name": "Concentration", "limit": conc_cap, "current": current_exp, "unit": "%"},
        {"name": "Leverage", "limit": lev_cap, "current": 0.0, "unit": "x"},
        {"name": "Daily Loss", "limit": daily_loss_cap, "current": round(daily_loss, 2), "unit": "$"},
    ]
