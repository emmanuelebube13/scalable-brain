# Layer 5 Frontend Dashboard

Last updated: 2026-04-06

React + TypeScript + Vite dashboard for visualizing Layers 1 through 4 outputs via Layer 5 API.

## Purpose

This frontend is a read-only operational console. It should:

1. Render API data defensively (null-safe, fallback-safe).
2. Reflect backend contracts without duplicating business logic.
3. Avoid direct DB dependencies.

## Main Views

- Overview
- Risk
- Regimes
- Model
- Trades
- Strategies
- Assets

## API Integration

- Service file: `src/services/api.ts`
- Base URL: `VITE_API_BASE_URL` or `/api/v1`
- Backend expected at `http://localhost:8000` when running locally.

## Local Development

```bash
cd src/layer5/frontend
npm install
npm run dev
```

## Production Build

```bash
npm run build
```

## Key Reliability Constraints

1. Views must not crash when API payloads are empty or partial.
2. Initial render should use safe defaults for stateful data objects.
3. Navigation between tabs must never hard-fail due to missing nested fields.

## Notes

1. The app currently reports bundle-size warnings during production build; this is non-blocking.
2. Code splitting can be added later if chunk size becomes a deployment concern.

## Upcoming UI Enhancements

1. Add macro intelligence cards/charts sourced from `Fact_Macro_Events` (FinBERT sentiment, dispersion, event surprise).
2. Add event-window overlays in trades/risk views for contextual interpretation of approvals/vetoes.
3. Keep all macro views read-only and contract-driven from Layer 5 API.
