# T6 — Research Strategy Engine (sandbox): contract, registry, promotion pipeline

> Paste this whole file as the prompt. Repo: `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`. Venv active.
> **First action: read `task/2026-W31/STATE.md`.** Requires T1 = DONE (builds directly on the repaired `src/layer0/strategies` package). This is the week's innovation track — design fully, implement the skeleton; the full engine may extend past this week and that is fine.

## Mission

Formalize what already exists informally (`strategies/research/`, `strategieStaged/`) into a real pipeline: a **strategy contract** (one interface every strategy implements), a **registry** (single source of truth for what exists and at what stage), and a **promotion pipeline** research → staged → qualified that runs the SAME leak-free walk-forward gates the vetting/gatekeeper stack now enforces. New strategy ideas get a sandbox to be tested and verified in — and can never reach live qualification through any door except the gates.

## Read first

- `src/system1/vetting/vet.py` + `gates.py` — the qualification gates (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo) — the sandbox must reuse these, not reimplement them
- `src/system1/validation/walk_forward.py` — the shared fold logic (min_train=36mo, step=6mo, OOS=6mo, anchored); the sandbox must use it so research backtests are leak-free by construction
- `src/layer0/backtest_engine.py`, `src/layer0/indicators.py` — the primitives strategies are built on; note the cost model (spread 1.0 pip, slippage 0.5 pip entry-only, commission 0)
- 2–3 existing strategies (post-T1 rename) — extract the de-facto interface they share
- `docs/SYSTEM1_ANALYSIS_2026-07-01.md` findings B & C — regimes don't discriminate, concentration risk: the sandbox exists to grow honest candidates, not to relax standards

## Agent team

- **Agent A (Plan):** design doc (step 1). Runs first, alone.
- **Agent B (general-purpose):** contract + registry implementation (steps 2–3).
- **Agent C (general-purpose):** promotion pipeline CLI + migration of one pilot strategy (steps 4–5).
- **Agent D (general-purpose, reviewer):** adversarial review of the design against the leak/gate discipline — tries to find a path where an unvetted strategy could reach `qualified` or where research code could touch live tables. Runs after B and C.

## Execution plan

1. **Design doc (Agent A).** `docs/design/RESEARCH_STRATEGY_ENGINE.md`: the three stages and their guarantees; the contract API; registry schema; how the sandbox gets data (read-only feature-store/price access — research must NEVER write to `fact_*` tables); how promotion invokes the existing vet gates; how this integrates with MODEL-005 without creating a second qualification path. Include a one-page "strategy author's guide": how the user drops in a new idea and gets a verdict.
2. **Contract (Agent B).** `src/layer0/strategies/contract.py`: an ABC `Strategy` with the minimal surface extracted from existing strategies (identity: `strategy_id`, `name`, `version`; `required_indicators`; `generate_signals(df) -> signals` — trailing-only data in, no look-ahead possible by construction; declared `granularities` and `pairs`). Plus `StrategyMetadata` (stage, author, created, hypothesis text — force authors to state the edge hypothesis, a research-hygiene practice). Type-hinted, mypy-clean.
3. **Registry (Agent B).** `src/layer0/strategies/registry.py`: discovers contract-compliant strategies from the three stage packages (`research/`, `staged/`, `qualified/` — create as proper packages; migrate `strategieStaged` content into `staged/`), validates uniqueness of `strategy_id` (a known past bug — duplicate strategy_id collapsed weights, FIX-S1-004; make the registry reject duplicates loudly), and answers `list(stage=...)`, `get(id)`. The vetting stage reads qualified candidates FROM the registry — one source of truth.
4. **Promotion pipeline (Agent C).** `python -m src.layer0.strategies.promote <strategy_id> --to staged|qualified`:
   - research → staged: contract compliance + unit smoke test + a walk-forward backtest using `validation/walk_forward.py` folds with the standard cost model; produces a report (per-fold OOS metrics), stored under `results/research/<strategy_id>/`
   - staged → qualified: runs the FULL vet gates (import and call `vetting/gates.py` — do not copy thresholds) on OOS folds only; refuses promotion on any gate failure with a per-gate explanation
   - all promotions are `git mv` + registry update + report artifact — auditable, reversible
   - **hard rule enforced in code:** nothing in `research/` or `staged/` is importable by the live pipeline; `vet.py` only sees `qualified/`
5. **Pilot (Agent C).** Migrate ONE existing strategy through the machinery end-to-end (pick a currently-unqualified one, e.g. from `mean_reversion/`): register at `research`, promote to `staged` (report produced), attempt `qualified` — whether it passes or fails the gates, capture the verdict + report as the demonstration. A gate REJECTION with a clear per-gate explanation is a fully successful pilot.
6. **Adversarial review (Agent D).** Attempt: promoting a strategy that skips gates; a research strategy writing to the DB; a look-ahead strategy passing the walk-forward (e.g. using `shift(-1)`); duplicate `strategy_id`. Each attempt must be blocked by code, not convention. File findings; Agent B/C fix anything that gets through.

