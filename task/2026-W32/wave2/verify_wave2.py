"""Central Wave-2 verification — the checks the fleet agents could not run.

Agents are barred from the database (fleet hard rule 6), so each proves look-ahead
freedom only on its hand-built fixture frames. PROMPT.md's definition of done also
requires ``assert_no_lookahead_v2`` **against real data**. That is this script.

For every landed research strategy:

1. import it and instantiate the single StrategyV2 subclass it defines
2. check ``metadata.strategy_id`` matches the filename
3. build REAL frames from the database for each declared pair
4. run ``assert_no_lookahead_v2`` against that real data
5. record the order count, so a strategy that fires almost nowhere on ten years of
   real data is visible rather than silently "passing" (the probe rejects a
   zero-order strategy, but the difference between 3 orders and 3000 matters)

Static ban-pattern scanning (``shift(-``, ``center=True``, ``detect_swing_points``,
``index <= ``) is done separately in the shell.

Usage:  python task/2026-W32/wave2/verify_wave2.py [strategy_id ...]   (default: all)
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.layer0.strategies.contract_v2 import (  # noqa: E402
    StrategyV2,
    assert_no_lookahead_v2,
)
from src.layer0.strategies.v2_harness import build_frames  # noqa: E402

RESEARCH = ROOT / "src" / "layer0" / "strategies" / "research"
SKIP = {"__init__", "example_ma_cross", "reference_pullback_continuation"}


def strategy_classes(module_name: str) -> List[type]:
    """The concrete StrategyV2 subclasses defined *in* this module."""
    mod = importlib.import_module(module_name)
    out = []
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if (
            issubclass(obj, StrategyV2)
            and obj is not StrategyV2
            and obj.__module__ == module_name
            and not inspect.isabstract(obj)
        ):
            out.append(obj)
    return out


def main(argv: List[str]) -> int:
    wanted = set(argv) or None
    ids = sorted(
        p.stem
        for p in RESEARCH.glob("*.py")
        if p.stem not in SKIP and (wanted is None or p.stem in wanted)
    )
    if not ids:
        print("no research strategies found")
        return 0

    frame_cache: Dict[tuple, Any] = {}
    results: List[Dict[str, Any]] = []

    for sid in ids:
        row: Dict[str, Any] = {"strategy_id": sid}
        try:
            classes = strategy_classes(f"src.layer0.strategies.research.{sid}")
            if len(classes) != 1:
                row.update(
                    status="FAIL",
                    stage="class_discovery",
                    error=f"expected exactly 1 StrategyV2 subclass, found "
                    f"{[c.__name__ for c in classes]}",
                )
                results.append(row)
                print(f"{row['status']:5} {sid}", flush=True)
                continue
            strat = classes[0]()
            meta = strat.metadata
            row["class"] = classes[0].__name__
            row["primary"] = meta.primary_granularity
            row["context"] = list(meta.context_granularities)
            row["pairs"] = list(meta.pairs)
            if meta.strategy_id != sid:
                row.update(
                    status="FAIL",
                    stage="metadata",
                    error=f"metadata.strategy_id {meta.strategy_id!r} != "
                    f"filename {sid!r}",
                )
                results.append(row)
                print(f"{row['status']:5} {sid}", flush=True)
                continue
        except Exception as exc:  # noqa: BLE001
            row.update(
                status="FAIL",
                stage="import",
                error=f"{type(exc).__name__}: {exc}",
                traceback=traceback.format_exc()[-1500:],
            )
            results.append(row)
            print(f"{row['status']:5} {sid}", flush=True)
            continue

        per_pair: Dict[str, Any] = {}
        probed = False
        for pair in meta.pairs:
            key = (pair, meta.primary_granularity, tuple(meta.context_granularities))
            if key not in frame_cache:
                try:
                    frame_cache[key] = build_frames(
                        pair,
                        meta.primary_granularity,
                        meta.context_granularities,
                        lookback_years=10,
                    )
                except Exception as exc:  # noqa: BLE001
                    frame_cache[key] = f"LOAD_ERROR: {type(exc).__name__}: {exc}"
            frames = frame_cache[key]
            if isinstance(frames, str):
                per_pair[pair] = frames
                continue
            if frames is None:
                per_pair[pair] = "no_data (pair/granularity not backfilled)"
                continue
            try:
                orders = list(strat.generate_orders(frames))
                longs = sum(1 for o in orders if o.direction == 1)
                assert_no_lookahead_v2(strat, frames)
                per_pair[pair] = {
                    "probe": "PASS",
                    "orders": len(orders),
                    "long": longs,
                    "short": len(orders) - longs,
                    "bars": int(len(frames[meta.primary_granularity])),
                }
                probed = True
            except Exception as exc:  # noqa: BLE001
                per_pair[pair] = {
                    "probe": "FAIL",
                    "error": f"{type(exc).__name__}: {exc}"[:600],
                }
        row["per_pair"] = per_pair
        failed = [
            p
            for p, v in per_pair.items()
            if isinstance(v, dict) and v.get("probe") == "FAIL"
        ]
        if failed:
            row["status"] = "FAIL"
            row["stage"] = "lookahead_probe"
        elif not probed:
            row["status"] = "SKIP"
            row["stage"] = "no_real_data_for_any_declared_pair"
        else:
            row["status"] = "PASS"
        results.append(row)
        print(f"{row['status']:5} {sid}", flush=True)

    out = Path(__file__).resolve().parent / "VERIFY_REAL_DATA.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    counts: Dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + json.dumps(counts), flush=True)
    print(f"wrote {out}")
    return 0 if counts.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
