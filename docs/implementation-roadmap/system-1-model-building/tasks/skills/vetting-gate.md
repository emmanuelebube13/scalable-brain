# Vetting Gate Specification

**Skill ID:** `vetting-gate`
**File:** `docs/implementation-roadmap/system-1-model-building/tasks/skills/vetting-gate.md`
**Applies To:** `attribution-vetting-agent` (MODEL-005).

---

## Gate Thresholds

All 6 gates must pass for a strategy×regime cell to qualify:

| # | Gate | Threshold | Direction | Formula |
|---|------|-----------|-----------|---------|
| 1 | Profit Factor | ≥ 1.5 | Higher is better | `gross_profit / gross_loss` |
| 2 | Sharpe Ratio | ≥ 0.8 | Higher is better | `mean(excess_returns) / std(excess_returns) * sqrt(252)` |
| 3 | Max Drawdown | ≤ 25% | Lower is better | `max(peak - trough) / peak` |
| 4 | Win Rate | ≥ 40% | Higher is better | `winning_trades / total_trades` |
| 5 | Recovery Factor | ≥ 3.0 | Higher is better | `net_profit / max_drawdown_absolute` |
| 6 | OOS Coverage | ≥ 60 months | Higher is better | Union span of walk-forward OOS fold windows |

---

## Sample Size Guard (Pre-Gate)

Before applying the 6 gates, check the `N_min` threshold:

```python
N_MIN = 20  # Configurable

def can_qualify(attribution_row):
    if attribution_row["trade_count"] < N_MIN:
        return False, "LOW_CONFIDENCE"
    return True, None
```

`low_confidence=true` cells are **always rejected** regardless of metric values.

---

## Gate Evaluation Function

```python
def evaluate_gates(cell):
    """
    cell: dict with keys matching gate names.
    Returns: (passed: bool, failures: list[str])
    """
    failures = []

    # Pre-gate: sample size
    if cell.get("low_confidence", False):
        return False, ["LOW_CONFIDENCE"]

    # Gate 1: Profit Factor
    if cell["profit_factor"] < 1.5:
        failures.append(f"PF={cell['profit_factor']:.2f} < 1.50")

    # Gate 2: Sharpe
    if cell["sharpe"] < 0.8:
        failures.append(f"Sharpe={cell['sharpe']:.2f} < 0.80")

    # Gate 3: Max Drawdown
    if cell["max_drawdown"] > 0.25:
        failures.append(f"MaxDD={cell['max_drawdown']:.1%} > 25%")

    # Gate 4: Win Rate
    if cell["win_rate"] < 0.40:
        failures.append(f"WinRate={cell['win_rate']:.1%} < 40%")

    # Gate 5: Recovery Factor
    if cell["recovery_factor"] < 3.0:
        failures.append(f"Recovery={cell['recovery_factor']:.2f} < 3.00")

    # Gate 6: OOS Coverage
    if cell.get("oos_months", 0) < 60:
        failures.append(f"OOS={cell['oos_months']}mo < 60mo")

    return len(failures) == 0, failures
```

---

## Boundary Tests

Every gate must accept at the threshold and reject just outside:

```python
def test_boundary_acceptance():
    """Gate accepts at threshold."""
    cell = make_cell(pf=1.50, sharpe=0.80, maxdd=0.25, winrate=0.40, recovery=3.0, oos=60)
    passed, _ = evaluate_gates(cell)
    assert passed  # All at threshold → should pass

def test_boundary_rejection():
    """Gate rejects just outside threshold."""
    cell = make_cell(pf=1.49, sharpe=0.79, maxdd=0.26, winrate=0.39, recovery=2.99, oos=59)
    passed, failures = evaluate_gates(cell)
    assert not passed
    assert len(failures) == 6  # All gates should fail

def test_low_confidence_always_rejected():
    """Even with perfect metrics, low-confidence cells are rejected."""
    cell = make_cell(pf=3.0, sharpe=2.0, maxdd=0.05, winrate=0.80, recovery=10.0, oos=120,
                     low_confidence=True, trade_count=10)
    passed, failures = evaluate_gates(cell)
    assert not passed
    assert "LOW_CONFIDENCE" in failures
```

---

## Artifact Schema Validation