## Validation

```bash
pytest src/layer0/strategies -v                       # contract, registry, promotion tests green
python -m src.layer0.strategies.promote --list        # registry lists all strategies with stages
mypy src/layer0/strategies
pytest src/system1 -v                                  # vetting still green — no regression in the live path
```

Pilot evidence: `results/research/<pilot_id>/` contains the fold report and the promotion (or rejection) verdict.

## Acceptance criteria

- [x] `docs/design/RESEARCH_STRATEGY_ENGINE.md` incl. the strategy author's guide
- [x] `contract.py` + `registry.py`; `DuplicateStrategyId` raised across all stages; mypy clean on the 4 new modules (remaining errors are pre-existing in legacy `strategieStaged/`)
- [x] `promote.py`; staged→qualified imports `vetting/gates.py` — a test asserts no threshold literal appears in the module
- [x] `test_live_vetting_path_sees_only_qualified` plants strategies in all three stages; `registry.qualified()` returns only the qualified one
- [x] `rsi_mean_reversion`: research→staged PROMOTED, staged→qualified **REFUSED** with 5 per-gate reasons over 9,806 OOS trades. File stayed in `staged/`.
- [x] 14 tests; all four attacks (plus a subtler look-ahead variant and a self-declared-stage attempt) blocked by code with source-level assertions

## Deliverables (required — task is not DONE without them)

Write to `task/2026-W31/deliverables/T6/`:

1. **`DELIVERABLE.md`** — detailed report: the contract API surface, registry behavior (incl. duplicate-id rejection proof), promotion CLI usage with real command transcripts, the pilot strategy's full journey with its verdict, the four adversarial attacks and how each is blocked *by code* (file:line), what remains for the full engine beyond this week, commit SHAs.
2. **Visuals (2 PNGs):**
   - `pipeline_diagram.png` — the research → staged → qualified flow: boxes per stage, the gate wall between staged and qualified listing the actual thresholds (PF≥1.5, Sharpe≥0.8, MaxDD≤25%, WinRate≥40%, Recovery≥3.0, OOS≥60mo), the walk-forward harness feeding both, and a red X on every bypass path the adversarial review tried. This is the picture you show anyone asking "how does a new idea reach live?"
   - `pilot_folds.png` — the pilot strategy's per-fold OOS metrics (Sharpe and PF per walk-forward fold as grouped bars) with the gate thresholds as horizontal lines — makes the pass/fail verdict visually obvious.
3. **`EXECUTIVE_SUMMARY.md`** — max 1 page: you now have a sandbox where any new strategy idea gets registered, backtested leak-free, and either promoted through the same gates the live system uses or rejected with per-gate reasons; the informal folders are formalized; there is provably no side door to live; what the pilot showed; what the next increment of the engine is.

## On failure

Log to `## Failure log`, correct the step, update STATE.md. If the week runs out mid-task, the design doc + contract + registry (steps 1–3) are the minimum shippable unit — record exactly which step the pipeline implementation stopped at.

## Failure log

**2026-07-29 — step 3's `strategieStaged` migration was NOT performed, deliberately.**
Those 6 strategies implement `StrategyBase`, not the new contract, and they are the *currently
live qualified set*, reached through the `layer0.strategies` re-exports that
`qualify_strategies.py` depends on — the exact import chain T1 repaired this week. Migrating
them into `staged/` would have demoted the live model and re-broken that chain. *Correction:*
the next increment is a `LegacyStrategyAdapter` registering them as `qualified` in place;
recorded in the design doc under "What is NOT built yet".

**2026-07-29 — the first `_aggregate_cell` reimplemented the metrics and got drawdown wrong.**
It divided by a near-zero early peak and reported MaxDD 1650%. *Root cause:* writing new metric
code instead of importing the existing one — the same mistake pattern as copying thresholds.
*Fix:* import `src.system1.attribution.metrics` and use the live `max_drawdown` (bounded in
[0,1) by construction), `profit_factor`, `annualized_sharpe`, `recovery_factor`, `win_rate`,
plus `validate_metrics` sanity bounds. Corrected value: 99.7%.

**2026-07-29 — `_git_mv` could not promote an untracked strategy.**
`git mv` refuses untracked sources, but a freshly-authored research idea is normally untracked —
the common case, not an error. *Fix:* detect tracking state and fall back to a filesystem move
plus `git add`.

**2026-07-29 — the backtest engine needed an adapter.**
The contract's `generate_signals(df)` does not match the engine's
`calculate_indicators/generate_signals(df, asset, granularity)` surface. *Fix:*
`engine_adapter.py`, which also imposes uniform ATR stops so no research strategy can flatter
itself with bespoke exit logic.
