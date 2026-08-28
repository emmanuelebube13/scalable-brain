# docs/design/ — system design documentation

Architecture decisions, data models, design specs, and research design standards.
The canonical reference for *how the system is designed to work*.

## What is in this folder

| Path | What it covers |
|---|---|
| `ADR-001-where-inference-runs.md` | Architecture Decision Record: should inference run on System 1 or System 2? (PROPOSED 2026-08-22) |
| `REGIME_STATE_AND_HOW_TO_RUN.md` | Which regime label is which; how to re-run regime models |
| `REGIME_LABELS_EXPLAINED.md` | Authoritative explanation of the 4 regime labels and the CSRM |
| `REGIME_AWARE_MODEL.md` | Design notes for the regime-aware model experiment (R3, concluded 2026-08-16) |
| `STRATEGY_EXPERIMENT_STANDARD.md` | **The contract every research experiment must follow.** 8 rules. Read before starting an experiment |
| `BUNDLE-CONSUMER-GUIDE.md` | How System 2 / System 3 fetch, verify, and use the published model bundle |
| `SYSTEM_ARCHITECTURE_EXPLANATION.md` | High-level architecture explanation |
| `README_LAYER0_INTEGRATION.md` | How Layer 0 qualification artifacts promote to Layer 2 runtime config |
| `README_SWING_ENGINE.md` | Layer 0 swing engine overview |
| `architecture/` | Detailed architecture diagrams and system design docs |
| `assets/` | Design assets |
| `database/` | Database design docs (ERD, data dictionary). Note: operational SQL rules are in `docs/database/` |
| `diagrams/` | System diagrams |
| `project_management/` | Project management design artifacts |
| `systems/` | Per-system design specs |
| `ui_ux/` | UI/UX design |

## What goes here

- Architecture Decision Records (`ADR-<N>-<slug>.md`)
- Design specifications and data models
- Research design standards (like `STRATEGY_EXPERIMENT_STANDARD.md`)
- Technical guides for understanding how things work

## Do NOT put here

- Work items (→ `task/`)
- Bug reports or fix proposals (→ `docs/proposed-fixes/`)
- Correspondence with other systems (→ `docs/comms/`)
- Research notes and exploratory analysis (→ `docs/research/`)
