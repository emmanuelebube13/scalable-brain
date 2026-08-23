"""MODEL-005 — strategy vetting + regime→strategy map / weights emitter.

Reads MODEL-004 attribution (latest qualification_run_id), applies the strict per-regime
gates, ranks qualifiers by composite score, and emits:
  * results/state/regime_strategy_map.json   (ranked qualifying strategies per regime)
  * results/state/strategy_weights.json      (per-regime weights, sum to 1)
  * results/reports/vetting_report_*.json     (gate pass/fail + rejection detail)
Both JSON artifacts validate against contracts/{regime-map,weights}-contract.json.

Log-only mode (VETTING_LOG_ONLY=true) writes to results/reports/proposed_* instead and
does not update the registry. Usage: python -m src.vetting.vet [--live]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text

from src.common.db import get_engine
from src.validation import walk_forward as WF
from src.vetting import gates as G

logger = logging.getLogger("system1.vetting")

SCHEMA_VERSION = "2.0.0"
REGIME_MODEL_VERSION = "hmm-v1.0.0"
REGIMES = ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]

#: FIX-S1-014 — strategies barred from qualification on **integrity** grounds,
#: regardless of their measured performance.
#:
#: This is deliberately separate from ``gates.py``. The gates encode *performance*
#: thresholds, and a strategy that fails them could pass later by improving. A
#: strategy listed here cannot: its recorded metrics are not a description of
#: anything it could actually have done. Folding the two together would imply the
#: rejection is a near miss. It is not.
#:
#: Checked BEFORE the gates, and never overridable by a metric.
INTEGRITY_DISQUALIFIED: Dict[int, str] = {
    10: (
        "look-ahead: divergence detection uses a centred rolling window "
        "(range_stochastic.py:245,248,281,284); emits zero signals when computed "
        "causally. See FIX-S1-014 and the 2026-08-02 audit."
    ),
}
# Human-designated cells: admitted into the live map despite failing one or more gates,
# because a person judged the evidence adequate and said so in writing. Keyed
# "{strategy_name}@{granularity}@{regime}" -> reason.
#
# This is NOT a way to lower the bar quietly. A designated cell is tagged
# ``selection_basis: "designated"`` and ships the exact gates it failed in
# ``gate_failures``, both of which System 3's ScoredSignal contract carries specifically so
# a designation is visible at the point of sizing rather than buried in a vetting report.
#
# Prefer this to editing GATES when the judgement is about ONE cell. Changing a threshold
# silently re-admits every other cell that happens to sit the right side of it.
DESIGNATED: Dict[str, Dict[str, Any]] = {
    # Human designations. Admitted into the live map despite failing gates, because the
    # owner judged the evidence adequate and said so on the record.
    #
    # Everything below is MEASURED, not asserted, from qualification run 77f83887 on
    # 2026-08-23. The contract requires it precisely so a designation cannot be a bare
    # opinion: ci_mean_r, max_pair_share, pairs_passed_fraction and tail_dependence all
    # ship with the signal so System 3 sizes against the real numbers.
    #
    # READ THE CONFIDENCE INTERVALS. Both straddle zero. System 1's analysis was that
    # neither cell is statistically distinguishable from no edge, and the owner overrode
    # that on 2026-08-23 to get the pipeline trading on a practice account. That
    # disagreement is recorded here rather than smoothed away, and it is visible
    # downstream in every signal these cells produce.
    "weekly_gap_fade@H1@High-Vol": {
        "by": "owner",
        "at": "2026-08-23T00:00:00Z",
        "reason": (
            "100 OOS trades over 18 OOS months, 52.0% win, R:R 1.20, MaxDD 2.1% — five "
            "times the sample of any qualified cell. Fails PF (1.30 < 1.50) and Recovery "
            "(1.65 < 3.00). Owner override: 95% CI on mean R is [-0.0344, +0.0993] and "
            "straddles zero, so this is not a demonstrated edge; designated to put a "
            "well-sampled cell through the live pipeline on practice capital. Tail "
            "dependence 3.77 — a single loss ~3.8x the mean absolute R."
        ),
        "oos_trade_count": 100,
        "ci_mean_r": [-0.0344, 0.0993],
        "pairs_passed_fraction": "3/5",
        "max_pair_share": 0.28,
        "tail_dependence": 3.7738,
    },
    "xard_ma_cross_daily_open@H1@Trending-Up": {
        "by": "owner",
        "at": "2026-08-23T00:00:00Z",
        "reason": (
            "224 OOS trades, PF 1.11, Sharpe 0.53, MaxDD 17.4%. Weaker than the High-Vol "
            "cell but added deliberately for coverage: 8 of 16 live regime-grid entries "
            "are Trending-Up against 1 in High-Vol, so this is the cell most likely to "
            "actually fire. 95% CI on mean R is [-0.1005, +0.2632] and straddles zero. "
            "Better diversified than either High-Vol designation — 4 of 5 pairs "
            "profitable and tail dependence 1.02 — but PF 1.11 is close enough to "
            "break-even that realistic spread costs may erase it; the backtest charges "
            "1.0 pip against a measured 1.8-2.9."
        ),
        "oos_trade_count": 224,
        "ci_mean_r": [-0.1005, 0.2632],
        "pairs_passed_fraction": "4/5",
        "max_pair_share": 0.2723,
        "tail_dependence": 1.0239,
    },
    "xard_ma_cross_daily_open@H1@High-Vol": {
        "by": "owner",
        "at": "2026-08-23T00:00:00Z",
        "reason": (
            "172 OOS trades, the largest clean sample in the platform. PF 1.25, Sharpe "
            "1.13, MaxDD 14.5%. Fails PF, Recovery and WinRate (39.5% vs 40%). Owner "
            "override: 95% CI on mean R is [-0.0555, +0.3736] and straddles zero."
        ),
        "oos_trade_count": 172,
        "ci_mean_r": [-0.0555, 0.3736],
        "pairs_passed_fraction": "3/5",
        "max_pair_share": 0.25,
        "tail_dependence": 0.7705,
    },
}

CAP = 100.0  # cap unbounded ratios (inf PF/recovery, huge Sharpe) for ranking/JSON
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_DIR = os.path.join(_REPO_ROOT, "results", "state")
REPORTS_DIR = os.path.join(_REPO_ROOT, "results", "reports")
CONTRACTS = os.path.join(_REPO_ROOT, "contracts")


def _cap(v: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return min(v, CAP) if v > 0 else max(v, -CAP)


def _load_cells() -> tuple[List[Dict], str]:
    engine = get_engine()
    with engine.connect() as conn:
        run_id = conn.execute(
            text(
                "SELECT qualification_run_id FROM fact_strategy_regime_attribution "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar()
        rows = (
            conn.execute(
                text(
                    "SELECT a.strategy_id, s.strategy_name, s.strategy_key, a.regime, a.granularity, a.trade_count, "
                    "a.win_rate, a.profit_factor, a.sharpe, a.max_drawdown, a.recovery_factor, "
                    "a.oos_months, a.low_confidence "
                    "FROM fact_strategy_regime_attribution a "
                    "JOIN dim_strategy s ON s.strategy_id = a.strategy_id "
                    "WHERE a.qualification_run_id = :rid"
                ),
                {"rid": run_id},
            )
            .mappings()
            .all()
        )
    cells = []
    for r in rows:
        cells.append(
            {
                "strategy_id": int(r["strategy_id"]),
                "strategy_key": str(r["strategy_key"] or r["strategy_name"]),
                "variant": f"{r['strategy_name']}@{r['granularity']}",
                "regime": r["regime"],
                "granularity": r["granularity"],
                "trade_count": int(r["trade_count"]),
                "win_rate": float(r["win_rate"]),
                "profit_factor": _cap(r["profit_factor"]),
                "sharpe": _cap(r["sharpe"]),
                "max_drawdown": float(r["max_drawdown"]),
                "recovery_factor": _cap(r["recovery_factor"]),
                "oos_months": float(r["oos_months"] or 0.0),
                "low_confidence": bool(r["low_confidence"]),
            }
        )
    return cells, str(run_id)


class WeightsNotNormalized(ValueError):
    """Raised by the build post-condition when a non-empty regime's weights do not
    sum to 1.0 (FIX-S1-004 guard). Failing the run is intentional: a collapsed/degenerate
    weight map (e.g. the shipped ``Ranging = {'10': 5e-08}``) must never be published.
    """


def _assert_weights_normalized(weights_out: Dict[str, Dict[str, float]]) -> None:
    """Hard post-condition: every NON-EMPTY regime's weights must sum to 1.0 (±1e-6).

    This guard CAN fire — it inspects already-computed weight dicts, so a bug upstream
    (a key collision, a dropped variant, a bad renormalization) that breaks the
    sum-to-1 invariant trips it and fails the run, rather than silently shipping a
    corrupt position-sizing artifact to Computer 2.
    """
    for regime, weights in weights_out.items():
        if not weights:
            continue
        total = sum(weights.values())
        if abs(total - 1.0) >= 1e-6:
            raise WeightsNotNormalized(
                f"Regime '{regime}' weights sum to {total!r}, not 1.0 "
                f"(keys={list(weights)}). Refusing to publish a degenerate weight map."
            )


def _metrics_block(c: Dict) -> Dict[str, float]:
    return {
        "profit_factor": round(c["profit_factor"], 4),
        "sharpe": round(c["sharpe"], 4),
        "win_rate": round(c["win_rate"], 4),
        "max_drawdown": round(c["max_drawdown"], 4),
        "recovery_factor": round(c["recovery_factor"], 4),
        "trade_count": c["trade_count"],
        "oos_months": round(c["oos_months"], 2),
    }


def _validation_design() -> Dict[str, Any]:
    """FIX-S1-002 walk-forward lineage block for the regime map (method + locked params).

    Records HOW the OOS numbers were earned so Computer 2 (MODEL-007 consumer) knows the
    ``oos_months`` gate now measures true out-of-sample coverage, not in-sample span.
    ``n_folds`` / ``anchor`` are per-granularity, derived from the live entry-time bounds.
    """
    design: Dict[str, Any] = {
        "method": "walk_forward",
        "min_train_months": WF.MIN_TRAIN_MONTHS,
        "step_months": WF.STEP_MONTHS,
        "oos_window_months": WF.OOS_WINDOW_MONTHS,
        "mode": WF.MODE,
        "anchor": "series_start = per-granularity min entry_time",
    }
    n_folds: Dict[str, int] = {}
    anchor: Dict[str, str] = {}
    try:
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    'SELECT granularity, MIN("timestamp") AS smin, MAX("timestamp") AS smax '
                    "FROM fact_trade_outcomes GROUP BY granularity"
                )
            ).all()
        for gran, smin, smax in rows:
            if smin is None or smax is None:
                continue
            folds = WF.default_folds(smin, smax)
            n_folds[str(gran)] = len(folds)
            anchor[str(gran)] = smin.isoformat()
    except (
        Exception
    ) as exc:  # noqa: BLE001 - lineage is best-effort, must not fail vetting
        logger.warning(
            "Could not derive per-granularity fold counts for lineage: %s", exc
        )
    design["n_folds"] = n_folds
    design["series_start"] = anchor
    return design


def build(
    cells: List[Dict],
    run_id: str,
    validation_design: Dict[str, Any] | None = None,
    disqualified: Dict[int, str] | None = None,
    live: bool = False,
) -> Dict[str, Any]:
    """Build the regime→strategy map from attribution cells.

    ``disqualified`` overrides :data:`INTEGRITY_DISQUALIFIED` (FIX-S1-014). It exists
    so a test about *weighting* can opt out of *integrity* policy explicitly, rather
    than silently depending on which strategy ids happen to be barred today. Pass
    ``{}`` to disable the bar. Production callers leave it as ``None``.
    """
    barred = INTEGRITY_DISQUALIFIED if disqualified is None else disqualified
    rejection = {
        k: 0
        for k in [
            "pf_fail",
            "sharpe_fail",
            "maxdd_fail",
            "winrate_fail",
            "recovery_fail",
            "oos_fail",
            "low_confidence_fail",
            "integrity_fail",
        ]
    }
    rejection_detail: List[Dict] = []
    by_regime: Dict[str, List[Dict]] = {r: [] for r in REGIMES}

    for c in cells:
        # FIX-S1-014: integrity disqualification precedes the performance gates.
        # A barred strategy is rejected on what it is, not on how it scored — its
        # recorded metrics describe a backtest it could not have traded.
        reason = barred.get(int(c["strategy_id"]))
        if reason is not None:
            rejection["integrity_fail"] += 1
            rejection_detail.append(
                {
                    "strategy_id": c["strategy_id"],
                    "variant": c["variant"],
                    "regime": c["regime"],
                    "failed_gates": ["INTEGRITY_DISQUALIFIED"],
                    "integrity_reason": reason,
                }
            )
            continue

        passed, failures = G.evaluate_gates(c)
        designation = DESIGNATED.get(f"{c['variant']}@{c['regime']}")
        if passed or designation:
            if c["regime"] != "UNKNOWN":
                c["selection_basis"] = "qualified" if passed else "designated"
                c["gate_failures"] = [] if passed else list(failures)
                c["designation"] = designation if not passed else None
                by_regime[c["regime"]].append(c)
            if not passed:
                # Still counted in the rejection profile: a designation is an override of
                # the gates, not a claim that they passed.
                logger.warning(
                    "DESIGNATED %s@%s despite %s", c["variant"], c["regime"], failures
                )
        else:
            for f in failures:
                if f == "LOW_CONFIDENCE":
                    rejection["low_confidence_fail"] += 1
                elif f.startswith("PF"):
                    rejection["pf_fail"] += 1
                elif f.startswith("Sharpe"):
                    rejection["sharpe_fail"] += 1
                elif f.startswith("MaxDD"):
                    rejection["maxdd_fail"] += 1
                elif f.startswith("WinRate"):
                    rejection["winrate_fail"] += 1
                elif f.startswith("Recovery"):
                    rejection["recovery_fail"] += 1
                elif f.startswith("OOS"):
                    rejection["oos_fail"] += 1
            rejection_detail.append(
                {
                    "strategy_id": c["strategy_id"],
                    "variant": c["variant"],
                    "regime": c["regime"],
                    "failed_gates": failures,
                }
            )

    regimes_out: Dict[str, List[Dict]] = {}
    weights_out: Dict[str, Dict[str, float]] = {}
    empty_regimes: List[str] = []
    for regime in REGIMES:
        ranked = G.rank_cells(by_regime[regime])
        if not ranked:
            empty_regimes.append(regime)
            logger.warning(
                "STARVATION: no qualifying strategies for regime '%s'", regime
            )
            continue
        regimes_out[regime] = [
            {
                "strategy_id": c["strategy_id"],
                "strategy_key": c["strategy_key"],
                "variant": c["variant"],
                "rank": c["rank"],
                "composite_score": round(c["composite_score"], 6),
                "selection_basis": c.get("selection_basis", "qualified"),
                "gate_failures": c.get("gate_failures", []),
                **(
                    {
                        "designated_by": c["designation"]["by"],
                        "designated_reason": c["designation"]["reason"],
                        "designated_at_utc": c["designation"]["at"],
                        "oos_trade_count": c["designation"]["oos_trade_count"],
                        "ci_mean_r": c["designation"]["ci_mean_r"],
                        "pairs_passed_fraction": c["designation"][
                            "pairs_passed_fraction"
                        ],
                        "max_pair_share": c["designation"]["max_pair_share"],
                        "tail_dependence": c["designation"]["tail_dependence"],
                    }
                    if c.get("designation")
                    else {}
                ),
                "direction": "both",
                "exits": {},
                "metrics": _metrics_block(c),
            }
            for c in ranked
        ]
        weights_out[regime] = {
            k: round(v, 8) for k, v in G.normalized_weights(ranked).items()
        }

    # FIX-S1-004 post-condition: fail the run before emitting if any non-empty regime's
    # weights don't sum to 1.0 (e.g. a duplicate-strategy key collision). Runs on the
    # rounded values that are actually written, so the published artifact is the one checked.
    _assert_weights_normalized(weights_out)

    now = datetime.now(timezone.utc).isoformat()
    regime_map = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now,
        "regime_model_version": REGIME_MODEL_VERSION,
        "qualification_run_id": run_id,
        # LIVE HAZARD, reported by System 2 on 2026-08-23. This was hardcoded "proposed"
        # even inside a model set whose manifest says "published". Their
        # ``parse_withdrawal`` treats any status outside {published, active} as a
        # WITHDRAWAL — so the moment anything downstream reads this field instead of the
        # manifest, it halts trading. Nothing reads it today; that is luck, not design.
        #
        # A log-only run is genuinely a proposal. A --live run is the live map and must say
        # so. The manifest remains authoritative either way.
        "status": "published" if live else "proposed",
        "ranking_rule": G.RANKING_RULE,
        "gates": G.GATES,
        "regimes": regimes_out,
        "empty_regimes": empty_regimes,
        "rejection_summary": rejection,
    }
    if validation_design is not None:
        regime_map["validation_design"] = validation_design
    weights = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now,
        "regime_model_version": REGIME_MODEL_VERSION,
        "qualification_run_id": run_id,
        "weights": weights_out,
    }
    return {"map": regime_map, "weights": weights, "rejection_detail": rejection_detail}


def _validate(artifact: Dict, contract_name: str) -> None:
    import jsonschema

    with open(os.path.join(CONTRACTS, contract_name), encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.validate(artifact, schema)


def _write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def _update_registry(regime_map: Dict) -> None:
    qualified_ids = {
        s["strategy_id"] for entries in regime_map["regimes"].values() for s in entries
    }
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE dim_strategy_registry ADD COLUMN IF NOT EXISTS is_qualified boolean"
            )
        )
        conn.execute(text("UPDATE dim_strategy_registry SET is_qualified = false"))
        if qualified_ids:
            conn.execute(
                text(
                    "UPDATE dim_strategy_registry SET is_qualified = true WHERE strategy_id = ANY(:ids)"
                ),
                {"ids": list(qualified_ids)},
            )
    logger.info("Registry: %d strategies marked qualified", len(qualified_ids))


def run(live: bool = False, register_mlflow: bool = True) -> Dict[str, Any]:
    cells, run_id = _load_cells()
    logger.info("Loaded %d attribution cells (run %s)", len(cells), run_id)
    out = build(cells, run_id, validation_design=_validation_design(), live=live)

    _validate(out["map"], "regime-map-contract.json")
    _validate(out["weights"], "weights-contract.json")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if live:
        _write_json(os.path.join(STATE_DIR, "regime_strategy_map.json"), out["map"])
        _write_json(os.path.join(STATE_DIR, "strategy_weights.json"), out["weights"])
        _update_registry(out["map"])
        map_path = os.path.join(STATE_DIR, "regime_strategy_map.json")
    else:
        _write_json(
            os.path.join(REPORTS_DIR, "proposed_regime_strategy_map.json"), out["map"]
        )
        _write_json(
            os.path.join(REPORTS_DIR, "proposed_strategy_weights.json"), out["weights"]
        )
        map_path = os.path.join(REPORTS_DIR, "proposed_regime_strategy_map.json")

    report = {
        "qualification_run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if live else "log_only",
        "n_cells": len(cells),
        "n_qualifying": sum(len(v) for v in out["map"]["regimes"].values()),
        "empty_regimes": out["map"]["empty_regimes"],
        "rejection_summary": out["map"]["rejection_summary"],
        "rejection_detail": out["rejection_detail"],
    }
    _write_json(os.path.join(REPORTS_DIR, f"vetting_report_{ts}.json"), report)

    summary = {
        k: report[k] for k in ("n_cells", "n_qualifying", "empty_regimes", "mode")
    }
    summary["map_path"] = map_path
    if register_mlflow:
        summary["mlflow_run_id"] = _register_mlflow(report)
    logger.info("MODEL-005 complete: %s", summary)
    return summary


def _register_mlflow(report) -> str:
    try:
        import mlflow
        from src.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-vetting")
        with mlflow.start_run(run_name="vetting") as run:
            mlflow.log_param("mode", report["mode"])
            mlflow.log_metric("n_cells", report["n_cells"])
            mlflow.log_metric("n_qualifying", report["n_qualifying"])
            for k, v in report["rejection_summary"].items():
                mlflow.log_metric(k, v)
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="MODEL-005 vetting + regime map")
    p.add_argument(
        "--live",
        action="store_true",
        help="write to results/state/ and update registry",
    )
    p.add_argument("--no-mlflow", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    live = args.live or os.environ.get("VETTING_LOG_ONLY", "true").lower() == "false"
    print(run(live=live, register_mlflow=not args.no_mlflow))


if __name__ == "__main__":
    main()
