"""Asset performance routes."""
from typing import List
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import reference_data_client
from layer5.services.data_contracts import Asset

router = APIRouter()


@router.get("/", response_model=List[Asset])
def get_assets(conn: sa.engine.Connection = Depends(get_db)):
    rows = reference_data_client.get_assets(conn.engine)
    return [Asset(**r) for r in rows]
