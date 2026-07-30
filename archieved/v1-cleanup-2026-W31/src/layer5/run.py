#!/usr/bin/env python3
"""
Layer 5 Telemetry API - Swing Trading Dashboard Backend.

🚀 SWING TRADING SYSTEM | Real-time observability for swing trade execution

Convenience entrypoint to start the Layer 5 FastAPI backend for swing trading
telemetry, KPI dashboards, and trade monitoring.

import os
import sys
from pathlib import Path

# Add src/ to Python path so we can import sibling layer modules
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn
from layer5.api.config import LAYER5_API_HOST, LAYER5_API_PORT

if __name__ == "__main__":
    reload_enabled = os.getenv("LAYER5_API_RELOAD", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    print(f"Starting Layer 5 Telemetry API on http://{LAYER5_API_HOST}:{LAYER5_API_PORT}")
    print(f"Reload mode: {'enabled' if reload_enabled else 'disabled'}")

    uvicorn_kwargs = {
        "host": LAYER5_API_HOST,
        "port": LAYER5_API_PORT,
        "reload": reload_enabled,
    }
    if reload_enabled:
        uvicorn_kwargs["reload_dirs"] = [str(Path(__file__).resolve().parent)]

    uvicorn.run(
        "layer5.api.main:app",
        **uvicorn_kwargs,
    )
