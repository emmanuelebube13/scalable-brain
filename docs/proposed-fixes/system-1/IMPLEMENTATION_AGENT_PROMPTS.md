# System-1 Proposed-Fixes — Multi-Agent Implementation Prompts

**Purpose:** A single, copy-pasteable playbook for working through the open System-1 fixes
(`FIX-S1-002 … FIX-S1-006`) with Claude Code subagents. Each fix has: a sequencing slot, the
agents to spawn, the skills to load, the exact files in scope, the steps, and the **definition of
done** (artifacts + tests + register update). FIX-S1-001 is already **Closed/Promoted** and is
listed only as the dependency baseline.

> **How to drive this:** from the repo root, hand the orchestrator (you, the top-level session) one
> phase at a time. Within a phase, spawn the named subagents with the copy-paste prompt blocks
> below. Do **not** run phases out of order — the dependency graph in §2 is load-bearing.

---

## 1. Global rules (apply to EVERY fix — bake into every agent prompt)

1. **Log-only first, never auto-promote.** All re-runs of MODEL-004/005/006/009 write `proposed_*`
   artifacts only. The currently-promoted bundle stays authoritative until a human sign-off. No
   agent calls a `--promote` path.
2. **One thing at a time.** Each fix is its own branch/worktree, its own test run, its own log-only
   diff, its own register status bump. Do not bundle two fixes in one change set.
3. **A gate that can never fire is a bug.** Every fix that touches a gate/guard must ship a
   regression test proving the gate *can return False* (mirrors the FIX-S1-001 sanity-bound guard).
4. **Schema-aware + project conventions.** Connect via `src/common/db.py`; parameterized SQL only;
   double-quote `"Open"`/`"Close"`/`"timestamp"`, lowercase everything else; `INSERT … ON CONFLICT`
   for idempotent writes. Type hints + docstrings; `black` + `mypy` clean.
5. **Tests are the contract.** Run the owning package's suite (`pytest src/system1/<pkg>/tests/ -v`)
   and keep the whole System-1 suite green. New behavior ⇒ new tests in the same change set.
6. **Update the register.** On completion, bump the row in `docs/proposed-fixes/README.md`
   (`Proposed → Implemented → Verified`) and add an implementation note to the fix file's header,
   exactly as FIX-S1-001 did.
7. **Report the diff, faithfully.** Every fix produces a before/after metric or artifact diff
   attached to the fix file. If a re-run shrinks the qualifying set or the OOS uplift, say so plainly
   — shrinkage is the expected, correct outcome for the OOS/leakage fixes.

---

## 2. Sequencing & dependency graph

```
FIX-S1-001 (metrics)  ──[CLOSED/PROMOTED, baseline]
        │
        ▼
Phase A  FIX-S1-004  (P0, weights collapse)        ← live-affecting TODAY; smallest; do first
        │
        ▼
Phase B  FIX-S1-002  (P1, true OOS walk-forward)    ← builds the walk-forward machinery
        │
        ▼
Phase C  FIX-S1-005  (P1/P0, causal regime labels)  ← reuses walk-forward; re-runs regime→attr→gk
        │
        ├────────────► Phase D  FIX-S1-003 (P1, regime discrimination)  ← needs causal labels
        │
        ▼
Phase E  FIX-S1-006  (P1, deployment gates inert)   ← needs MODEL-006 oos_uplift (from Phase C)
```

**Why this order**
- **S1-004 first:** it is the only *currently-live* corruption (Ranging weight `5e-8`), and it is a
  pure-function + post-condition fix — highest risk/effort ratio.
- **S1-002 before S1-005:** both are walk-forward/OOS-honesty fixes; S1-002 introduces the
  `is_oos`/`fold_id` tagging and walk-forward pass that S1-005 reuses.
- **S1-003 after S1-005:** the regime-discrimination question can only be answered on *causal*
  labels; measuring it on leaked labels would repeat the original sin.
- **S1-006 last:** `oos_uplift_ok` can't be armed until MODEL-006 actually produces an OOS uplift
  (Phase C re-runs the gatekeeper), and `beats_incumbent` needs the serializer change.

---

## 3. Agent & skill roster

**Claude Code subagents** (spawn via the Agent tool):

