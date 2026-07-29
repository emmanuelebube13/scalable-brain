"""Trade blotter & forensics routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer4_client, layer2_client
from layer5.services.data_contracts import Trade, Signal

router = APIRouter()


@router.get("/", response_model=List[Trade])
def get_trades(
    limit: int = 50,
    status: Optional[str] = None,
    asset: Optional[str] = None,
    strategy: Optional[str] = None,
    conn: sa.engine.Connection = Depends(get_db),
):
    rows = layer4_client.get_live_trades(conn.engine, limit=limit, status=status, asset=asset, strategy=strategy)
    return [Trade(**r) for r in rows]


@router.get("/blocked", response_model=List[Trade])
def get_blocked(
    limit: int = 10,
    conn: sa.engine.Connection = Depends(get_db),
):
    rows = layer4_client.get_blocked_trades(conn.engine, limit=limit)
    return [Trade(**r) for r in rows]


@router.get("/signals/pending", response_model=List[Signal])
def get_pending(
    limit: int = 5,
    conn: sa.engine.Connection = Depends(get_db),
):
    rows = layer2_client.get_pending_signals(conn.engine, limit=limit)
    return [Signal(**r) for r in rows]
