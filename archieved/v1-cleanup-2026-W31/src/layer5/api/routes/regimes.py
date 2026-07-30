"""Regime analysis routes."""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer1_client
from layer5.services.data_contracts import RegimeData, RegimePerformance

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
def get_regimes_summary(conn: sa.engine.Connection = Depends(get_db)):
    """Get both current regimes and performance summary."""
    current = layer1_client.get_current_regimes(conn.engine)
    performance = layer1_client.get_regime_performance(conn.engine)
    return {
        "current": current,
        "performance": performance,
        "count": len(current)
    }


@router.get("/current", response_model=List[RegimeData])
def get_current_regimes(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer1_client.get_current_regimes(conn.engine)
    return [RegimeData(**r) for r in rows]


@router.get("/performance", response_model=List[RegimePerformance])
def get_regime_performance(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer1_client.get_regime_performance(conn.engine)
    return [RegimePerformance(**r) for r in rows]
