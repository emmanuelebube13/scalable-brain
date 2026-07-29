"""Layer 5 API configuration — env-driven, no hardcoded secrets."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up from src/layer5/api)
ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")

DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "ForexBrainDB")
DB_PORT = int(os.getenv("DB_PORT", "1433"))

LAYER5_API_PORT = int(os.getenv("LAYER5_API_PORT", "8001"))
LAYER5_API_HOST = os.getenv("LAYER5_API_HOST", "0.0.0.0")

# CORS origins for the Vite dev server and any production frontends
CORS_ORIGINS = os.getenv(
    "LAYER5_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
).split(",")

# Layer 3 model artifacts path
# The workspace may have models/ at the git root (one level above scalable-brain)
# or inside the project root. Pick whichever exists.
_default_models = ROOT_DIR / "models"
if not _default_models.exists() and (ROOT_DIR.parent / "models").exists():
    _default_models = ROOT_DIR.parent / "models"

MODELS_DIR = Path(os.getenv("LAYER3_MODELS_DIR", str(_default_models)))
LAYER3_MANIFEST_PATH = MODELS_DIR / "champion_manifest.json"
LAYER3_STABLE_ALIAS = MODELS_DIR / "champion_model.pkl"
LAYER3_PREPROCESSOR_ALIAS = MODELS_DIR / "champion_preprocessor.pkl"
