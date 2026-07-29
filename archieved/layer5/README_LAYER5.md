# Layer 5 Telemetry Surface

Last updated: 2026-04-06

Layer 5 is the observability/read layer for the trading stack. It does not generate signals or execute trades.

## Scope

1. FastAPI backend exposing `/api/v1/*` endpoints.
2. React/Vite frontend dashboard consuming those endpoints.
3. Service clients that read Layer 1/2/3/4 artifacts and tables.

## Folder Layout

```
src/layer5/
	api/
		main.py
		config.py
		dependencies.py
		routes/
			assets.py
			kpi.py
			model.py
			regimes.py
			risk.py
			strategies.py
			trades.py
	services/
		db_client.py
		layer1_client.py
		layer2_client.py
		layer3_client.py
		layer4_client.py
		data_contracts.py
	frontend/
		src/
			services/api.ts
			components/
			views/
	run.py
```

## Runtime Contracts

Layer 5 service clients read from:

- Layer 1: regime context (`Fact_Market_Regime_V2`)
- Layer 2: signal stream (`Fact_Signals`)
- Layer 3: champion manifest and model metadata from `models/`
- Layer 4: live decisions and trade outcomes (`Fact_Live_Trades`, execution logs)
- Auxiliary NLP (upcoming telemetry integration): `Fact_Macro_Events`

Layer 5 must remain read-oriented and should not duplicate Layer 2/3/4 decision logic.

## Current State Snapshot (Apr 6, 2026)

1. Layer 4 schema-write alignment fixes are applied, so trade read models should be validated against current active `Fact_Live_Trades` columns.
2. Layer 4 logs now rotate; operational dashboards should assume active log file rollover.
3. NLP macro ingestion exists as an auxiliary data source and is planned for Layer 5 macro insight cards/endpoints.

## API Surface

- `GET /health`
- `GET /api/v1/kpi/`
- `GET /api/v1/kpi/trend`
- `GET /api/v1/kpi/attribution`
- `GET /api/v1/trades/`
- `GET /api/v1/trades/blocked`
- `GET /api/v1/trades/signals/pending`
- `GET /api/v1/risk/`
- `GET /api/v1/risk/limits`
- `GET /api/v1/regimes/current`
- `GET /api/v1/regimes/performance`
- `GET /api/v1/model/metadata`
- `GET /api/v1/model/performance`
- `GET /api/v1/model/calibration`
- `GET /api/v1/model/features`
- `GET /api/v1/model/drift`
- `GET /api/v1/strategies/`
- `GET /api/v1/assets/`

## Local Run

From repository root:

```bash
python src/layer5/run.py
```

Then start frontend in a second terminal:

```bash
cd src/layer5/frontend
npm install
npm run dev
```

## Current Notes

1. Some route outputs include fallback/default shaping when source data is sparse.
2. Frontend must treat all API fields as potentially partial and render defensively.
3. Bundle size warnings in frontend build are non-blocking and performance-related.
