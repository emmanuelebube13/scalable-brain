"""Risk dashboard routes."""
from typing import List
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer4_client
from layer5.services.data_contracts import RiskMetrics, LimitStatus

router = APIRouter()


@router.get("/", response_model=RiskMetrics)
def get_risk(conn: sa.engine.Connection = Depends(get_db)):
    return RiskMetrics(**layer4_client.get_risk_metrics(conn.engine))


@router.get("/limits", response_model=List[LimitStatus])
def get_limits(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer4_client.get_risk_limits(conn.engine)
    return [LimitStatus(**r) for r in rows]
