# FND-007 — CI/CD & Automated Test Harness

- **Task ID**: FND-007
- **System**: Foundational & Cross-Cutting
- **Priority**: P1-High
- **Estimated Effort**: 3d
- **Prerequisites**: FND-003
- **External Dependencies**:
  - A CI runner. Recommended: **GitHub Actions** (free tier ample for a solo repo) or a self-hosted runner on Computer 1 if the repo stays private/local. *Why:* manual `black`/`mypy`/`pytest` runs are easy to skip; a multi-system refactor needs an automated gate.
  - A **Docker registry** (GitHub Container Registry / self-hosted) to publish per-system images. *Why:* the three systems deploy to three hosts and need reproducible, versioned build artifacts.
  - CI-scoped secrets via FND-003 (dummy/test credentials only — never live broker keys in CI).

## Objective
Establish a CI/CD pipeline with quality gates and an automated, per-system test harness so every change is linted, type-checked, tested, built, and publishable before deployment.

## Current State
Tooling exists but is run by hand: `pytest src/...`, `black src/`, `mypy src/`, and `pytest --cov=src`. Tests are scattered per layer (`src/layer0/tests/`, `src/layer3_ml/tests/`, `src/layer4_executor/tests/` with `--live-sim`, `src/layer7/tests/`). There is no CI, no enforced gate, no build/publish step, and no environment to run integration tests across the new three-system topology.

## Target State
- A CI pipeline triggered on push/PR running: format check (`black --check`), type check (`mypy`), lint, unit tests with coverage, and fast integration tests using ephemeral PostgreSQL + Redis service containers.
- Per-system test suites runnable in isolation (`system1`, `system2`, `system3`, `foundational`) and as a whole.
- A CD step building and publishing versioned per-system Docker images to the registry, with deploy to each host gated on green CI.
- Coverage and quality thresholds enforced as merge gates.

## Technical Specification

### Pipeline stages
1. **Static:** `black --check`, `mypy src/`, lint, and the FND-003 secret-scan (block plaintext secrets).
2. **Unit:** `pytest` per package with coverage; fail under an agreed threshold (start at current baseline, ratchet up).
3. **Integration:** spin up PostgreSQL+TimescaleDB and Redis as CI service containers; run cross-component tests (e.g. Layer 3 → queue → Decision Gate → outbound queue) against dummy data and the OANDA **practice** sandbox or a recorded fixture — never live.
4. **Build:** build per-system Docker images tagged with git SHA + semver; run a container smoke test.
5. **Publish:** push images to the registry on main/tags.
6. **Deploy (manual approval):** promote a tagged image to a host; deploy is operator-approved, not fully automatic, given trading risk.

### Test harness organization
- Test markers/paths: `-m system1|system2|system3|foundational`, plus `--live-sim` for Layer 4 execution simulation and a new `--integration` marker for cross-system flows.
- Deterministic fixtures: fixed signal/regime/model inputs assert deterministic Decision-Gate and execution outputs (honors the determinism contract).
- Backtest/statistical checks (System 1) run as a longer scheduled job, not on every PR, to keep PR feedback fast.

### Secrets in CI
- CI uses only dummy credentials and OANDA practice (or recorded fixtures). Live broker/DB secrets are never exposed to CI runners. Enforced via FND-003 scoping (CI key cannot decrypt live secrets).

## Testing & Validation
- A PR with a formatting violation, a type error, or a failing test is **blocked** by the gate (verify each independently).
- The integration job stands up PostgreSQL+Redis, runs a signal→decision→order flow, and asserts the expected approved/rejected outcome.
- The secret-scan blocks a deliberately committed plaintext credential.
- A green build produces per-system images in the registry that pass a container smoke test.
- A deliberately introduced regression in Decision-Gate output is caught by the deterministic fixture test.

## Rollback Plan
CI/CD is orthogonal to runtime — if the pipeline breaks, deployment falls back to the current manual process (`black`/`mypy`/`pytest` + manual image build) and services already deployed are unaffected. A bad published image is rolled back by redeploying the previous tagged image (registry retains prior versions).

## Acceptance Criteria
- [ ] CI runs format + type + lint + unit (with coverage) + secret-scan on every push/PR and blocks merges on failure.
- [ ] An integration job exercises a cross-system signal→decision→order flow against ephemeral PostgreSQL+Redis with no live credentials.
- [ ] CD builds and publishes versioned per-system Docker images to the registry on main/tags.
- [ ] Per-system test suites are runnable in isolation and collectively.
- [ ] Deterministic fixtures catch a regression in Decision-Gate / execution output.

## Notes & Risks
- **Never expose live broker or DB secrets to CI** — practice/dummy only; this is a hard rule, enforced by FND-003 scoping.
- Keep PR feedback fast: heavy backtests/statistical validation belong in scheduled jobs, not the PR gate.
- For a solo operator, fully automatic deploy-to-trading is risky; keep deploy operator-approved.
- Coverage thresholds should ratchet, not start punitive, to avoid blocking incremental migration work.
