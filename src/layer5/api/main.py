"""Layer 5 FastAPI backend — loosely coupled telemetry API for the React dashboard."""

import sys
from pathlib import Path

# Ensure src/ is on the path so we can import sibling layers
LAYER5_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = LAYER5_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from layer5.api.config import CORS_ORIGINS
from layer5.api.routes import kpi, trades, risk, regimes, model, strategies, assets

app = FastAPI(
    title="Scalable Brain | Layer 5 Telemetry API",
    version="1.0.0",
    description="Loosely-coupled API serving Layers 0-4 data to the institutional dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kpi.router, prefix="/api/v1/kpi", tags=["KPI"])
app.include_router(trades.router, prefix="/api/v1/trades", tags=["Trades"])
app.include_router(risk.router, prefix="/api/v1/risk", tags=["Risk"])
app.include_router(regimes.router, prefix="/api/v1/regimes", tags=["Regimes"])
app.include_router(model.router, prefix="/api/v1/model", tags=["Model"])
app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["Strategies"])
app.include_router(assets.router, prefix="/api/v1/assets", tags=["Assets"])


@app.get("/health")
def health_check():
    return {"status": "ok", "layer": 5}
