"""Alert System routes — alert configuration and management endpoints."""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, Body
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import alerts_client
from layer5.services.data_contracts import (
    AlertConfig,
    AlertCreateRequest,
    AlertResponse,
    TriggeredAlert
)

router = APIRouter()


@router.get("/", response_model=List[AlertResponse])
def get_alerts(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[str] = Query(None, description="Filter by status (active, triggered, paused, expired)"),
    limit: int = Query(100, ge=1, le=500, description="Maximum alerts to return"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get alerts with optional filtering.
    
    Returns all alerts sorted by creation date (newest first).
    """
    alerts = alerts_client.get_alerts(conn.engine, symbol, status, limit)
    return [AlertResponse(**alert.model_dump()) for alert in alerts]


@router.post("/", response_model=AlertResponse)
def create_alert(
    alert_request: AlertCreateRequest,
    conn: sa.engine.Connection = Depends(get_db),
):
    """Create a new price or indicator alert.
    
    Example request:
    ```json
    {
        "name": "EURUSD Support Break",
        "type": "price",
        "symbol": "EUR_USD",
        "condition": "crosses_below",
        "value": 1.0850,
        "timeframe": "1h",
        "message": "Price broke below key support level"
    }
    ```
    """
    alert_config = AlertConfig(**alert_request.model_dump())
    created = alerts_client.create_alert(conn.engine, alert_config)
    return AlertResponse(**created.model_dump())


@router.put("/{alert_id}/status")
def update_alert_status(
    alert_id: str,
    status: str = Query(..., description="New status (active, paused, expired)"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Update alert status (pause, resume, expire)."""
    success = alerts_client.update_alert_status(conn.engine, alert_id, status)
    return {"success": success, "alert_id": alert_id, "status": status}


@router.delete("/{alert_id}")
def delete_alert(
    alert_id: str,
    conn: sa.engine.Connection = Depends(get_db),
):
    """Delete an alert permanently."""
    success = alerts_client.delete_alert(conn.engine, alert_id)
    return {"success": success, "alert_id": alert_id}


@router.get("/triggered", response_model=List[TriggeredAlert])
def get_triggered_alerts(
    since: Optional[datetime] = Query(None, description="Get alerts triggered since this time"),
    limit: int = Query(50, ge=1, le=200, description="Maximum alerts to return"),
    conn: sa.engine.Connection = Depends(get_db),
):
    """Get recently triggered alerts.
    
    Useful for notification systems and alert history.
    """
    alerts = alerts_client.get_triggered_alerts(conn.engine, since, limit)
    return [TriggeredAlert(**alert.model_dump()) for alert in alerts]


@router.post("/evaluate/{symbol}")
def evaluate_symbol_alerts(
    symbol: str,
    conn: sa.engine.Connection = Depends(get_db),
):
    """Manually trigger alert evaluation for a symbol.
    
    This endpoint checks all active alerts for the symbol against
    current market prices and returns any triggered alerts.
    """
    triggered = alerts_client.evaluate_alerts(conn.engine, symbol)
    return {
        "symbol": symbol,
        "evaluated_at": datetime.now().isoformat(),
        "triggered_count": len(triggered),
        "triggered_alerts": [TriggeredAlert(**alert.model_dump()) for alert in triggered]
    }


@router.get("/types", response_model=List[str])
def get_alert_types():
    """Get available alert types."""
    return ["price", "indicator", "pattern", "volume"]


@router.get("/conditions", response_model=List[str])
def get_alert_conditions():
    """Get available alert conditions."""
    return ["above", "below", "crosses_above", "crosses_below", "equals"]
