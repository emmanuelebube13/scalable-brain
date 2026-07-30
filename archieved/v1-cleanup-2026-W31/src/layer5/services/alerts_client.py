"""Alert System service — price and indicator-based alerts.

Manages alert configuration, evaluation, and notification triggers.
Alerts are stored in the database for persistence.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Literal
import sqlalchemy as sa
from pydantic import BaseModel

from layer5.services.db_client import execute_to_records, get_engine
from layer5.services.chart_data_client import get_price_history

AlertType = Literal["price", "indicator", "pattern", "volume"]
AlertCondition = Literal["above", "below", "crosses_above", "crosses_below", "equals"]
AlertStatus = Literal["active", "triggered", "paused", "expired"]


class AlertConfig(BaseModel):
    """Alert configuration model."""
    id: Optional[str] = None
    name: str
    type: AlertType
    symbol: str
    condition: AlertCondition
    value: float
    timeframe: Optional[str] = "1h"
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    status: AlertStatus = "active"
    triggered_at: Optional[datetime] = None
    triggered_price: Optional[float] = None


def _ensure_alerts_table(engine: sa.engine.Engine) -> None:
    """Ensure the alerts table exists."""
    query = sa.text("""
        CREATE TABLE IF NOT EXISTS Layer5_Alerts (
            Alert_ID SERIAL PRIMARY KEY,
            Alert_Name VARCHAR(255) NOT NULL,
            Alert_Type VARCHAR(50) NOT NULL,
            Symbol VARCHAR(50) NOT NULL,
            Condition_Type VARCHAR(50) NOT NULL,
            Target_Value DOUBLE PRECISION NOT NULL,
            Timeframe VARCHAR(10) DEFAULT '1h',
            Message VARCHAR(500),
            Created_At TIMESTAMP DEFAULT NOW(),
            Expires_At TIMESTAMP,
            Status VARCHAR(20) DEFAULT 'active',
            Triggered_At TIMESTAMP,
            Triggered_Price DOUBLE PRECISION
        )
    """)
    try:
        with engine.connect() as conn:
            conn.execute(query)
            conn.commit()
    except Exception:
        pass  # Table may already exist


def create_alert(
    engine: sa.engine.Engine,
    alert: AlertConfig
) -> AlertConfig:
    """Create a new alert."""
    _ensure_alerts_table(engine)
    
    query = sa.text("""
        INSERT INTO Layer5_Alerts 
        (Alert_Name, Alert_Type, Symbol, Condition_Type, Target_Value, Timeframe, Message, Expires_At, Status)
        VALUES 
        (:name, :type, :symbol, :condition, :value, :timeframe, :message, :expires_at, 'active')
        RETURNING Alert_ID, Created_At
    """)
    
    params = {
        "name": alert.name,
        "type": alert.type,
        "symbol": alert.symbol,
        "condition": alert.condition,
        "value": alert.value,
        "timeframe": alert.timeframe or "1h",
        "message": alert.message,
        "expires_at": alert.expires_at or datetime.now() + timedelta(days=30),
    }
    
    rows = execute_to_records(engine, query, params)
    if rows:
        alert.id = str(rows[0]["Alert_ID"])
        alert.created_at = rows[0]["Created_At"]
        alert.status = "active"
    
    return alert


def get_alerts(
    engine: sa.engine.Engine,
    symbol: Optional[str] = None,
    status: Optional[AlertStatus] = None,
    limit: int = 100
) -> List[AlertConfig]:
    """Get alerts with optional filtering."""
    _ensure_alerts_table(engine)
    
    where_clauses = ["1=1"]
    params = {}
    
    if symbol:
        where_clauses.append("Symbol = :symbol")
        params["symbol"] = symbol
    if status:
        where_clauses.append("Status = :status")
        params["status"] = status
    
    query = sa.text(f"""
        SELECT
            Alert_ID as id,
            Alert_Name as name,
            Alert_Type as type,
            Symbol as symbol,
            Condition_Type as condition,
            Target_Value as value,
            Timeframe as timeframe,
            Message as message,
            Created_At as created_at,
            Expires_At as expires_at,
            Status as status,
            Triggered_At as triggered_at,
            Triggered_Price as triggered_price
        FROM Layer5_Alerts
        WHERE {' AND '.join(where_clauses)}
        ORDER BY Created_At DESC
        LIMIT {limit}
    """)
    
    rows = execute_to_records(engine, query, params)
    
    alerts = []
    for r in rows:
        alerts.append(AlertConfig(
            id=str(r.get("id", "")),
            name=r.get("name", ""),
            type=r.get("type", "price"),
            symbol=r.get("symbol", ""),
            condition=r.get("condition", "above"),
            value=float(r.get("value") or 0),
            timeframe=r.get("timeframe", "1h"),
            message=r.get("message"),
            created_at=r.get("created_at"),
            expires_at=r.get("expires_at"),
            status=r.get("status", "active"),
            triggered_at=r.get("triggered_at"),
            triggered_price=float(r.get("triggered_price")) if r.get("triggered_price") else None,
        ))
    
    return alerts


def update_alert_status(
    engine: sa.engine.Engine,
    alert_id: str,
    status: AlertStatus
) -> bool:
    """Update alert status."""
    query = sa.text("""
        UPDATE Layer5_Alerts
        SET Status = :status
        WHERE Alert_ID = :alert_id
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {"alert_id": alert_id, "status": status})
            conn.commit()
            return result.rowcount > 0
    except Exception:
        return False


