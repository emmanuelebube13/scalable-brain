"""KPI / Overview routes."""
from typing import List
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer4_client
from layer5.services.data_contracts import KPIData, ApprovalTrendPoint, PerformanceAttribution

router = APIRouter()


@router.get("/", response_model=KPIData)
def get_kpi(conn: sa.engine.Connection = Depends(get_db)):
    return KPIData(**layer4_client.get_kpi_data(conn.engine))


@router.get("/trend", response_model=List[ApprovalTrendPoint])
def get_trend(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer4_client.get_approval_trend(conn.engine)
    return [ApprovalTrendPoint(**r) for r in rows]


@router.get("/attribution", response_model=List[PerformanceAttribution])
def get_attribution():
    # Placeholder: layer attribution requires dedicated P&L decomposition.
    return []