| Role in this playbook | `subagent_type` | When |
|---|---|---|
| **Designer** | `Plan` | Up-front design for the larger fixes (S1-002, S1-005, S1-003). Returns step plan + critical files + trade-offs. No edits. |
| **Investigator** | `Explore` | Read-only fan-out (S1-003 discrimination study, locating every consumer of a label/key). |
| **Implementer** | `general-purpose` | Writes code + tests, runs the log-only re-run, produces the diff. Full tool access. |
| **Reviewer** | (skill) `/code-review high` | Correctness review of the implementer's diff before sign-off. |
| **Verifier** | (skill) `/verify` | Confirms the re-run/test actually behaves as claimed. |

**Project skills to load** (read the file, then follow it as the canonical spec — paths are under
`docs/implementation-roadmap/system-1-model-building/tasks/skills/`):

| Skill file | Governs | Used by fix |
|---|---|---|
| `financial-metrics.md` | canonical Sharpe/MaxDD/Recovery/OOS formulas | S1-002 |
| `point-in-time-leakage.md` | causal vs leaked joins, look-ahead tests | S1-002, S1-005 |
| `vetting-gate.md` | gate definitions, weights, sum-to-1 invariant | S1-004, S1-006 |
| `hmm-semantic-mapping.md` | regime label semantics & mapping | S1-005, S1-003 |
| `postgres-patterns.md` | `src/common/db.py`, ON CONFLICT, column case | any fix touching the DB |
| `object-storage-protocol.md` | bundle/manifest serialization | S1-006 |

**Contracts** (JSON, in `contracts/`): `weights-contract.json` (S1-004),
`regime-map-contract.json` (S1-003/005), `signal-message-contract.json`.

---

## 4. Per-fix prompt blocks

Each block is structured: **Slot · Agents · Skills · Files · Result required**, then a
**copy-paste agent prompt**. Run the Plan agent first where present, fold its plan into the
Implementer prompt, then run Reviewer + Verifier.

---

### Phase A — FIX-S1-004: per-regime weights collapse on duplicate strategy_id

- **Severity/why-first:** P0, live-affecting today (Ranging resolves to `{"10": 5e-08}`). Smallest
  blast radius — a pure function + a post-condition + a contract tweak.
- **Agents:** Implementer (`general-purpose`) → Reviewer (`/code-review high`) → Verifier (`/verify`).
  No Plan agent needed (root cause and fix are already concrete in the fix doc).
- **Skills:** `vetting-gate.md`, `postgres-patterns.md`.
- **Files in scope:** `src/system1/vetting/gates.py` (`normalized_weights`),
  `src/system1/vetting/vet.py` (`build`), `contracts/weights-contract.json`,
  `src/system1/vetting/tests/test_gates.py`.
- **Result required:**
  1. `normalized_weights` keyed by the **variant identity** (`f"{strategy_name}@{granularity}"` or a
     stable `(strategy_id, granularity)` string) the map already uses.
  2. Hard post-condition in `vet.build`: every non-empty regime asserts
     `abs(sum(weights.values()) - 1.0) < 1e-6`, else **fail the run**.
  3. Explicit, documented duplicate policy (keep-both-summed-to-1 **or** deliberate collapse-to-best
     — pick one, write it in the docstring).
  4. New regression test: two cells same `strategy_id`, different granularity → two keys summing to
     1.0; property test `sum == 1.0 (±1e-9)` for arbitrary regime lists.
  5. Log-only MODEL-005 re-run producing `proposed_strategy_weights.json`; **diff vs the broken
     `strategy_weights.json`** attached to the fix file; confirm every non-empty regime sums to 1.0.
  6. Confirm Computer-2 sizing consumer's key space matches (variant vs strategy_id) — note the
     reconciliation in the fix file.
  7. Register row → **Implemented**, header note added.

