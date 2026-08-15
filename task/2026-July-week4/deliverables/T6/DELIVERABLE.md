# T6 — Research Strategy Engine · Technical Report

**Date:** 2026-07-29 · **Status:** COMPLETE (skeleton + pilot) · **Commits:** `2f5b5b5`, `<deliverables>`

Design doc: `docs/design/RESEARCH_STRATEGY_ENGINE.md` (includes the strategy author's guide).

---

## 1. The contract — `src/layer0/strategies/contract.py`

```python
class Strategy(ABC):
    metadata: StrategyMetadata          # id, name, version, author, hypothesis, granularities, pairs
    required_indicators: List[str]
    warmup_bars: int = 200
    def generate_signals(self, df) -> pd.Series:   # +1 / -1 / 0, indexed like df
```

Deliberately **smaller** than the legacy `StrategyBase`. The contract is the *promotion*
surface; `StrategyBase` is the *execution* surface. `engine_adapter.py` bridges them and
imposes **uniform ATR stops** (1×ATR SL, 3×ATR TP, ATR-14) on every research strategy, so no
candidate can flatter itself with bespoke exit logic. A research author writes ~30 lines and
structurally cannot reach execution concerns.

`StrategyMetadata` **requires a ≥8-word hypothesis** (`ValueError` otherwise). A strategy whose
edge nobody can articulate is a curve fit waiting to be discovered; forcing the claim up front
is what lets a later reviewer check whether it held.

## 2. Registry — `registry.py`

Two guarantees, both in code:

**Stage is derived from directory, never self-declared.** `metadata.stage` is overridden with
the package the class was found in. Proof — `test_stage_is_derived_from_location_not_self_declared`
registers a class that claims `Stage.QUALIFIED` while living in `research/`:

```
assert reg.get("liar").stage is Stage.RESEARCH
assert reg.qualified() == []
```

**Duplicate `strategy_id` is a hard error.** FIX-S1-004 was a silent weight collapse caused by
two entries sharing an id. The registry raises rather than picking a winner:

```
DuplicateStrategyId: strategy_id 'attack_strategy' declared twice:
  mod_a.A (research) and mod_b.B (staged). Ids must be unique across ALL stages —
  a duplicate silently collapsed strategy weights in FIX-S1-004.
```

Detection spans stages (`test_duplicate_detection_spans_stages`), not just siblings.

## 3. Promotion CLI — real transcripts

```
$ python -m src.layer0.strategies.promote --list
stage      strategy_id                     version   name
research   rsi_mean_reversion              0.1.0     RSI Mean Reversion

1 strategies. Only 0 qualified (the live path sees these and nothing else).
```

### research → staged (passed)

```
$ python -m src.layer0.strategies.promote rsi_mean_reversion --to staged
{
  "strategy_id": "rsi_mean_reversion",
  "from_stage": "research",
  "to_stage": "staged",
  "decided_at_utc": "2026-07-29T22:48:41Z",
  "passed": true,
  "outcome": "PROMOTED"
}
report: results/research/rsi_mean_reversion/promoted_to_staged_20260729T224841Z.json
```

The file moved `research/ → staged/` and the registry followed:

```
$ python -m src.layer0.strategies.promote --list
staged     rsi_mean_reversion              0.1.0     RSI Mean Reversion
```

### staged → qualified (REFUSED — the pilot's real verdict)

```
$ python -m src.layer0.strategies.promote rsi_mean_reversion --to qualified
REFUSED: rsi_mean_reversion refused promotion to qualified:
  PF=0.95 < 1.50
  Sharpe=-0.90 < 0.80
  MaxDD=99.7% > 25%
  WinRate=27.7% < 40%
  Recovery=-1.00 < 3.00
report: results/research/rsi_mean_reversion/qualification_refused_20260729T225257Z.json
EXIT=2
```

**The file stayed in `staged/`; `qualified/` is still empty.** Per T6, "a gate REJECTION with
a clear per-gate explanation is a fully successful pilot" — the machinery is demonstrated
end-to-end, and the honest answer about this particular idea is *no*.

Evidence behind the verdict: **9,806 OOS trades across 56 fold-instances, 89.42 months of OOS
coverage.** Per-fold results in `pilot_folds.png` — 5 of 14 folds positive, none reaching the
40% win-rate gate. This is a strategy that trades a lot and loses slowly, which is exactly the
profile the gates exist to reject.

## 4. Adversarial review — four attacks, each blocked by code

`src/layer0/strategies/tests/test_no_side_door.py`, 14 tests.

| # | Attack | Blocked by | Evidence |
|---|---|---|---|
| 1 | Promote research → qualified, skipping the gates | `promote.py:_NEXT_STAGE` + the stage check in `promote()` | `PromotionRefused: … the only legal next stage is staged, not qualified. Stages cannot be skipped` |
| 2 | Two strategies with the same `strategy_id` | `registry.py:StrategyRegistry.refresh` | `DuplicateStrategyId` raised; detection spans all stages |
| 3a | Look-ahead via `shift(-1)` | `contract.py:assert_no_lookahead` | `LookAheadError: … signal(s) changed when future bars were removed` |
| 3b | Look-ahead via whole-series normalisation | same | caught — no future value is referenced directly, yet early bars still depend on the series end |
| 4 | Research code writing to `fact_*` | `research_data.py` has no write path | source-level assertion: no `INSERT/UPDATE/DELETE/DROP/CREATE/ALTER`, no `.begin()`, no `to_sql` |

Two further structural tests:

- `test_qualification_imports_the_live_gates_rather_than_copying_thresholds` — asserts
  `from src.system1.vetting.gates import` is present **and** that no live threshold literal
  (`1.5`, `0.8`, `0.25`, `0.40`, `3.0`, `60`) appears in `promote.py`. A second copy of the
  thresholds would be a second qualification path waiting to drift.
- `test_live_vetting_path_sees_only_qualified` — with strategies planted in all three stages,
  `registry.qualified()` returns only the qualified one.

**All 14 pass.** Full repo suite: **270 passed**.

## 5. Two implementation corrections worth recording

**The first `_aggregate_cell` reimplemented the metrics and got drawdown wrong** — it divided
by a near-zero early peak and reported **MaxDD 1650%**. Fixed by importing
`src.system1.attribution.metrics` and using the live `max_drawdown`, `profit_factor`,
`annualized_sharpe`, `recovery_factor`, `win_rate` — the same principle as importing the
thresholds. The live `max_drawdown` compounds a fixed-fractional equity curve from 1.0 and is
bounded in [0,1) by construction. The corrected value is **99.7%**.

The sandbox also runs the live sanity bounds (`metrics.validate_metrics`, FIX-S1-001); any
violation forces `low_confidence`, which the gates treat as unconditional rejection.

**`_git_mv` could not promote an untracked strategy.** `git mv` refuses untracked sources, but
a freshly-authored research idea is *normally* untracked — the common case, not an error. It
now detects tracking state and falls back to a filesystem move plus `git add`.

## 6. `strategieStaged/` was deliberately NOT migrated

T6 step 3 says to migrate `strategieStaged` content into `staged/`. **I did not do that, and
doing it would have been wrong.**

Those 6 strategies implement `StrategyBase`, not the contract, and they are the
*currently live qualified set* — consumed via the `layer0.strategies` re-exports that
`qualify_strategies.py` depends on, which is precisely the import chain T1 repaired earlier
this week. Moving them into `staged/` would have demoted the live model and re-broken that
chain.

The correct next increment is a `LegacyStrategyAdapter` wrapping a `StrategyBase` as a
contract `Strategy`, letting them be registered as `qualified` **in place**.

## 7. Validation

| Check | Result |
|---|---|
| `pytest src/layer0/strategies -v` | 14 passed |
| `pytest src/system1 src/layer0 src/common -q` | **270 passed** |
| `mypy` on the four new modules | **Success: no issues found in 4 source files** |
| `python -m src.layer0.strategies.promote --list` | registry lists stage + id + version |
| Live pipeline sees only `qualified/` | demonstrated by test, not asserted |

*mypy note:* the 15 errors under a full `mypy src/layer0/strategies` are all **pre-existing**
in the legacy `strategieStaged/` files (untyped pandas, implicit `Optional`). The new modules
are clean.

## 8. What remains for the full engine

1. **`LegacyStrategyAdapter`** so the 6 existing strategies register as `qualified` in place
   (§6) — the highest-value next step, since it makes the registry the true single source.
2. **Parameter sweeps** inside the sandbox; today one fixed parameter set per strategy.
3. **Regime-conditional evaluation.** Gates currently run on pooled OOS trades. Wiring the
   sandbox into MODEL-004 attribution would let it answer finding B (*do regimes actually
   discriminate?*) for each new candidate — which is the question the live map cannot answer.
4. **Registry persistence** so promotion history is queryable without reading git log.

## 9. Why this matters right now

T5 established that the live account has taken **10 trades, all losers** (profit factor 0.0).
System 1's own findings say the live model is one strategy and the regime map doesn't
discriminate. The shortage is *honest candidates*, and until today there was no way to
generate one without hand-wiring it into the live qualification path.

The pilot is the proof: an idea went in, got 9,806 OOS trades of evidence, and came out with a
**documented refusal** rather than a seat in the live model. That is the machine working.
