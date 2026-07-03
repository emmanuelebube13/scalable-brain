# Documentation Index (Current)

Last updated: 2026-04-06

This index defines canonical documentation for the current system structure.

## Canonical Documents

1. `README.md`
   - High-level system map and runbook.

2. `docs/design/SYSTEM_ARCHITECTURE.md`
   - Current 8-layer architecture and layer contracts.

3. `docs/design/ERD_ACTIVE_SCHEMA_2026.md`
   - Active table/contract mapping used by runtime code.

4. `src/layer5/README_LAYER5.md`
   - Layer 5 backend/frontend telemetry scope and endpoints.

5. `src/layer5/frontend/README.md`
   - Frontend runtime, integration, and reliability constraints.

6. `src/layer0/README_LAYER0_INTEGRATION.md`
   - Layer 0 to Layer 2 promotion workflow.

7. `frontend/index.html`
   - HTML documentation/navigation landing for architecture, research, schema, and operational guides.

8. `frontend/architecture.html`
   - Human-readable architecture narrative aligned to current layer contracts.

9. `frontend/data_dictionary_updated.html`
   - Runtime-aligned schema dictionary used by operators and analysts.

10. `frontend/erd_interactive.html`
    - Interactive ERD and relationship explorer for active/deprecated table sets.

11. `src/nlp/finbert.py` + `src/nlp/macro_scraper.py`
    - NLP macro intelligence implementation references for upcoming integration.

## Historical and Non-Canonical Docs

The files below are retained as historical records or notes and should not be treated as current architecture source of truth.

- `docs/notes/content/FIXES_APPLIED_2026_04_05.md` (historical fix report)
- `results/**/*.md` (generated run artifacts)
- `docs/notes/**/*.md` (working notes)

## Update Policy

1. When architecture contracts change, update `README.md`, `docs/design/SYSTEM_ARCHITECTURE.md`, and this index in the same commit.
2. When schema contracts change, update `docs/design/ERD_ACTIVE_SCHEMA_2026.md` and relevant layer README files.
3. Generated reports under `results/` are immutable run artifacts and should not be rewritten as canonical docs.

## Current Documentation Focus Areas

1. Keep all architecture references aligned to the 8-layer runtime model.
2. Keep Layer 4 runtime status and schema compatibility notes current.
3. Track NLP/FinBERT as an auxiliary implemented service with upcoming Layer 3/4 integration milestones.