> **Copy-paste — Implementer (`general-purpose`):**
> "Implement FIX-S1-004 in the Scalable_Brain repo. Read
> `docs/proposed-fixes/system-1/FIX-S1-004-weights-collapse-duplicate-strategy-id.md` and the
> `vetting-gate` skill (`docs/implementation-roadmap/system-1-model-building/tasks/skills/vetting-gate.md`)
> in full first. The bug: `src/system1/vetting/gates.py:normalized_weights` keys the weight dict by
> `str(strategy_id)`, so when one strategy qualifies at two granularities in a regime the dict
> overwrites itself and the regime's weights stop summing to 1 (shipped `Ranging = {'10': 5e-08}`).
> (1) Re-key weights by the variant identity the map uses (`name@granularity`). (2) Add a post-
> condition in `src/system1/vetting/vet.py:build` that fails the run if any non-empty regime's
> weights don't sum to 1.0 (±1e-6). (3) Document the duplicate-strategy policy in the docstring.
> (4) Add regression + property tests in `src/system1/vetting/tests/test_gates.py`. (5) Update
> `contracts/weights-contract.json` patternProperties if the key format is constrained. Keep all of
> `pytest src/system1/vetting/tests/ -v` green, run `black`+`mypy`. Then do a LOG-ONLY MODEL-005
> re-run to emit `proposed_strategy_weights.json` (NO promotion), and produce a before/after diff
> table of per-regime weight sums. Do NOT touch the live promoted artifact. Return: files changed,
> test output, the diff table, and the exact text to append to the fix file's header + the register
> row update. Follow the repo's global rules in
> `docs/proposed-fixes/system-1/IMPLEMENTATION_AGENT_PROMPTS.md §1`."

---

### Phase B — FIX-S1-002: "OOS≥60mo" gate measures in-sample span, not true OOS

- **Severity:** P1, but it is the **anti-overfitting guard** and currently never fires
  (`oos_fail: 0`). Medium-large: re-architects the qualification/backtest pass.
- **Agents:** **Plan** (`Plan`) → Implementer (`general-purpose`) → Reviewer (`/code-review high`) →
  Verifier (`/verify`). Plan agent is mandatory here — the fix doc deliberately leaves the design open
  (Option A walk-forward vs Option B holdout).
- **Skills:** `financial-metrics.md` (`oos_month_span`), `point-in-time-leakage.md`,
  `postgres-patterns.md`.
- **Files in scope:** `src/system1/attribution/attribute.py` (`_cell_metrics` `oos_months`),
  `src/system1/vetting/gates.py` (OOS gate), `fact_trade_outcomes` schema (new `is_oos`/`fold_id`),
  the Layer-0/qualification backtest pass, `financial-metrics` skill (`oos_month_span`),
  attribution/serializer tests.
- **Result required:**
  1. **Decision recorded** (Plan agent): Option A (walk-forward, recommended) vs Option B (holdout).
     Default to **A** unless the Plan agent surfaces a blocking cost.
  2. `fact_trade_outcomes.is_oos` (bool) and/or `fold_id` column (ON CONFLICT-safe migration).
  3. Attribution computes **all** gate metrics (PF/Sharpe/MaxDD/Recovery/WinRate/oos_months) on
     **OOS trades only**; `oos_months` = union span of OOS windows via `oos_month_span`.
  4. **A gate-can-fire test:** a deliberately overfit strategy passes in-sample but **fails** OOS
     gates (proves the gate is no longer inert).
  5. Log-only qualification re-run; expect the qualifying set to **shrink** vs the FIX-S1-001 map —
     attach the before/after qualifying-set diff to the fix file.
  6. Honest rename in the skill + map lineage ("oos_months counts OOS only").
  7. Register row → **Implemented**.

> **Copy-paste — Plan (`Plan`):**
> "Design the implementation for FIX-S1-002 (true out-of-sample qualification) in the Scalable_Brain
> repo. Read `docs/proposed-fixes/system-1/FIX-S1-002-oos-not-true-out-of-sample.md`, the
> `financial-metrics` and `point-in-time-leakage` skills, and the current code:
> `src/system1/attribution/attribute.py` (`_cell_metrics`), `src/system1/vetting/gates.py`, and the
> qualification/backtest pass that populates `fact_trade_outcomes`. Produce a concrete plan that
> chooses Option A (walk-forward folds, recommended) vs Option B (reserved holdout): the schema
> change (`is_oos`/`fold_id`), where fold boundaries are produced and recorded, how attribution is
> taught to filter to OOS trades, the migration approach (ON CONFLICT-safe), the new tests including
> the 'overfit strategy must fail OOS' regression, and the re-run/diff plan. Identify every file that
> must change and the order to change them. Do NOT edit files. Return the step-by-step plan + risks."