### `regime_strategy_map.json` Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["schema_version", "generated_at_utc", "regime_model_version", "qualification_run_id", "ranking_rule", "gates", "regimes", "empty_regimes", "rejection_summary"],
  "properties": {
    "schema_version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
    "regimes": {
      "type": "object",
      "patternProperties": {
        "^(Trending-Up|Trending-Down|Ranging|High-Vol)$": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["strategy_id", "variant", "rank", "metrics"],
            "properties": {
              "rank": {"type": "integer", "minimum": 1},
              "metrics": {
                "type": "object",
                "required": ["profit_factor", "sharpe", "win_rate", "max_drawdown", "recovery_factor", "trade_count", "oos_months"]
              }
            }
          }
        }
      }
    },
    "empty_regimes": {
      "type": "array",
      "items": {"type": "string"}
    },
    "rejection_summary": {
      "type": "object",
      "properties": {
        "pf_fail": {"type": "integer"},
        "sharpe_fail": {"type": "integer"},
        "maxdd_fail": {"type": "integer"},
        "winrate_fail": {"type": "integer"},
        "recovery_fail": {"type": "integer"},
        "oos_fail": {"type": "integer"},
        "low_confidence_fail": {"type": "integer"}
      }
    }
  }
}
```

### `strategy_weights.json` Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["schema_version", "generated_at_utc", "regime_model_version", "qualification_run_id", "weights"],
  "properties": {
    "weights": {
      "type": "object",
      "patternProperties": {
        "^(Trending-Up|Trending-Down|Ranging|High-Vol)$": {
          "type": "object",
          "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    }
  }
}
```

---

## Schema Validation Code

```python
import jsonschema

def validate_regime_map(artifact_path, schema_path):
    with open(artifact_path) as f:
        artifact = json.load(f)
    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.validate(artifact, schema)

    # Additional semantic checks beyond schema
    for regime, strategies in artifact["regimes"].items():
        # Ranks are dense
        ranks = [s["rank"] for s in strategies]
        assert ranks == list(range(1, len(ranks) + 1)), f"Ranks not dense for {regime}"

        # Only qualifying strategies appear (should have been filtered by gates)
        for strategy in strategies:
            passed, _ = evaluate_gates(strategy["metrics"])
            assert passed, f"Non-qualifying strategy in map: {strategy['strategy_id']} in {regime}"

    # Empty regimes listed
    for regime in ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]:
        if regime not in artifact["regimes"] or len(artifact["regimes"][regime]) == 0:
            assert regime in artifact["empty_regimes"], f"Empty regime {regime} not listed"

def validate_strategy_weights(artifact_path, schema_path):
    with open(artifact_path) as f:
        artifact = json.load(f)
    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.validate(artifact, schema)

    for regime, weights in artifact["weights"].items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"Weights for {regime} sum to {total}, not 1.0"
```

---

## Starvation Guard

If any regime has zero qualifying strategies, the behavior is:

1. The regime appears in `empty_regimes` with a warning.
2. The `rejection_summary` shows why all strategies were rejected for that regime.
3. The warning is logged at WARNING level.
4. `serializer-infra-agent` (MODEL-007) may refuse to publish a bundle with an empty regime (guard), or it may proceed with a warning — **this is a configurable policy**.
5. The downstream (Computer 2) must handle missing regimes gracefully (fallback strategy or sit out).

```python
def check_starvation(regime_map):
    empty = []
    for regime in ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]:
        strategies = regime_map["regimes"].get(regime, [])
        if len(strategies) == 0:
            empty.append(regime)
            logger.warning(f"STARVATION: No qualifying strategies for regime '{regime}'")

    return empty
```

---

## Log-Only Mode

Before making MODEL-005 live (changing actual promotion behavior), run in log-only mode:

```python
LOG_ONLY_MODE = os.environ.get("VETTING_LOG_ONLY", "true").lower() == "true"

if LOG_ONLY_MODE:
    logger.info("Running in LOG-ONLY mode. Computing would-be artifacts but not promoting.")
    # Compute pass/fail and would-be artifacts
    would_be_map = build_regime_map(cells)
    would_be_weights = build_weights(cells)

    # Log results
    logger.info(f"Would-be qualified strategies: {count_qualified(would_be_map)}")
    logger.info(f"Would-be rejection counts: {summary}")
    logger.info(f"Would-be empty regimes: {check_starvation(would_be_map)}")

    # Write artifacts to a "proposed" directory, not results/state/
    write_artifact(would_be_map, "results/reports/proposed_regime_strategy_map.json")
    write_artifact(would_be_weights, "results/reports/proposed_strategy_weights.json")
    return

# Live mode: compute and promote
# ...
```

**Never go live with MODEL-005 without first reviewing log-only output against historical data.**

---

## Rejection Reason Reporting

Every strategy×regime cell that fails should have documented reasons:

```python
rejection_detail = {
    "strategy_id": "...",
    "variant": "...",
    "regime": "Ranging",
    "failed_gates": ["PF=1.32 < 1.50", "Sharpe=0.55 < 0.80"],
    "metrics": {...}
}
```

This is written to `results/reports/vetting_rejection_detail_{timestamp}.json` and included in the MLflow run. It provides the audit trail for tuning gate thresholds.

---

## Backward Compatibility

The existing aggregate vetting in `src/layer0/qualify_strategies.py` (positive expectancy, ≥20 trades, ~1.15 profit factor) must continue to run unchanged:

```python
# Existing aggregate vetting (unchanged)
aggregate_results = run_aggregate_vetting(backtest_trades)

# New per-regime vetting (additive)
per_regime_results = run_per_regime_vetting(backtest_trades, regime_labels)

# Both results emitted
write_qualification_report(aggregate_results, per_regime_results)
```
