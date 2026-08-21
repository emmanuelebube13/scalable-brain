"""Entry point: score cross-sectional currency momentum as one portfolio.

    python -m src.portfolio.run_momentum
    python -m src.portfolio.run_momentum --json results/reports/portfolio_momentum.json

Read-only. Touches no live artifact, writes no map, promotes nothing — there is no path
from this module to the champion bundle by design (`task/OPEN.md` item 5).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.portfolio.bundle import build_bundle
from src.portfolio.evaluate import evaluate
from src.portfolio.schedule import build_weight_schedule

logger = logging.getLogger("system1.portfolio.run_momentum")

DEFAULT_PAIRS: Sequence[str] = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
)

#: The two cost points pre-registered in PREREGISTRATION.md: free, and 2 bp of turnover
#: (which brackets the 1.8-2.9 pip spreads measured on this account).
COST_ARMS: Sequence[float] = (0.0, 0.0002)


def run(
    pairs: Sequence[str] = DEFAULT_PAIRS, granularity: str = "D1"
) -> Dict[str, object]:
    frames, closes, report = build_bundle(list(pairs), granularity)
    schedule = build_weight_schedule(closes)

    arms: List[Dict[str, object]] = []
    for vol_scaled in (False, True):
        for cost in COST_ARMS:
            result = evaluate(
                closes, schedule, cost_per_unit_turnover=cost, vol_scaled=vol_scaled
            )
            arms.append(result)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pairs": list(pairs),
        "granularity": granularity,
        "bundle": report.summary(),
        "rebalances": int(len(schedule)),
        "first_rebalance": str(schedule.index[0]),
        "last_rebalance": str(schedule.index[-1]),
        "arms": arms,
    }


def _print(summary: Dict[str, Any]) -> None:
    first = str(summary["first_rebalance"])[:10]
    last = str(summary["last_rebalance"])[:10]
    print(f"\nbundle    : {summary['bundle']}")
    print(f"rebalances: {summary['rebalances']} ({first} -> {last})\n")

    header = (
        f"{'vol_scaled':>10} {'cost':>7} | {'Sharpe':>7} {'PF':>6} {'MaxDD':>7} "
        f"{'AnnRet':>8} | {'oosSharpe':>9} {'oosPF':>6}"
    )
    print(header)
    print("-" * len(header))
    arms: List[Dict[str, Any]] = summary["arms"]
    for arm in arms:
        f: Dict[str, float] = arm["full_sample"]
        o: Dict[str, float] = arm["walk_forward_oos"]
        print(
            f"{str(arm['vol_scaled']):>10} {arm['cost_per_unit_turnover']:>7.4f} | "
            f"{f['sharpe']:>7.3f} {f['profit_factor']:>6.3f} "
            f"{f['max_drawdown']*100:>6.1f}% {f['annualized_return']*100:>7.2f}% | "
            f"{o['sharpe']:>9.3f} {o['profit_factor']:>6.3f}"
        )
    print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--granularity", default="D1")
    parser.add_argument("--json", dest="json_path", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    summary = run(granularity=args.granularity)
    _print(summary)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, default=str)
        logger.info("wrote %s", args.json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