> **Copy-paste — Implementer (`general-purpose`):** *(paste the Plan agent's chosen design at the
> top, then:)* "Implement the approved FIX-S1-002 plan above. Honor repo global rules
> (`IMPLEMENTATION_AGENT_PROMPTS.md §1`): log-only re-run, no promotion, schema-aware DB via
> `src/common/db.py`, parameterized SQL, `black`+`mypy` clean, full System-1 suite green. Tag each
> trade `is_oos`, compute gate metrics on OOS trades only, rename `oos_months` honestly, and add the
> 'overfit strategy fails OOS' regression test. Then run qualification LOG-ONLY and produce the
> before/after qualifying-set diff (it should shrink). Return: files changed, migration, test output,
> the qualifying-set diff, and the fix-file header note + register update text."

---

### Phase C — FIX-S1-005: regime labels are non-causal (look-ahead leak)

- **Severity:** P1, arguably P0 — leaks future data into attribution **and** the gatekeeper's OOS
  uplift (its headline edge proof). Shares walk-forward machinery with Phase B.
- **Agents:** **Plan** (`Plan`) → Implementer (`general-purpose`) → Reviewer (`/code-review high`) →
  Verifier (`/verify`).
- **Skills:** `point-in-time-leakage.md` (primary), `hmm-semantic-mapping.md`, `postgres-patterns.md`.
- **Files in scope:** `src/system1/regime/hmm_regime.py` (fit + label emission),
  `src/system1/attribution/attribute.py` (`tag_regime_at_entry`),
  `src/system1/gatekeeper/train.py` (`build_frame`, `_walk_forward`), `fact_market_regime_v2`
  schema (new causal-label columns), `champion_manifest.json` `regime_features`, regime tests.
