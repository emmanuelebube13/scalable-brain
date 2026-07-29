"""Model insights routes."""
from typing import List
from fastapi import APIRouter, Depends
import sqlalchemy as sa

from layer5.api.dependencies import get_db
from layer5.services import layer3_client
from layer5.services.data_contracts import (
    ModelMetadata,
    ModelPerformance,
    CalibrationPoint,
    FeatureImportance,
    DriftAlert,
)

router = APIRouter()


@router.get("/metadata", response_model=ModelMetadata)
def get_metadata(conn: sa.engine.Connection = Depends(get_db)):
    return ModelMetadata(**layer3_client.get_model_metadata(conn.engine))


@router.get("/performance", response_model=List[ModelPerformance])
def get_performance(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer3_client.get_model_performance(conn.engine)
    return [ModelPerformance(**r) for r in rows]


@router.get("/calibration", response_model=List[CalibrationPoint])
def get_calibration(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer3_client.get_calibration_data(conn.engine)
    return [CalibrationPoint(**r) for r in rows]


@router.get("/features", response_model=List[FeatureImportance])
def get_features():
    rows = layer3_client.get_feature_importance()
    return [FeatureImportance(**r) for r in rows]


@router.get("/drift", response_model=List[DriftAlert])
def get_drift(conn: sa.engine.Connection = Depends(get_db)):
    rows = layer3_client.get_drift_alerts(conn.engine)
    return [DriftAlert(**r) for r in rows]
