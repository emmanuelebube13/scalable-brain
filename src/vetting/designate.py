"""Human designation: admit a strategy into one regime despite gate failures.

Designation is an OVERRIDE, not an approval. It admits a strategy that failed the
performance gates because a human judged the evidence adequate and said so on the record.
It is NOT a way to lower the bar quietly.

Changes from the previous version
----------------------------------
D1  The ``status`` field is NOT written here. It is set by ``vet.py --live``.
    Designation against a map whose status is not in {published, active} exits non-zero.
    Designation is not an approval mechanism.
D2  Weights are rewritten ONLY for the regime being designated, using
    ``gates.normalized_weights`` rather than an inline equal-weight rule.
    Regimes that were not designated retain their ``vet.py``-derived weights.
D3  Weight keys use ``gates._variant_key`` (strategy@granularity), not bare strategy_id,
    preventing the FIX-S1-004 key collision. Tolerance widened to 1e-4.
D4  ``--regime`` is required. A designation lands in exactly one regime; the metrics it
    records are for that regime's cell, not pooled across all regimes.
D5  The weights document always carries all four regime keys after writing, with {} for
    empty ones, so a consumer can distinguish "no allocation" from "key missing".
D6  Both artifacts are validated against their JSON-schema contracts before writing.
    A ``designation_log`` array is appended to the map so every mutation has a record.
D9  Raise if the strategy's OOS trades span more than one granularity; require
    ``--granularity`` to resolve the ambiguity.
D10 If the strategy passes all gates, print that and exit without writing.
    A qualifying strategy enters the map through ``vet.py``, not here.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.registry import catalog
from src.vetting.vet import (
    INTEGRITY_DISQUALIFIED,
    STATE_DIR,
    REPORTS_DIR,
    REGIMES,
    _cap,
    _validate,
)
from src.vetting import gates as G
from src.vetting import map_contract as MC
from src.attribution import attribute as attr


_VALID_MAP_STATUSES = {"published", "active"}


def main() -> None:
    p = argparse.ArgumentParser(
        description="Designate a strategy into a single regime of the live map."
    )
    p.add_argument("--strategy", required=True, help="strategy_key")
    p.add_argument("--regime", required=True, choices=REGIMES, help="target regime")
    p.add_argument("--reason", required=True, help="human-readable justification")
    p.add_argument("--by", required=True, help="designating party (owner / analyst)")
    p.add_argument("--granularity", default=None, help="e.g. H1, H4, D1")
    p.add_argument("--direction", default="both")
    p.add_argument("--exits", default="{}")
    # D2 — the declared weight for this override. Defaults to the same floor the softmax
    # guarantees a merit qualifier (gates.MIN_WEIGHT), so the default is conservative and
    # stated rather than inherited from whatever other cells happen to score.
    p.add_argument(
        "--weight",
        type=float,
        default=G.MIN_WEIGHT,
        help=(
            "explicit capital weight for this designated cell within its regime "
            f"(default {G.MIN_WEIGHT}); merit-qualified cells share the remainder"
        ),
    )
    p.add_argument(
        "--engine",
        default=attr.POOLED,
        choices=[*attr.VALID_ENGINES, attr.POOLED],
        help=(
            "simulation engine whose trades form the evidence. Pooling the two is "
            "explicitly not qualification-grade — see the warning this prints."
        ),
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not 0.0 < args.weight <= 1.0:
        print(f"ERROR: --weight must be in (0, 1]; got {args.weight}.")
        sys.exit(1)

    try:
        record = catalog.by_key(args.strategy)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    sid = record.strategy_id

    # D1 — integrity gate is still first.
    if sid in INTEGRITY_DISQUALIFIED:
        print(
            f"ERROR: Strategy {sid} ({args.strategy}) is INTEGRITY_DISQUALIFIED.\n"
            f"Reason: {INTEGRITY_DISQUALIFIED[sid]}"
        )
        sys.exit(1)

    engine = get_engine()
    # Engine population. `_load_trades` deliberately has no default because
    # `fact_trade_outcomes` holds two engines whose `r_multiple` does not mean the same
    # thing (v2 moves stops and scales out; v1 does neither), and its docstring is explicit
    # that POOLED is "valid for a descriptive report, not for qualifying a strategy".
    #
    # Designation is NOT a descriptive report — it writes the live map and its metrics
    # ship to System 3 as sizing inputs. Pooling was hardcoded here with the comment
    # "whichever engine produced it", which quietly accepted a weighted average of two
    # incomparable populations as the evidence for a live-trading override. The choice is
    # now the operator's and is stated on every run; POOLED remains the default only so
    # this fix changes no existing number without a decision, and it warns loudly.
    if args.engine == attr.POOLED:
        print(
            "WARNING: metrics below are POOLED across backtest_engine_v1 and "
            "position_engine_v2, whose r_multiple are not comparable. Per "
            "attribute._load_trades this is valid for a descriptive report, NOT for "
            "qualifying a strategy — and a designation writes the live map. Pass "
            f"--engine with one of {list(attr.VALID_ENGINES)} for a qualification-grade "
            "number. Tracked as register item E2."
        )
    trades = attr._load_trades(engine, args.engine)
    strat_oos = trades[(trades["strategy_id"] == sid) & (trades["is_oos"] == True)]

    if len(strat_oos) == 0:
        print(f"ERROR: Strategy {sid} has 0 OOS trades.")
        sys.exit(1)

    # D9 — raise if more than one granularity is present without an explicit --granularity.
    grans = strat_oos["granularity"].unique()
    if args.granularity is not None:
        if args.granularity not in grans:
            print(
                f"ERROR: --granularity {args.granularity!r} has no OOS trades for "
                f"{args.strategy}. Available: {sorted(grans)}"
            )
            sys.exit(1)
        gran = args.granularity
        strat_oos = strat_oos[strat_oos["granularity"] == gran]
    elif len(grans) > 1:
        print(
            f"ERROR: Strategy {args.strategy} has OOS trades at multiple granularities: "
            f"{sorted(grans)}. Pass --granularity to resolve."
        )
        sys.exit(1)
    else:
        gran = str(grans[0])

    folds_by_gran = attr._folds_by_granularity(strat_oos)
    folds = folds_by_gran.get(str(gran), {})

    # D4 — compute metrics for the target regime's cell, not pooled.
    tagged_all = attr.tag_regime_at_entry(trades, engine)
    regime_cell = tagged_all[
        (tagged_all["strategy_id"] == sid)
        & (tagged_all["granularity"] == gran)
        & (tagged_all["regime"] == args.regime)
        & (tagged_all["is_oos"] == True)
    ]
    if len(regime_cell) == 0:
        # Fail closed. The obvious alternative — fall back to the strategy's pooled OOS
        # metrics and print a warning — reintroduces D4 in the exact shape D4 describes:
        # an entry sitting in one named regime, carrying performance measured across all
        # regimes, indistinguishable downstream from a regime-conditioned permission. A
        # warning on stdout is not a control on a path that writes the live map.
        #
        # No OOS trades in this cell means there is no evidence for a regime-conditioned
        # designation, which is a reason to refuse, not a reason to substitute other
        # evidence. Missing ⇒ REJECT is the house rule.
        print(
            f"ERROR: {args.strategy}@{gran} has no OOS trades tagged {args.regime}, so "
            "there is no regime-conditioned evidence to designate on. Refusing.\n"
            "  If the regime label coverage is stale, fix that first (register L1/S3) — "
            "attribution currently sees roughly 40% of H1 bars.\n"
            "  If the strategy genuinely never traded this regime, it does not belong in "
            "this regime's map cell."
        )
        sys.exit(1)

    m = attr._oos_cell_metrics(regime_cell, folds)

    passed, failures = G.evaluate_gates(m)

    print(f"Strategy {args.strategy}@{gran} in {args.regime} — gate evaluation:")
    print(f"  Passed: {passed}")
    print(f"  Failures: {failures}")

    # D10 — a qualifying strategy enters the map through vet.py, not here.
    if passed:
        print(
            f"Strategy {args.strategy}@{gran} passes all gates in {args.regime}. "
            "It qualifies on merit and will appear in the map on the next vetting run. "
            "Designation is not required. Exiting without writing."
        )
        sys.exit(0)

    # D4 — the SIZING fields are conditioned on the same cell as `metrics`.
    #
    # These were computed on the strategy's pooled OOS trades while `metrics` was
    # conditioned on the regime cell, so one entry mixed two populations: `metrics`
    # described High-Vol while `ci_mean_r`, `max_pair_share` and `tail_dependence`
    # described every regime at once. `ci_mean_r` and `tail_dependence` ship to System 3
    # as position-sizing inputs, so a half-conditioned entry is not a cosmetic problem —
    # the consumer cannot see which half it is reading.
    r_multiples = regime_cell["r_multiple"].to_numpy(dtype=float)
    np.random.seed(42)
    means = [
        np.mean(np.random.choice(r_multiples, size=len(r_multiples), replace=True))
        for _ in range(1000)
    ]
    ci_mean_r = [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]
    max_pair_share = float(
        regime_cell["asset_id"].value_counts().max() / len(regime_cell)
    )

    # D8 — pairs_passed_fraction: count attribution cells (strategy×regime) passing gates.
    # Name is kept for wire compatibility; the description is "cells_passed / total_cells".
    # TODO D8: when the intended per-pair measure is implemented, update both name and value.
    with engine.connect() as conn:
        run_id = conn.execute(
            text(
                "SELECT qualification_run_id FROM fact_strategy_regime_attribution "
                "ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar()
        cells = (
            conn.execute(
                text(
                    "SELECT * FROM fact_strategy_regime_attribution "
                    "WHERE strategy_id = :sid AND qualification_run_id = :rid"
                ),
                {"sid": sid, "rid": run_id},
            )
            .mappings()
            .all()
        )
    passed_cells = sum(
        1
        for c in cells
        if G.evaluate_gates(
            {
                **dict(c),
                "oos_months": dict(c).get("oos_months") or 0.0,
                "low_confidence": dict(c).get("low_confidence") or False,
            }
        )[0]
    )
    pairs_passed_fraction = f"{passed_cells}/{len(cells)}" if cells else "0/0"

    # D7 — tail_dependence: max(|R|) / mean(|R|), matching the description in designation
    # reasons ("a single loss ~Xx the mean absolute R"). The previous formula summed all
    # but the three largest R values — a scale-dependent sum that grew with trade count and
    # was not a dependence measure of any kind.
    abs_r = np.abs(r_multiples)
    mean_abs_r = float(np.mean(abs_r)) if len(abs_r) > 0 else 0.0
    max_abs_r = float(np.max(abs_r)) if len(abs_r) > 0 else 0.0
    tail_dependence = round(max_abs_r / mean_abs_r, 4) if mean_abs_r > 0 else 0.0

    map_path = os.path.join(STATE_DIR, "regime_strategy_map.json")
    if not os.path.exists(map_path):
        print(f"ERROR: {map_path} not found. Run vet.py --live first.")
        sys.exit(1)

    with open(map_path, "r", encoding="utf-8") as fh:
        regime_map = json.load(fh)

    # D1 — fail if the map has not been approved for live.
    map_status = regime_map.get("status")
    if map_status not in _VALID_MAP_STATUSES:
        print(
            f"ERROR: Map status is {map_status!r}, not in {_VALID_MAP_STATUSES}. "
            "Run vet.py --live first to produce an approved map before designating."
        )
        sys.exit(1)

    entry = {
        "strategy_id": sid,
        "strategy_key": args.strategy,
        "variant": f"{args.strategy}@{gran}",
        "rank": 999,
        "composite_score": 0.0,
        "selection_basis": "designated",
        # D2 — the declared weight travels ON the entry, so the map and the weights file
        # state the same number and a re-run reproduces the same allocation.
        "designated_weight": args.weight,
        "direction": args.direction,
        "exits": json.loads(args.exits),
        "metrics": {
            "profit_factor": _cap(m["profit_factor"]),
            "sharpe": _cap(m["sharpe"]),
            "win_rate": m["win_rate"],
            "max_drawdown": m["max_drawdown"],
            "recovery_factor": _cap(m["recovery_factor"]),
            "trade_count": m["trade_count"],
            "oos_months": m["oos_months"],
        },
        "gate_failures": failures,
        "designated_by": args.by,
        "designated_reason": args.reason,
        "designated_at_utc": datetime.now(timezone.utc).isoformat(),
        "oos_trade_count": len(strat_oos),
        "ci_mean_r": [round(v, 4) for v in ci_mean_r],
        "pairs_passed_fraction": pairs_passed_fraction,
        "max_pair_share": round(max_pair_share, 4),
        "tail_dependence": tail_dependence,
    }

    if args.dry_run:
        print(f"DRY RUN. Would write entry to {args.regime}:")
        print(json.dumps(entry, indent=2))
        return

    # R1.1 — the designation path is a live map write and is frozen with the rest.
    MC.assert_map_writes_allowed("vetting.designate")

    # D2 — write to one regime only (the one being designated).
    target = args.regime
    bucket = regime_map["regimes"].setdefault(target, [])
    # Idempotent: re-designating replaces the existing entry rather than appending.
    bucket[:] = [e for e in bucket if e.get("strategy_id") != sid]
    bucket.append(entry)

    # A regime that now carries an entry is no longer starved.
    regime_map["empty_regimes"] = [
        r for r in regime_map.get("empty_regimes", []) if r != target
    ]

    # D1 — do NOT touch regime_map["status"]. It was set by vet.py --live.

    # D6 — designation_log: an append-only record of every map mutation.
    log = regime_map.setdefault("designation_log", [])
    log.append(
        {
            "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            "by": args.by,
            "strategy_id": sid,
            "strategy_key": args.strategy,
            "variant": f"{args.strategy}@{gran}",
            "regime": target,
            "gate_failures_at_designation": failures,
        }
    )

    # Validate before writing — D6.
    try:
        _validate(regime_map, "regime-map-contract.json")
    except Exception as e:
        print(f"ERROR: map contract validation failed after designation: {e}")
        sys.exit(1)

    tmp = map_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(regime_map, fh, indent=2)
    os.replace(tmp, map_path)

    written = sum(
        1
        for v in regime_map["regimes"].values()
        for e in v
        if e.get("strategy_key") == args.strategy
    )
    if written == 0:
        print("ERROR: designation wrote no entries — refusing to report success.")
        sys.exit(1)

    # D2 — rewrite weights for the designated regime ONLY. Other regimes retain their
    # vet.py-derived weights unchanged; the previous version rewrote every regime with an
    # inline equal-weight rule and discarded gates.normalized_weights (and with it the
    # softmax, the temperature and the FIX-S1-001 floor) even for cells that qualified on
    # merit and were never designated.
    weights_path = os.path.join(STATE_DIR, "strategy_weights.json")
    with open(weights_path, encoding="utf-8") as fh:
        weights_doc = json.load(fh)

    # D5 — ensure all four regime keys are present (even if empty), so a consumer can tell
    # "no allocation" from "key missing". `Ranging` was absent from the file entirely.
    weights_doc.setdefault("weights", {})
    for r in REGIMES:
        weights_doc["weights"].setdefault(r, {})

    # D2 (third bullet) — a designated cell gets an EXPLICIT, DECLARED weight.
    #
    # It must not be handed to the softmax alongside merit cells. A designated entry
    # carries `composite_score: 0.0`, which is a placeholder meaning "never scored", not a
    # position on the same scale as a merit cell's score. Feeding it to
    # `normalized_weights` makes its allocation a function of the arbitrary magnitude of
    # OTHER cells' scores: against merit scores of ~2-3 it lands on the 0.05 floor, but
    # against scores of ~0.1 the same entry takes roughly half the regime. That is the
    # "accidental weight" D2 names, and it moves with an unrelated run's numbers.
    #
    # So: designated cells take their declared weight off the top, and the merit cells
    # share the remainder through `normalized_weights` — one weighting rule for merit,
    # unchanged, and one declared number for the override.
    target_entries = regime_map["regimes"].get(target, [])
    designated = [e for e in target_entries if e.get("selection_basis") == "designated"]
    merit = [e for e in target_entries if e.get("selection_basis") != "designated"]

    declared: Dict[str, float] = {}
    for e in designated:
        # `designated_weight` is recorded on the entry itself so the map and the weights
        # file state the same number, and re-running designation is idempotent.
        declared[G._variant_key(e)] = float(e.get("designated_weight", args.weight))

    declared_total = sum(declared.values())
    if declared_total > 1.0 + 1e-9:
        print(
            f"ERROR: declared designated weights in {target} sum to {declared_total:.6f}, "
            f"which exceeds 1.0. Lower --weight, or remove a designation."
        )
        sys.exit(1)
    if merit and declared_total > 1.0 - 1e-9:
        print(
            f"ERROR: declared designated weights in {target} consume the entire regime "
            f"({declared_total:.6f}) but {len(merit)} merit-qualified cell(s) are present "
            "and would be allocated zero. Lower --weight."
        )
        sys.exit(1)

    if merit:
        remainder = 1.0 - declared_total
        merit_weights = G.normalized_weights(merit)
        target_weights = {k: v * remainder for k, v in merit_weights.items()}
        target_weights.update(declared)
    elif declared_total > 0:
        # Designated-only regime: renormalise the declared weights among themselves so the
        # sum-to-1 invariant holds. With a single designation this is 1.0.
        target_weights = {k: v / declared_total for k, v in declared.items()}
    else:
        target_weights = {}

    # D3 — keys come from `_variant_key` (strategy@granularity), never bare strategy_id.
    # Keying by strategy_id is the FIX-S1-004 collision: a strategy qualifying at two
    # granularities in one regime collapses to a single key and the sum stops being 1.0.
    weights_doc["weights"][target] = {k: round(v, 8) for k, v in target_weights.items()}

    # D3 — widen the sum-to-1 tolerance to 1e-4.
    for r, w in weights_doc["weights"].items():
        if not w:
            continue
        total = sum(w.values())
        if abs(total - 1.0) > 1e-4:
            print(
                f"ERROR: weights for {r} sum to {total:.10f}, not 1.0 — refusing to write."
            )
            sys.exit(1)

    weights_doc["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    weights_doc["qualification_run_id"] = regime_map.get("qualification_run_id")

    # D6 — validate weights before writing.
    try:
        _validate(weights_doc, "weights-contract.json")
    except Exception as e:
        print(f"ERROR: weights contract validation failed after designation: {e}")
        sys.exit(1)

    wtmp = weights_path + ".tmp"
    with open(wtmp, "w", encoding="utf-8") as fh:
        json.dump(weights_doc, fh, indent=2)
    os.replace(wtmp, weights_path)

    # D6 — emit a designation report alongside, so every mutation of the live map has a
    # distinct, timestamped record.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    designation_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy_id": sid,
        "strategy_key": args.strategy,
        "variant": f"{args.strategy}@{gran}",
        "regime": target,
        "by": args.by,
        "reason": args.reason,
        "gate_failures": failures,
        "metrics_at_designation": entry["metrics"],
        "ci_mean_r": ci_mean_r,
        "pairs_passed_fraction": pairs_passed_fraction,
        "max_pair_share": max_pair_share,
        "tail_dependence": tail_dependence,
        "weights_after": weights_doc["weights"].get(target, {}),
    }
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"designation_report_{ts}.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(designation_report, fh, indent=2)

    print(f"Designated {args.strategy}@{gran} into {target} regime.")
    print(f"Gate failures: {failures}")
    print(f"Weights for {target}: {weights_doc['weights'].get(target)}")
    print(f"Designation report: {report_path}")


if __name__ == "__main__":
    main()
