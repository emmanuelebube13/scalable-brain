# Layer 5: Execution & Telemetry Dashboard

**Date:** April 3, 2026  
**Scope:** Institutional-grade React dashboard + FastAPI backend for visualizing Layers 0-4 outputs.  
**System Context:** Consumes data from the shared `ForexBrainDB` without recomputing upstream logic.

---

## Architecture

```
src/layer5/
├── api/               # FastAPI service layer
│   ├── main.py        # App factory, CORS, router wiring
│   ├── config.py      # Env-driven configuration
│   ├── dependencies.py# DB connection injection
│   └── routes/        # 7 view routers (kpi, trades, risk, regimes, model, strategies, assets)
├── services/          # Loose-coupling business logic
│   ├── data_contracts.py   # Pydantic models mirroring React types
│   ├── db_client.py        # Shared SQLAlchemy engine
│   ├── layer1_client.py    # Regime data (Fact_Market_Regime_V2)
│   ├── layer2_client.py    # Signal data (Fact_Signals)
│   ├── layer3_client.py    # ML metadata (models dir + DB)
│   ├── layer4_client.py    # Execution/risk data (Fact_Live_Trades)
│   └── query_builder.py    # Reusable SQL fragments
├── frontend/          # React + Vite + Tailwind dashboard
│   └── src/
│       └── services/
│           ├── api.ts      # Axios/fetch wrapper calling backend
│           └── mockData.ts # Fallback / offline mock generators
├── legacy/            # Prior Dash prototypes (app3.py, app4.py)
├── app.py             # Legacy Dash app (backward compat)
└── run.py             # `python src/layer5/run.py` startup script
```

---

## Loose-Coupling Rules

1. The React frontend talks **only** to the FastAPI backend via `/api/v1/*`.
2. Backend routes delegate **all** DB access to `services/*_client.py`.
3. **No hardcoded SQL** in React components or route handlers.
4. Each `layerN_client.py` reads the fact/dimension tables produced by that layer.
5. **Granularity keys** (`H1`, `H4`, `D1`) are preserved end-to-end.

---

## API Endpoints

| View | Endpoint | Description |
|------|----------|-------------|
| Overview | `GET /api/v1/kpi/` | High-level KPIs |
| Overview | `GET /api/v1/kpi/trend` | 7-day approval trend |
| Overview | `GET /api/v1/kpi/attribution` | Layer contribution breakdown |
| Trades | `GET /api/v1/trades/?limit=&status=&asset=&strategy=` | Live trade blotter |
| Trades | `GET /api/v1/trades/blocked?limit=` | Blocked/vetoed trades |
| Trades | `GET /api/v1/trades/signals/pending?limit=` | Pending signals |
| Risk | `GET /api/v1/risk/` | Risk metrics + underwater |
| Risk | `GET /api/v1/risk/limits` | Risk limit tracker |
| Regimes | `GET /api/v1/regimes/current` | Current regime by asset |
| Regimes | `GET /api/v1/regimes/performance` | Regime-stratified performance |
| Model | `GET /api/v1/model/metadata` | Champion model metadata |
| Model | `GET /api/v1/model/performance` | Training vs live metrics |
| Model | `GET /api/v1/model/calibration` | Calibration curve points |
| Model | `GET /api/v1/model/features` | Feature importance |
| Model | `GET /api/v1/model/drift` | Drift alerts |
| Strategies | `GET /api/v1/strategies/` | Strategy cards |
| Assets | `GET /api/v1/assets/` | Asset performance cards |
| Health | `GET /health` | Liveness probe |

---

## Running Locally

### 1. Start the API backend

```bash
cd scalable-brain
python src/layer5/run.py
```

The API will be available at `http://localhost:8000`.

### 2. Start the React frontend (in a second terminal)

```bash
cd scalable-brain/src/layer5/frontend
npm install   # only first time
npm run dev
```

The dashboard will be available at `http://localhost:5173` and will proxy API calls to `:8000` automatically via `vite.config.ts`.

### 3. Forced mock mode (no backend)

If you want to run the frontend without the Python backend:

```bash
VITE_USE_MOCK=1 npm run dev
```

---

## Known Limitations

- `Strategies` and `Assets` routes currently return synthetic data for UI completeness; they will be backed by `Dim_Strategy` and `Fact_Market_Prices` queries in a future iteration.
- Some forensics fields (slippage, hold duration, exit details) are augmented with sensible defaults when the database does not yet contain rich execution logs.
- Real-time WebSocket streaming is planned but not yet implemented; the UI refreshes on view switch or page reload.

---

## Verification Checklist

- [ ] `python src/layer5/run.py` starts without import errors.
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok","layer":5}`.
- [ ] `curl http://localhost:8000/api/v1/kpi/` returns KPI JSON.
- [ ] Frontend loads at `:5173` and all 7 tabs render without console errors.
- [ ] Switching tabs triggers API calls (visible in browser Network tab) and falls back to mock data if the backend is down.
