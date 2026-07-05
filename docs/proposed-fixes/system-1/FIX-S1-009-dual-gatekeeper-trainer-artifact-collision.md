# FIX-S1-009 — Two gatekeeper trainers write the same `champion_*` artifacts (contract collision) + legacy-trainer defects

**Severity:** P0 (an ungoverned, incompatible-contract, historically-leaky trainer can silently overwrite the live champion that Layer-4/System-1 inference depends on)
**Status:** IMPLEMENTED 2026-07-05 — all five fixes landed (1a quarantine, 2 shell script, 3 RandomForest, 4 dead pipelines, 5 atomic_promote write-guard). 143 tests green (130 system1 + 13 layer3_ml). Live champion bundle sha256 unchanged throughout. No git commit (log-only per §7 until sign-off).
**Author:** Claude (trainer-provenance audit, verified against source 2026-07-04)
**Scope (files):**
- `src/system1/gatekeeper/train.py` (canonical trainer)
- `src/system1/scheduler/orchestrator.py` (governed promote path)
- `src/layer3_ml/training/train_ml_gatekeeper.py` (legacy tournament trainer — already patched by FIX-S1-008)
- `src/layer3_ml/train_ml_gatekeeper.py` (legacy **root** 270-line dead pipeline)
- `src/layer3_ml/feature_alignment.py` (legacy inference aligner)
- `src/layer3_ml/__init__.py` (exports the dead root pipeline)
- `shell/retrain_tournament.sh` (stale/broken invocation of the legacy trainer)
- `models/` (shared, git-ignored artifact store)

**Relationship to other fixes:** This is the architectural umbrella over **FIX-S1-008**
(which patched leakage/gates/cleanup *inside* the legacy trainer). FIX-S1-008 hardened the
legacy trainer defensively; **FIX-S1-009 is about retiring/quarantining it so it can never
clobber the governed champion.** Also touches **FIX-S1-006** (the orchestrator promote gate)
and **FIX-S1-005** (causal regime labels the canonical trainer consumes).

---

## ENGINEER BRIEF (read this first)

### Your role
You are a **senior ML-platform engineer** owning **model-artifact governance**. Your mandate
is that **exactly one pipeline can write the live champion bundle, through one governed
promote path, with one manifest schema.** A change that makes the system *refuse* an
ungoverned write is a success even if it deletes working-looking code. Treat any path that
can overwrite `models/champion_*.pkl` outside the orchestrator as a production incident.

