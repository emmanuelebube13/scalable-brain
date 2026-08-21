import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.registry import catalog
from src.vetting.vet import INTEGRITY_DISQUALIFIED, STATE_DIR, _cap
from src.vetting import gates as G
from src.attribution import attribute as attr


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--by", required=True)
    p.add_argument("--direction", default="both")
    p.add_argument("--exits", default="{}")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    try:
        record = catalog.by_key(args.strategy)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    sid = record.strategy_id

    if sid in INTEGRITY_DISQUALIFIED:
        print(
            f"ERROR: Strategy {sid} ({args.strategy}) is INTEGRITY_DISQUALIFIED. Reason: {INTEGRITY_DISQUALIFIED[sid]}"
        )
        sys.exit(1)

    engine = get_engine()
    trades = attr._load_trades(engine)
    strat_trades = trades[(trades["strategy_id"] == sid) & (trades["is_oos"] == True)]

    if len(strat_trades) == 0:
        print(f"ERROR: Strategy {sid} has 0 OOS trades.")
        sys.exit(1)

    folds_by_gran = attr._folds_by_granularity(strat_trades)
    gran = strat_trades["granularity"].iloc[0]
    folds = folds_by_gran.get(str(gran), {})
    m = attr._oos_cell_metrics(strat_trades, folds)

    passed, failures = G.evaluate_gates(m)

    print(f"Strategy {args.strategy} gate evaluation (Pooled OOS):")
    print(f"Passed: {passed}")
    print(f"Failures: {failures}")

    if not failures:
        # Actually, it's fine if it passes, we can still designate it, or not?
        pass

    r_multiples = strat_trades["r_multiple"].to_numpy(dtype=float)
    np.random.seed(42)
    means = [
        np.mean(np.random.choice(r_multiples, size=len(r_multiples), replace=True))
        for _ in range(1000)
    ]
    ci_mean_r = [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]

    max_pair_share = strat_trades["asset_id"].value_counts().max() / len(strat_trades)

    r_sorted = np.sort(r_multiples)
    tail_dependence = (
        float(np.sum(r_sorted[:-3])) if len(r_sorted) > 3 else float(np.sum(r_sorted))
    )

    with engine.connect() as conn:
        run_id = conn.execute(
            text(
                "SELECT qualification_run_id FROM fact_strategy_regime_attribution ORDER BY created_at DESC LIMIT 1"
            )
        ).scalar()
        cells = (
            conn.execute(
                text(
                    "SELECT * FROM fact_strategy_regime_attribution WHERE strategy_id = :sid AND qualification_run_id = :rid"
                ),
                {"sid": sid, "rid": run_id},
            )
            .mappings()
            .all()
        )

    attempted = len(cells)

    # We must mock a cell dict for evaluate_gates, ensuring we provide everything
    passed_cells = 0
    for c in cells:
        c_dict = dict(c)
        c_dict["oos_months"] = c_dict.get("oos_months") or 0.0
        c_dict["low_confidence"] = c_dict.get("low_confidence") or False
        if G.evaluate_gates(c_dict)[0]:
            passed_cells += 1

    pairs_passed_fraction = f"{passed_cells}/{attempted}" if attempted > 0 else "0/0"

    map_path = os.path.join(STATE_DIR, "regime_strategy_map.json")
    if not os.path.exists(map_path):
        print(f"ERROR: {map_path} not found. Run vet.py --live first.")
        sys.exit(1)

    with open(map_path, "r") as f:
        regime_map = json.load(f)

    entry = {
        "strategy_id": sid,
        "strategy_key": args.strategy,
        "variant": f"{args.strategy}@{gran}",
        "rank": 999,
        "composite_score": 0.0,
        "selection_basis": "designated",
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
        "oos_trade_count": len(strat_trades),
        "ci_mean_r": [round(c, 4) for c in ci_mean_r],
        "pairs_passed_fraction": pairs_passed_fraction,
        "max_pair_share": round(float(max_pair_share), 4),
        "tail_dependence": round(float(tail_dependence), 4),
    }

    if args.dry_run:
        print("DRY RUN. Would write entry to all regimes in the map:")
        print(json.dumps(entry, indent=2))
    else:
        # `regimes` is {} whenever vetting qualified nobody — all four labels sit in
        # `empty_regimes` instead. Iterating `regimes` therefore appended to NOTHING and
        # still printed success, so the command silently no-opped in the exact situation
        # it exists for. Seed the keys explicitly.
        all_regimes = ("Trending-Up", "Trending-Down", "Ranging", "High-Vol")
        targets = list(regime_map["regimes"].keys()) or list(all_regimes)
        for r in targets:
            bucket = regime_map["regimes"].setdefault(r, [])
            # Idempotent: re-designating replaces, never appends. A duplicate
            # strategy_id in one regime silently collapsed a strategy's weight once
            # already (FIX-S1-004), and here it would also halve the computed share.
            bucket[:] = [e for e in bucket if e.get("strategy_id") != sid]
            bucket.append(entry)

        # A regime that now carries an entry is no longer starved.
        regime_map["empty_regimes"] = [
            r for r in regime_map.get("empty_regimes", []) if r not in targets
        ]

        # `status` is mandatory under the bumped contract (agreed with System 2 on
        # 2026-08-15: a consumer REJECTS on missing/unrecognised status, because
        # "unknown is never a permissive default"). vet.py does not write it, so a map
        # that only ever passed through vet fails contract validation. Set it here and
        # move the schema_version with it, so the artefact declares the shape it has.
        regime_map["status"] = "published"
        regime_map["schema_version"] = "2.0.0"

        tmp = map_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(regime_map, f, indent=2)
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

        # The map and the weights are two halves of one instruction. A map entry with no
        # weight tells System 3 "trade this" and gives it no size to trade — and
        # serialize._guard_inputs only checks the map is non-empty, so an inconsistent
        # pair would publish silently. Weights are re-derived here from the map so the
        # two cannot drift.
        weights_path = os.path.join(STATE_DIR, "strategy_weights.json")
        with open(weights_path, encoding="utf-8") as f:
            weights_doc = json.load(f)
        for r, entries in regime_map["regimes"].items():
            if not entries:
                continue
            # Equal weight across the entries present in the regime. With a single
            # designated strategy this is 1.0; the shape generalises without inviting a
            # second, softer weighting rule to grow beside gates.normalized_weights.
            share = round(1.0 / len(entries), 6)
            weights_doc.setdefault("weights", {})[r] = {
                str(e["strategy_id"]): share for e in entries
            }
        weights_doc["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        weights_doc["qualification_run_id"] = regime_map.get("qualification_run_id")

        wtmp = weights_path + ".tmp"
        with open(wtmp, "w", encoding="utf-8") as f:
            json.dump(weights_doc, f, indent=2)
        os.replace(wtmp, weights_path)

        for r, w in weights_doc["weights"].items():
            total = sum(w.values())
            if abs(total - 1.0) > 1e-6:
                print(f"ERROR: weights for {r} sum to {total}, not 1.0 — refusing.")
                sys.exit(1)

        print(f"Designated strategy added to map in {written} regime(s): {targets}")
        print(f"Weights written: {json.dumps(weights_doc['weights'])}")


if __name__ == "__main__":
    main()
