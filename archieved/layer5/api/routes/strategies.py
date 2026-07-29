"""Strategy breakdown routes."""
from typing import List
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import reference_data_client
from layer5.services.data_contracts import Strategy

router = APIRouter()


@router.get("/", response_model=List[Strategy])
def get_strategies(conn: sa.engine.Connection = Depends(get_db)):
    rows = reference_data_client.get_strategies(conn.engine)
    return [Strategy(**r) for r in rows]