def delete_alert(engine: sa.engine.Engine, alert_id: str) -> bool:
    """Delete an alert."""
    query = sa.text("""
        DELETE FROM Layer5_Alerts
        WHERE Alert_ID = :alert_id
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {"alert_id": alert_id})
            conn.commit()
            return result.rowcount > 0
    except Exception:
        return False


def evaluate_alerts(engine: sa.engine.Engine, symbol: str) -> List[AlertConfig]:
    """Evaluate active alerts for a symbol and return triggered alerts."""
    active_alerts = get_alerts(engine, symbol=symbol, status="active")
    triggered = []
    
    # Get current price
    price_history = get_price_history(engine, symbol, lookback_days=1)
    if not price_history:
        return triggered
    
    current_price = price_history[-1]["price"]
    previous_price = price_history[-2]["price"] if len(price_history) > 1 else current_price
    
    for alert in active_alerts:
        # Check expiration
        if alert.expires_at and alert.expires_at < datetime.now():
            update_alert_status(engine, alert.id, "expired")
            continue
        
        is_triggered = False
        
        if alert.condition == "above":
            is_triggered = current_price > alert.value
        elif alert.condition == "below":
            is_triggered = current_price < alert.value
        elif alert.condition == "crosses_above":
            is_triggered = previous_price <= alert.value and current_price > alert.value
        elif alert.condition == "crosses_below":
            is_triggered = previous_price >= alert.value and current_price < alert.value
        elif alert.condition == "equals":
            is_triggered = abs(current_price - alert.value) < 0.0001
        
        if is_triggered:
            # Mark as triggered
            query = sa.text("""
                UPDATE Layer5_Alerts
                SET Status = 'triggered',
                    Triggered_At = NOW(),
                    Triggered_Price = :price
                WHERE Alert_ID = :alert_id
            """)
            try:
                with engine.connect() as conn:
                    conn.execute(query, {"alert_id": alert.id, "price": current_price})
                    conn.commit()
            except Exception:
                pass
            
            alert.status = "triggered"
            alert.triggered_at = datetime.now()
            alert.triggered_price = current_price
            triggered.append(alert)
    
    return triggered


def get_triggered_alerts(
    engine: sa.engine.Engine,
    since: Optional[datetime] = None,
    limit: int = 50
) -> List[AlertConfig]:
    """Get recently triggered alerts."""
    _ensure_alerts_table(engine)
    
    since = since or datetime.now() - timedelta(days=1)
    
    query = sa.text(f"""
        SELECT
            Alert_ID as id,
            Alert_Name as name,
            Alert_Type as type,
            Symbol as symbol,
            Condition_Type as condition,
            Target_Value as value,
            Timeframe as timeframe,
            Message as message,
            Created_At as created_at,
            Expires_At as expires_at,
            Status as status,
            Triggered_At as triggered_at,
            Triggered_Price as triggered_price
        FROM Layer5_Alerts
        WHERE Status = 'triggered'
          AND Triggered_At >= :since
        ORDER BY Triggered_At DESC
        LIMIT {limit}
    """)
    
    rows = execute_to_records(engine, query, {"since": since})
    
    alerts = []
    for r in rows:
        alerts.append(AlertConfig(
            id=str(r.get("id", "")),
            name=r.get("name", ""),
            type=r.get("type", "price"),
            symbol=r.get("symbol", ""),
            condition=r.get("condition", "above"),
            value=float(r.get("value") or 0),
            timeframe=r.get("timeframe", "1h"),
            message=r.get("message"),
            created_at=r.get("created_at"),
            expires_at=r.get("expires_at"),
            status=r.get("status", "triggered"),
            triggered_at=r.get("triggered_at"),
            triggered_price=float(r.get("triggered_price")) if r.get("triggered_price") else None,
        ))
    
    return alerts