### Tools & environment
- **Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`, Python 3.12, venv at
  `/home/emmanuel/Documents/Scalable_Brain/.venv`.
- **DB:** PostgreSQL 16 + TimescaleDB on `localhost:5432`, `ForexBrainDB`, role `sa`; connect
  only via `src/common/db.py`. `fact_trade_outcomes` / `fact_signals` are **populated** on
  the live DB (≈2073 joined rows for the legacy query; the canonical trainer joins trades to
  causal regime probs) — you can run both trainers for real.
- **Canonical trainer:** `python -m src.system1.gatekeeper.train --dry-run`
  (writes `models/proposed_champion_*`, never the live champion).
- **Legacy trainer:** `python src/layer3_ml/training/train_ml_gatekeeper.py --dry-run --selection-mode fallback`.
- **Orchestrator (governed promote):** `python -m src.system1.scheduler.orchestrator`.
- **Tests:** `pytest src/system1/ -q` and `pytest src/layer3_ml/tests/ -q`.
- **Guardrails:** the `models/` store is **shared** — it also holds
  `models/hmm_model.joblib` (System-1 regime subsystem) and `models/archive/`. **Never
  delete `hmm_model.joblib`.** Preserve the champion manifest schema that live consumers read.

### Definition of done
1. Only `src/system1/gatekeeper/train.py` (via the orchestrator) can write `models/champion_*`.
2. The legacy trainer(s) **cannot** overwrite `champion_*` — either removed, or hard-guarded
   to write to a distinct `models/legacy_*` path and refuse `--promote-as-champion`.
3. `shell/retrain_tournament.sh` is deleted or rewritten to call the canonical trainer with
   correct paths.
4. The `randomforest` factory bug (below) is fixed **or** RandomForest is intentionally dropped.
5. Dead pipelines (`src/layer3_ml/train_ml_gatekeeper.py` root + `__init__` export) resolved.
6. A written finding in §6: which trainer is canonical, what was retired, and confirmation
   that no non-orchestrator path can write the champion.

---

## 1. Executive summary

Verified against source, there are **four** compounding problems:

1. **Champion-artifact collision (P0).** Two independent trainers write the **same**
   `models/champion_model.pkl` / `champion_preprocessor.pkl` / `champion_manifest.json` with
   **incompatible feature contracts**. The canonical System-1 trainer is governed by the
   orchestrator; the legacy `layer3_ml` trainer can overwrite the champion **outside all
   governance** (manual run or the stale shell script).
2. **The legacy trainer is the wrong/dangerous one to promote (P0).** It historically leaked
   (FIX-S1-008), and on real data — leak-free — it has **no edge** (0/N models pass the gates;
   PR-AUC ≈ chance). Promoting it would replace a leak-conscious, uplift-positive champion
   with a chance-level model *and* break the manifest/feature contract downstream consumers read.
3. **RandomForest never trains (P1).** A duplicate-kwarg bug silently drops 1 of 3 tournament
   models on every legacy run.
4. **Dead/stale scaffolding (P2).** Three divergent legacy pipelines, an `__init__` that
   exports the dead one, and a shell script pointing at a non-existent path on another machine.

---

## 2. Evidence (file:line, verified 2026-07-04)

### 2a. The two trainers and the collision

**Canonical — `src/system1/gatekeeper/train.py` (405 lines).** Orchestrated by
`src/system1/scheduler/orchestrator.py` ("MODEL-009 — triggers → gated pipeline → atomic
promote"). Trains on `fact_trade_outcomes` joined point-in-time to **causal** regime probs
(FIX-S1-005, walk-forward, forward-only labels). It selects only `is_winner` (label) and
`r_multiple` (**used for OOS-uplift evaluation, never as a feature**), so it has **none** of
the FIX-S1-008 outcome-column leakage. Writes (`train.py:300-341`):

```python
prefix = "proposed_champion" if dry_run else "champion"      # :301
model_path = os.path.join(MODELS_DIR, f"{prefix}_model.pkl")  # MODELS_DIR = <repo>/models  (:67)
joblib.dump(model, model_path)                                # -> models/champion_model.pkl
```
Manifest schema (`:311-341`): `{model_type, features:[atr_value, adx_value,
prob_causal_trending_up/down/ranging/high_vol, regime, strategy_id, entry_signal_type],
regime_features, dynamic_thresholds{per-regime}, turnover_band:[0.05,0.60], oos_uplift{...},
regime_model_version, feature_set_version, sha256}`. This is what produced the **live**
champion (`models/champion_manifest.json`: features are `prob_*`/`regime_smoothed`,
`oos_uplift.uplift = 0.031902`, significant).

**Legacy — `src/layer3_ml/training/train_ml_gatekeeper.py` (2053 lines).** Writes the **same
three paths**:
```python
MODELS_DIR = Path("models")                                   # :119
CHAMPION_MODEL_PATH        = MODELS_DIR / "champion_model.pkl"        # :120
CHAMPION_PREPROCESSOR_PATH = MODELS_DIR / "champion_preprocessor.pkl" # :121
CHAMPION_MANIFEST_PATH     = MODELS_DIR / "champion_manifest.json"    # :122
```
`promote_to_champion(...)` (gated by `--promote-as-champion`) archives then overwrites these.
Its feature set is `Strat_WinRate_*`, `Ind_RSI`, `ADX_Value`, … (see FIX-S1-008) — **a
completely different contract** from the System-1 champion. Its manifest schema also differs
(single `threshold`, per-model `metrics`, no `regime_features`/`dynamic_thresholds`/`oos_uplift`).

**Collision:** any of these writes `models/champion_*`:
- `python src/layer3_ml/training/train_ml_gatekeeper.py --selection-mode fallback --promote-as-champion --allow-degenerate-promotion`
- `bash shell/retrain_tournament.sh` (see 2d)

…overwriting the orchestrator-owned champion with an ungoverned, incompatible, historically-
leaky bundle. Downstream consumers that read `champion_manifest.json` expect the System-1
schema (`regime_features`, `dynamic_thresholds`, etc.) and will KeyError or silently
mispredict on the legacy manifest.

### 2b. Legacy trainer has no edge once leak-free (context, measured)

Real-data OOS on the legacy feature set (2073 rows, identical split, only leakage toggled —
see FIX-S1-008 §6d): leaked PR-AUC **1.0000** / +1.0R (perfect, fabricated); leak-free PR-AUC
**0.4958 ≈ base rate 0.4578 (chance)**, expectancy **negative**. A strict run therefore
correctly promotes nothing. **This trainer should not be a promotion source at all**, not
merely "gated."

### 2c. RandomForest never trains (duplicate kwarg)

`optuna_objective` suggests `min_samples_leaf` into `params` for randomforest:
```python
"min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 5),   # optuna_objective (rf branch)
```
…and `tree_model_factory` **also hardcodes** it:
```python
else:  # randomforest
    base_model = RandomForestClassifier(
        **params,                    # already contains min_samples_leaf
        random_state=SEED,
        class_weight="balanced_subsample",
        min_samples_split=5,
        min_samples_leaf=2,          # <-- duplicate -> TypeError at construction
    )