- **Result required:**
  1. **Causal label path:** emit per-bar labels from a **forward-only filtered posterior**
     `P(state_t | x_1..x_t)` *or* a **walk-forward re-fit** (reuse the `_train_sequences` scaffolding
     and Phase B's walk-forward machinery). Drop smoothed `predict_proba`/Viterbi for the *consumed*
     label.
  2. **Persist both** a causal label (for ML/attribution) and the smoothed label (post-hoc reporting
     only), schema-distinguished so no consumer can train on the smoothed one.
  3. **Leakage regression test:** mutating bars strictly after `t` must not change the emitted
     label/posterior at `t` (invert the §2B demonstration in the fix doc into an assertion).
  4. Re-run MODEL-004 (attribution) and MODEL-006 (gatekeeper) on causal labels, log-only; report the
     **OOS-uplift before/after** (expect it to **shrink** toward its honest value) and the per-regime
     attribution distribution shift. Attach both diffs to the fix file.
  5. Register row → **Implemented**; flag the impact on the current champion's claimed edge.

> **Copy-paste — Plan (`Plan`):**
> "Design FIX-S1-005 (causal regime labels) for the Scalable_Brain repo. Read
> `docs/proposed-fixes/system-1/FIX-S1-005-regime-labels-non-causal-leakage.md`, the
> `point-in-time-leakage` and `hmm-semantic-mapping` skills, and the code:
> `src/system1/regime/hmm_regime.py`, `src/system1/attribution/attribute.py:tag_regime_at_entry`,
> `src/system1/gatekeeper/train.py` (`build_frame`, `_walk_forward`). Choose between filtered
> forward-only inference vs walk-forward re-fit for the consumed label (and whether to reuse
> FIX-S1-002's walk-forward machinery). Specify the schema change to persist causal + smoothed labels
> separately, the leakage regression test, and the MODEL-004/006 re-run + diff plan. Do NOT edit.
> Return the plan, the recommended option with justification, and the full list of downstream
> consumers of `regime_smoothed`/`prob_*` that must switch to the causal column."

> **Copy-paste — Implementer (`general-purpose`):** *(paste the chosen design, then:)* "Implement the
> approved FIX-S1-005 plan above under repo global rules (`§1`). Emit a causal regime label, persist
> causal + smoothed separately, point attribution and the gatekeeper at the causal column, and add
> the 'future bars can't change a past label' regression test. Re-run MODEL-004 and MODEL-006
> LOG-ONLY and report OOS-uplift before/after and the per-regime attribution shift — do not hide a
> shrinking uplift, that is the leakage being removed. No promotion. Return: files changed, schema
> change, test output, both diffs, and the fix-file header + register update text."

---

### Phase D — FIX-S1-003: regimes do not discriminate (investigation → fix)

- **Severity:** P1, investigation-first. The map's central premise (specialization by regime) is
  currently inert; must be **measured on the causal labels from Phase C**, not the leaked ones.
- **Agents:** **Investigator** (`Explore`) for the discrimination study → **Plan** (`Plan`) to turn
  findings into a fix → Implementer (`general-purpose`) → Reviewer/Verifier. This one may legitimately
  end as "documented finding + targeted fix" rather than a big code change.
- **Skills:** `hmm-semantic-mapping.md`, `vetting-gate.md`.
- **Files in scope:** `src/system1/attribution/attribute.py` (regime tagging — entry-only vs
  over-trade-life), the regime model/labels, signal generation (regime-filtering), MODEL-004/005
  premise.
- **Result required:**
  1. **Quantified discrimination test** (on causal labels): per strategy, is win-rate-by-regime
     significantly non-uniform? Report the spread table (like §2 of the fix doc) recomputed post-S1-005.
  2. A decision on the candidate root causes: (a) entry-only tag vs multi-bar trades → test
     **dominant-regime-over-trade-life** tagging and re-measure; (b) strategies not regime-filtered →
     prototype regime-filtered attribution; (c) label relevance.
  3. A **standalone sanity check of strategy 10** (no look-ahead in the stochastic signal; realistic
     exits) before any live trust.
  4. Written conclusion in the fix file: is the regime dimension earning its place? If not, the
     explicit recommendation (filter at signal-gen, or treat v1 map as one regime-agnostic strategy
     knowingly).
  5. Register row → **Implemented** (or **Verified** if it lands as a documented finding + the
     dominant-regime tagging change).

> **Copy-paste — Investigator (`Explore`, very thorough):**
> "Investigate FIX-S1-003 (do regimes discriminate strategy performance?) in the Scalable_Brain repo,
> using the CAUSAL regime labels produced by FIX-S1-005 (not the smoothed ones). Read
> `docs/proposed-fixes/system-1/FIX-S1-003-regimes-do-not-discriminate.md`. Locate: (1) where regime
> is tagged per trade (`src/system1/attribution/attribute.py`) and whether it's entry-only or over
> the trade's life; (2) whether Layer-0/signal generation filters strategies by regime at all;
> (3) every place the win-rate-by-regime spread is computed. Recompute the per-strategy win-rate
> spread across regimes on causal labels and report whether any strategy's per-regime distribution is
> significantly non-uniform. Do NOT edit files. Return: the spread table, the answer to 'is the regime
> feature earning its place?', and the 2-3 highest-leverage code locations a fix would touch."

> **Copy-paste — Plan + Implementer:** *(after the Investigator returns, spawn `Plan` to design the
> chosen remedy — dominant-regime-over-life tagging and/or regime-filtered attribution — then a
> `general-purpose` Implementer under §1 rules. If the conclusion is 'regimes don't discriminate and a
> code fix is premature,' the deliverable is the written finding in the fix file + register bump to
> Verified, with the recommendation for the broader strategy roster.)*

---

### Phase E — FIX-S1-006: deployment gates `oos_uplift_ok` & `beats_incumbent` never reject

- **Severity:** P1. Additive fix, but depends on Phase C: `oos_uplift_ok` can only be armed once
  MODEL-006 actually surfaces an OOS uplift.
- **Agents:** Implementer (`general-purpose`) → Reviewer (`/code-review high`) → Verifier (`/verify`).
  No Plan agent — the fix is concrete in the doc.
- **Skills:** `vetting-gate.md`, `object-storage-protocol.md`.
- **Files in scope:** `src/system1/scheduler/orchestrator.py` (`deployment_gates`,
  `_default_pipeline`, `_incumbent`), `src/system1/serializer/serialize.py` (`metrics`),
  `src/system1/scheduler/tests/test_scheduler.py`, `src/system1/serializer/tests/test_serialize.py`.
- **Result required:**
  1. Thread MODEL-006's `oos_uplift` + `significant` into `_default_pipeline`'s return;
     `oos_uplift_ok` requires `uplift >= MIN_UPLIFT and significant`. When MODEL-006 is genuinely
     unavailable, **fail closed** (block promotion) or require an explicit `--allow-missing-uplift`
     override — never a silent `None ⇒ pass`.
  2. `serialize.publish` writes `metrics["regime_accuracy"]` (and other gate-relevant metrics) into
     `model_metadata.json`, so `_incumbent` can read it and `beats_incumbent` can actually compare.
     Reconcile the metric key on both producer and consumer sides.
  3. **Gate-can-reject unit tests:** a candidate with `oos_uplift < MIN_UPLIFT`/not-significant, and a
     candidate with `regime_accuracy < incumbent`, must return `passed = False`. These tests must
     **fail before the fix and pass after**.
  4. Integration: publish a bundle, confirm `model_metadata.json.metrics.regime_accuracy` is present
     and `_incumbent()` reads it back; run the orchestrator with a deliberately-worse candidate and
     confirm `outcome == "skipped_gates_failed"`.
  5. Document the fail-open-vs-fail-closed default for the *first-ever* comparison (no incumbent
     metric yet). Register row → **Implemented**.

> **Copy-paste — Implementer (`general-purpose`):**
> "Implement FIX-S1-006 in the Scalable_Brain repo. Read
> `docs/proposed-fixes/system-1/FIX-S1-006-deployment-gates-never-reject.md` and the `vetting-gate`
> skill. Two gates in `src/system1/scheduler/orchestrator.py:deployment_gates` can never reject:
> `oos_uplift_ok` is True whenever uplift is None (and `_default_pipeline` always sets
> `oos_uplift=None`), and `beats_incumbent` compares on `regime_accuracy`, which
> `src/system1/serializer/serialize.py` never writes into `model_metadata.json`. (1) Thread the
> gatekeeper's `oos_uplift`+`significant` into `_default_pipeline`; make `oos_uplift_ok` require
> `uplift >= MIN_UPLIFT and significant`, and FAIL CLOSED (or require `--allow-missing-uplift`) when
> the gatekeeper result is missing — no silent pass. (2) Have `serialize.publish` persist
> `metrics['regime_accuracy']` so `_incumbent` can read it and `beats_incumbent` can fire; reconcile
> the key on both sides. (3) Add unit tests that each gate returns `passed=False` for a worse/
> edge-less candidate (must fail before the fix, pass after) plus the integration test
> (`outcome == 'skipped_gates_failed'`). Document the first-comparison fail-open/closed default.
> Honor repo global rules (`§1`): `black`+`mypy`, full scheduler+serializer suites green, no
> promotion. Return: files changed, test output (before/after), and the fix-file header + register
> update text."

---

## 5. Orchestration loop (what the top-level session does)

For each phase A→E, in order:

1. **(If a Plan agent is listed)** spawn it; read its plan; resolve any open decision (default to the
   fix doc's recommended option). If a decision is genuinely the owner's call (e.g. S1-002 Option A vs
   B, or S1-004 keep-both vs collapse), surface it to the user before implementing.
2. **Spawn the Implementer** with the copy-paste prompt (plus the Plan output). Wait for: files
   changed, green tests, the log-only diff, and the register/header text.
3. **Run `/code-review high`** on the working diff. Feed any correctness findings back to the
   Implementer (continue the same agent via SendMessage — don't start cold).
4. **Run `/verify`** to confirm the re-run/test behaves as claimed.
5. **Apply the register + fix-file updates** (`Proposed → Implemented`; `Verified` after `/verify`).
6. **STOP for human sign-off before any promotion.** Promotion of a corrected bundle/map is always an
   explicit owner decision — no agent promotes.

**Parallelism:** Phases are serial because of the dependency graph, but within a phase the
Reviewer and Verifier run after the Implementer. The only safe parallel pair is **Phase D's
Investigator** running while Phase C's re-run completes — start it read-only, then design the fix on
the final causal-label numbers.

---

## 6. Done-definition for the whole batch

- [ ] FIX-S1-004 — weights sum to 1.0 per regime; post-condition guard live; `proposed_*` diff shows
      `Ranging` corrected; register **Verified**.
- [ ] FIX-S1-002 — trades tagged OOS; gate metrics on OOS-only; "overfit fails OOS" test green;
      qualifying-set shrink documented; register **Verified**.
- [ ] FIX-S1-005 — causal label emitted + persisted; leakage regression test green; OOS-uplift
      before/after reported; register **Verified**.
- [ ] FIX-S1-003 — discrimination measured on causal labels; conclusion + recommendation written;
      register **Verified**.
- [ ] FIX-S1-006 — both gates can reject (tests prove it); `regime_accuracy` persisted; register
      **Verified**.
- [ ] A single owner sign-off review of all five `proposed_*` artifacts before any re-promotion +
      MODEL-007 bundle to Computer 2.
```
