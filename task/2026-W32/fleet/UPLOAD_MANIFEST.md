# Upload manifest — exactly what to send, per wave

Repo root below is `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`.
Everything is a path relative to that.

---

## Wave 0 — spec extraction (send now)

**Prompt:** `task/2026-W32/fleet/WAVE0_SPEC_EXTRACTION.md`

| File | Path |
|---|---|
| The 51 strategies | `src/layer0/strategies/strategieStaged/forex_swing_strategies.csv` |
| The design spec | `docs/design/CONTRACT_V2_AND_POSITION_ENGINE.md` |
| Data availability | `task/2026-W32/fleet/DATA_AVAILABILITY.md` |
| Indicator inventory | `task/2026-W32/fleet/INDICATOR_INVENTORY.md` |

**Per-agent instruction:** append one line — `You are assigned row N.` — for N = 1…51.

That is four files plus the row assignment. Wave 0 needs no source code: it produces
documents, not modules.

---

## Wave 1 — engine build (send now, concurrently)

**Prompt:** `task/2026-W32/fleet/WAVE1_ENGINE_BUILD.md`

| File | Path | Why |
|---|---|---|
| **The spec** | `docs/design/CONTRACT_V2_AND_POSITION_ENGINE.md` | authoritative |
| v1 contract | `src/layer0/strategies/contract.py` | extend; do not edit |
| Uniform adapter | `src/layer0/strategies/engine_adapter.py` | reference |
| Incumbent engine | `src/layer0/core_engine/backtest_engine.py` | conventions; **never edit** |
| MTF engine | `src/layer0/core_engine/multi_timeframe.py` | verify + wire |
| Indicators | `src/layer0/data_access/indicators.py` | inventory |
| Promotion CLI | `src/layer0/strategies/promote.py` | integration point |
| Registry | `src/layer0/strategies/registry.py` | integration point |
| Data access | `src/layer0/strategies/research_data.py` | the only data door |
| Folds | `src/system1/validation/walk_forward.py` | import; never reimplement |
| Gates | `src/system1/vetting/gates.py` | import; never reimplement |
| Metrics | `src/system1/attribution/metrics.py` | import; never reimplement |
| Look-ahead findings | `task/2026-W32/lookahead-audit/FINDINGS.md` | why swings are banned |
| Existing tests | `src/layer0/strategies/tests/` | must keep passing |
| Data availability | `task/2026-W32/fleet/DATA_AVAILABILITY.md` | pairs/granularities |
| Pilot report | `results/research/rsi_mean_reversion/qualification_refused_20260802T221725Z.json` | the output shape to preserve |

**Do not upload:** `.env`, anything under `secrets/`, `configuration/`. No credentials leave
this machine — the fleet needs code and schema, never keys.

---

## Wave 2 — strategy authoring (⛔ HOLD until Wave 1 is reviewed)

**Prompt:** `task/2026-W32/fleet/WAVE2_STRATEGY_AUTHORING.md`

| File | Path |
|---|---|
| **That agent's own spec** | `SPEC-<strategy_id>.md` (Wave 0 output) |
| Frozen contract | `src/layer0/strategies/contract_v2.py` (Wave 1 output) |
| Position engine | `src/layer0/strategies/position_engine.py` (Wave 1 output) |
| Causal structure | `src/layer0/strategies/causal_structure.py` (Wave 1 output) |
| Worked example | `REFERENCE_STRATEGY.py` (I write this after reviewing Wave 1) |
| Indicators | `src/layer0/data_access/indicators.py` |
| Indicator inventory | `task/2026-W32/fleet/INDICATOR_INVENTORY.md` |
| Data availability | `task/2026-W32/fleet/DATA_AVAILABILITY.md` |

**Each agent gets only its own `SPEC-*.md`** — not all 51. One agent, one strategy, no
cross-contamination of interpretation.

Note Wave 2 does **not** receive the CSV. By then the spec is the source of truth; handing
back the raw prose invites an agent to re-litigate decisions that were already made and
reviewed.

---

## Bringing work back

Ask for output as a **single archive per wave** with this layout, so I can review in one
pass rather than reassembling:

```
wave0/
  SPEC-<id>.md            × 51
  DATA-GAP-<id>.md        × however many
wave1/
  contract_v2.py  position_engine.py  causal_structure.py
  tests/...
  WAVE1_REPORT.md
wave2/
  <id>.py                 × 51
  tests/test_<id>_fixture.py × 51
  REPORT-<id>.md          × 51
```

Nothing gets written into the repo until I have reviewed it. The fleet produces candidate
files; wiring them in is done here, on this machine, against the real database.
