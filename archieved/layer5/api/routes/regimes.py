"""Regime analysis routes."""
from typing import List
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer1_client
from layer5.services.data_contracts import RegimeData, RegimePerformance

router = APIRouter()


@router.get("/current", response_model=List[RegimeData])
def get_current_regimes(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer1_client.get_current_regimes(conn.engine)
    return [RegimeData(**r) for r in rows]


@router.get("/performance", response_model=List[RegimePerformance])
def get_regime_performance(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer1_client.get_regime_performance(conn.engine)
    return [RegimePerformance(**r) for r in rows]
