#!/usr/bin/env python3
"""Convenience entrypoint to start the Layer 5 FastAPI backend."""

import sys
from pathlib import Path

# Add src/ to Python path so we can import sibling layer modules
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn
from layer5.api.config import LAYER5_API_HOST, LAYER5_API_PORT

if __name__ == "__main__":
    print(f"Starting Layer 5 Telemetry API on http://{LAYER5_API_HOST}:{LAYER5_API_PORT}")
    uvicorn.run(
        "layer5.api.main:app",
        host=LAYER5_API_HOST,
        port=LAYER5_API_PORT,
        reload=True,
        reload_dirs=[str(Path(__file__).resolve().parent / "api")],
    )