```
Result at runtime: `RandomForestClassifier() got multiple values for keyword argument
'min_samples_leaf'` → the `except Exception` in the tree loop swallows it and `continue`s, so
**RandomForest is silently absent from every tournament** (2 of 3 tree models actually run).

### 2d. Stale/broken shell script and dead pipelines

`shell/retrain_tournament.sh` is abandoned and points off-machine:
```bash
cd /home/eem/Documents/trading_system      # wrong user + wrong project dir (does not exist here)
source quant_env/bin/activate              # wrong venv
python src/layer3_ml/train_ml_gatekeeper.py   # the ROOT 270-line DEAD pipeline, not training/
# echoes: "Champion model saved to: models/best_ml_gatekeeper.pkl"
```
It invokes `src/layer3_ml/train_ml_gatekeeper.py` — the **root 270-line** file, which is the
third, dead feature pipeline (FIX-S1-008 §2c) exported by `src/layer3_ml/__init__.py:8`
(`comprehensive_feature_engineering`) but trained/served by nobody. The one real feature
pipeline is `src/system1/features/feature_pipeline.py` (the single-source contract FIX-S1-008
Fix 2 asked for **already exists in System-1**).

### 2e. `models/` is a shared, git-ignored store (do not "clean to one file")

`models/` holds artifacts from multiple System-1 components and is entirely git-ignored:
- `champion_model.pkl` / `champion_preprocessor.pkl` / `champion_manifest.json` — live gatekeeper (System-1).
- `hmm_model.joblib` — **System-1 regime subsystem** (`src/system1/regime/hmm_regime.py`, bundled by `src/system1/serializer/serialize.py`). **Must not be deleted.**
- `models/archive/` — where `archive_current_champion()` copies the prior champion on promote.
- (Cleaned 2026-07-04: removed old `ml_gatekeeper_run_*.json`, legacy `best_ml_gatekeeper_*`, `proposed_champion_*`.)

---

## 3. Root cause

Two eras coexist. The System-1 rebuild (`src/system1/*`) is the current, governed
architecture (single feature pipeline, causal labels, walk-forward, orchestrated promote with
a real OOS-uplift gate). The pre-rebuild `src/layer3_ml/*` monolith was never removed, still
hard-codes the **same** `models/champion_*` output paths, and can be run manually or via a
stale cron script — so a superseded, incompatible, historically-leaky trainer retains write
access to the single most safety-critical artifact in the system. Nothing enforces
"one writer, one contract, one promote path."

---

## 4. The fix (do in order)

### Fix 1 — Make the legacy trainer unable to overwrite the champion (P0)
Pick **one** (recommended: 1a):
- **1a (quarantine).** In `src/layer3_ml/training/train_ml_gatekeeper.py`, repoint the output
  constants to a distinct namespace so a legacy promote can never touch the governed bundle:
  ```python
  MODELS_DIR = Path("models")
  CHAMPION_MODEL_PATH        = MODELS_DIR / "legacy_gatekeeper_model.pkl"
  CHAMPION_PREPROCESSOR_PATH = MODELS_DIR / "legacy_gatekeeper_preprocessor.pkl"
  CHAMPION_MANIFEST_PATH     = MODELS_DIR / "legacy_gatekeeper_manifest.json"
  ```
  and hard-refuse promotion at the top of `main()` when `--promote-as-champion` is set
  (raise with "legacy trainer is retired; use the System-1 orchestrator").
- **1b (delete).** Remove `src/layer3_ml/training/train_ml_gatekeeper.py`, the root
  `src/layer3_ml/train_ml_gatekeeper.py`, `feature_alignment.py`, and the `__init__` exports,
  after confirming no non-test importers remain (`grep -rn "layer3_ml" src --include=*.py`).

### Fix 2 — Kill the stale shell script (P0, trivial)
Delete `shell/retrain_tournament.sh`, or replace its body with the governed entrypoint:
```bash
python -m src.system1.scheduler.orchestrator   # triggers → gated pipeline → atomic promote
```

### Fix 3 — Fix (or drop) RandomForest (P1)
In `tree_model_factory` remove the hardcoded `min_samples_leaf=2` from the RandomForest
branch (Optuna already tunes it); keep `min_samples_split=5` only if Optuna does **not** also
suggest it (it currently does not). If the legacy trainer is deleted (Fix 1b), this is moot.

### Fix 4 — Retire the dead pipelines / fix `__init__` (P2)
If not deleting in Fix 1b: reduce the root `src/layer3_ml/train_ml_gatekeeper.py` to a
re-export of the canonical `src/system1/features/feature_pipeline.py`, and fix
`src/layer3_ml/__init__.py:8` to stop exporting the dead builder.

### Fix 5 — Guard the write path structurally (P1, defense-in-depth)
Make `models/champion_*` writable only through the orchestrator's promote path (e.g. an
`atomic_promote()` helper in System-1 that stages to a temp file + `os.replace`, and is the
sole code that names `champion_*`). Any other module naming `champion_*` for writing is a
review red flag.

---

## 5. Validation
- **Collision closed:** after Fix 1, `grep -rn "champion_model.pkl" src --include=*.py` shows
  the string is *written* only by `src/system1/gatekeeper/train.py`. A legacy
  `--promote-as-champion` run either errors or writes `models/legacy_*` — assert
  `champion_manifest.json` mtime/sha is unchanged by it (add a test).
- **Canonical trainer still promotes:** `python -m src.system1.gatekeeper.train --dry-run`
  writes `models/proposed_champion_*` and leaves `champion_*` untouched; the orchestrator
  dry-run threads a real `oos_uplift`.
- **RandomForest:** legacy dry-run (if kept) shows `randomforest` completing (3 tree models),
  no `multiple values for keyword argument` in logs.
- **Shared store intact:** `models/hmm_model.joblib` present and untouched throughout.
- **No dead importers:** `pytest src/system1/ src/layer3_ml/tests/ -q` green.

## 6. Findings (implemented 2026-07-05)
- **Canonical trainer confirmed:** `src/system1/gatekeeper/train.py` (orchestrated by
  `src/system1/scheduler/orchestrator.py`). It is the only trainer that produces the live
  champion; a fresh leak-free dry-run threads a real, significant OOS uplift
  (**uplift=0.033034, p=5.0e-5, sig=True, approval=0.2835** over 134,520 trades).
- **Legacy action taken:** **quarantine (1a).** `src/layer3_ml/training/train_ml_gatekeeper.py`
  now writes only the `models/legacy_gatekeeper_*` namespace (constants + archive path +
  every dump/manifest write repointed) and hard-refuses `--promote-as-champion` via
  `SystemExit` at the top of `main()`, before any DB access, training, or file write. The
  dead root pipeline `src/layer3_ml/train_ml_gatekeeper.py` was reduced to a `raise
  ImportError` deprecation stub pointing at `src/system1/features/feature_pipeline.py`; its
  `__init__` export was removed. `feature_alignment.py` kept (still imported by live code).
  `shell/retrain_tournament.sh` rewritten to `python -m src.system1.scheduler.orchestrator`.
- **Non-orchestrator writers of `champion_*` after fix:** **none.** No file names a literal
  `champion_model.pkl` / `champion_preprocessor.pkl` / `champion_manifest.json` as a write
  target. All champion (and dry-run `proposed_champion_*`) writes go through the single
  governed helper `atomic_promote()` in `src/system1/gatekeeper/promote.py` (Fix 5), which
  stages to a temp file in-dir and `os.replace`s it (atomic on POSIX). Remaining literal
  `champion_*` references are **read-only** (reporting: `model_winner_impact_report.py`;
  mlflow artifact log; docstrings; tests).
- **RandomForest:** **fixed.** Removed the duplicate hardcoded `min_samples_leaf=2` from the
  `randomforest` branch of `tree_model_factory` (Optuna already tunes it); `min_samples_split=5`
  kept (Optuna does not suggest it). RF now constructs without the swallowed `TypeError`.
- **Live champion bundle unchanged by a legacy/dry-run attempt: YES.** sha256 of
  `champion_manifest.json` (`3f5f9b0d…`), `champion_model.pkl` (`2515db2b…`), and
  `champion_preprocessor.pkl` (`b1c881e8…`) identical before/after the canonical dry-run;
  the dry-run wrote only `models/proposed_champion_*`. `models/hmm_model.joblib` and
  `models/archive/` untouched. A quarantine unit test asserts a `--promote-as-champion`
  attempt leaves `champion_manifest.json` byte-identical.

## 7. Rollout
Log-only until sign-off. Because this changes who owns `models/champion_*`, land it as one
change set: (a) legacy write-path quarantined/removed, (b) shell script fixed, (c) tests
green, (d) a manual legacy `--promote-as-champion` attempt proven unable to alter the live
champion. Do **not** delete `models/hmm_model.joblib` or `models/archive/`. Coordinate with
**FIX-S1-008** (leak/gate patches already in the legacy trainer) and **FIX-S1-006** (the
orchestrator promote gate that remains the only promotion authority).
