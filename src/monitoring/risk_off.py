"""R4.2 — freshness contracts, and the risk-off flag the producer actually reads.

The thing this module fixes is NOT a missing check
--------------------------------------------------
``fact_market_regime_v2`` stopped updating on 2026-08-24 while prices ran to 2026-09-04.
The heartbeat **detected this correctly, every single day**:

    2026-09-04T09:00:01Z CRITICAL regimes=CRITICAL: 10.5 days behind the last market
                                  close; latest row 2026-08-24 09:00Z

It wrote ``results/state/HEARTBEAT_ALERT``, appended to ``logs/heartbeat_alerts.log``,
and exited 2. No hold suppressed it. It was right, it was loud, and it was ignored —
because **nothing read it**. ``grep`` over the whole repo finds no consumer of
``HEARTBEAT_ALERT`` outside ``heartbeat.py`` itself, and ``src/monitoring/__init__.py``
says so in as many words: "No integrations."

So for twelve days the producer emitted signals every hour, routed through a map built on
labels that had stopped moving, while the system's own monitoring screamed CRITICAL each
morning into a file nobody opened.

The gap was never detection. It was **consequence**. This module is the consequence:
a stale decision-path input now stops trading instead of being traded on.

Two independent triggers, deliberately
--------------------------------------
1. **Live evaluation.** The producer evaluates the contracts itself, on its own run. A
   flag written by a once-daily heartbeat would let a breach trade for up to 24 hours
   before anything noticed; evaluating in-process bounds that by the producer's own
   cadence instead.
2. **A flag file.** ``results/state/RISK_OFF`` lets the heartbeat, or a human, force
   risk-off for a reason this module cannot compute.

Either one refuses. They are ORed, never ANDed: a mechanism where two things must agree
before trading stops is a mechanism that fails open.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from src.monitoring.freshness import last_market_close, market_is_open

logger = logging.getLogger("system1.monitoring.risk_off")

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATE_DIR = os.path.join(_REPO_ROOT, "results", "state")

#: Set this file to force risk-off regardless of measured freshness. Written by the
#: heartbeat on a blocking breach; also writable by hand. Presence == refuse to emit.
RISK_OFF_FLAG = os.path.join(STATE_DIR, "RISK_OFF")


@dataclass(frozen=True)
class Contract:
    """A maximum staleness one decision-path input must satisfy.

    ``blocking`` is the load-bearing field. A non-blocking contract alerts and is
    recorded, but does not stop trading — reserved for inputs that genuinely are not on
    the decision path.
    """

    name: str
    max_staleness_hours: float
    blocking: bool
    why: str
    #: None means "no bar-open allowance"; otherwise the bar duration in hours. Bars are
    #: stamped at their OPEN, so the freshest possible row for a granularity is already
    #: one bar-width old the instant it closes. Without this, a perfectly healthy D1
    #: series reads as 24 hours stale.
    bar_hours: float = 0.0
    granularity: Optional[str] = None


CONTRACTS: List[Contract] = [
    Contract(
        name="fact_market_prices",
        max_staleness_hours=3.0,
        bar_hours=1.0,
        blocking=True,
        why="every signal is computed from the newest closed bar; stale prices mean "
        "trading on a stale view of the market",
    ),
    Contract(
        name="fact_regime_structural",
        granularity="D1",
        max_staleness_hours=30.0,
        bar_hours=24.0,
        blocking=True,
        why="the canonical label that routes every signal (D1)",
    ),
    Contract(
        name="fact_regime_structural",
        granularity="H4",
        max_staleness_hours=10.0,
        bar_hours=4.0,
        blocking=True,
        why="the canonical label that routes every signal (H4)",
    ),
    Contract(
        name="fact_regime_structural",
        granularity="H1",
        max_staleness_hours=7.0,
        bar_hours=1.0,
        blocking=True,
        why="the canonical label that routes every signal (H1)",
    ),
    Contract(
        name="fact_regime_structural_live",
        granularity="D1",
        max_staleness_hours=30.0,
        bar_hours=24.0,
        blocking=False,
        why="observability of live-vs-backtest label divergence (D1)",
    ),
    Contract(
        name="fact_regime_structural_live",
        granularity="H4",
        max_staleness_hours=10.0,
        bar_hours=4.0,
        blocking=False,
        why="observability of live-vs-backtest label divergence (H4)",
    ),
    Contract(
        name="fact_regime_structural_live",
        granularity="H1",
        max_staleness_hours=7.0,
        bar_hours=1.0,
        blocking=False,
        why="observability of live-vs-backtest label divergence (H1)",
    ),
    Contract(
        name="regime_strategy_map.json",
        max_staleness_hours=7 * 24.0,
        blocking=True,
        why="a map that outlives its evidence must stop trading; primary enforcement is "
        "the R1.3 admissibility check, this is defence in depth",
    ),
    Contract(
        name="fact_market_regime_v2",
        max_staleness_hours=30.0,
        bar_hours=24.0,
        blocking=False,
        why="research only as of 2026-09; retained so its decay stays visible",
    ),
]


@dataclass(frozen=True)
class Breach:
    contract: Contract
    detail: str
    age_hours: Optional[float]

    @property
    def blocking(self) -> bool:
        return self.contract.blocking

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.contract.name,
            "blocking": self.contract.blocking,
            "detail": self.detail,
            "age_hours": (
                round(self.age_hours, 2) if self.age_hours is not None else None
            ),
            "max_staleness_hours": self.contract.max_staleness_hours,
            "why": self.contract.why,
        }


def _reference_time(now: datetime) -> datetime:
    """The instant against which staleness is measured.

    When the market is shut, data *cannot* be fresher than the Friday close, so measuring
    against ``now`` would flag every weekend. This is the same reasoning
    ``freshness.py`` already applies to prices, reused rather than re-derived.
    """
    return now if market_is_open(now) else last_market_close(now)


def _latest_row(table: str, column: str, granularity: Optional[str] = None) -> Optional[datetime]:
    """Newest timestamp in a table, or None if the table is absent or empty."""
    from sqlalchemy import text

    from src.common.db import get_engine

    with get_engine().connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}
        ).scalar()
        if exists is None:
            raise LookupError(f"table {table} does not exist")
        # Table and column names are module constants from CONTRACTS, never user input;
        # they are still not interpolated from anything caller-supplied.
        if granularity:
            return conn.execute(text(f"SELECT max(\"{column}\") FROM {table} WHERE granularity = '{granularity}'")).scalar()
        else:
            return conn.execute(text(f'SELECT max("{column}") FROM {table}')).scalar()


_TABLE_COLUMNS = {
    "fact_market_prices": "timestamp",
    "fact_market_regime_v2": "timestamp",
    "fact_regime_structural": "bar_time_utc",
    "fact_regime_structural_live": "bar_time_utc",
}


def _evaluate_table(contract: Contract, now: datetime) -> Optional[Breach]:
    try:
        latest = _latest_row(contract.name, _TABLE_COLUMNS[contract.name], contract.granularity)
    except LookupError as exc:
        # A missing table is a BREACH, not an exemption. Fail-closed: "the input I am
        # required to check is not there" is never a reason to proceed.
        return Breach(contract, f"{exc}", None)
    except Exception as exc:  # noqa: BLE001
        return Breach(contract, f"could not evaluate ({exc})", None)

    if latest is None:
        return Breach(contract, "table is empty", None)

    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    allowed = contract.max_staleness_hours + contract.bar_hours
    age = (_reference_time(now) - latest).total_seconds() / 3600.0
    if age > allowed:
        return Breach(
            contract,
            f"newest row {latest.isoformat()} is {age:.1f}h behind "
            f"{'now' if market_is_open(now) else 'the last market close'}, "
            f"over the {allowed:.0f}h limit",
            age,
        )
    return None


def _evaluate_map(contract: Contract, now: datetime) -> Optional[Breach]:
    """Age the map by what it SAYS about itself, never by its file mtime.

    mtime was the first implementation and it is wrong, demonstrably: on 2026-09-05 the
    map file was hand-edited to remove one entry, which reset its mtime and made a map
    whose own header still read ``generated_at_utc: 2026-08-24`` look five hours old to
    this check. Any touch of the file — an edit, a copy, a restore from backup — silently
    renews a stale artifact's licence to trade.

    The declared timestamp cannot be refreshed without actually rebuilding the map. If a
    map declares no timestamp at all, that is a breach rather than a pass: an artifact
    that will not say how old it is has not earned the benefit of the doubt.
    """
    path = os.path.join(STATE_DIR, "regime_strategy_map.json")
    if not os.path.exists(path):
        return Breach(contract, f"{path} does not exist", None)

    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001
        return Breach(contract, f"map is unreadable ({exc})", None)

    declared = payload.get("built_at_utc") or payload.get("generated_at_utc")
    if not declared:
        return Breach(
            contract,
            "map declares neither built_at_utc nor generated_at_utc, so its age cannot "
            "be established",
            None,
        )
    try:
        built = datetime.fromisoformat(str(declared).replace("Z", "+00:00"))
    except ValueError:
        return Breach(contract, f"map timestamp {declared!r} is unparseable", None)
    if built.tzinfo is None:
        return Breach(contract, f"map timestamp {declared!r} is timezone-naive", None)

    age = (now - built).total_seconds() / 3600.0
    if age > contract.max_staleness_hours:
        return Breach(
            contract,
            f"map declares it was built {built.isoformat()} — {age / 24:.1f} days ago, "
            f"over the {contract.max_staleness_hours / 24:.0f} day limit",
            age,
        )
    return None


def evaluate_contracts(now: Optional[datetime] = None) -> List[Breach]:
    """Every freshness contract currently in breach, blocking and non-blocking alike."""
    now = now or datetime.now(timezone.utc)
    breaches: List[Breach] = []
    for contract in CONTRACTS:
        checker: Callable[[Contract, datetime], Optional[Breach]] = (
            _evaluate_map if contract.name.endswith(".json") else _evaluate_table
        )
        breach = checker(contract, now)
        if breach is not None:
            breaches.append(breach)
    return breaches


# --------------------------------------------------------------------------- #
# The flag file
# --------------------------------------------------------------------------- #
def flag_reasons() -> List[str]:
    """Reasons recorded in the RISK_OFF flag file, or [] when it is absent.

    An unreadable flag file counts as SET. The file exists to stop trading; a parse error
    in it must not become a way to resume.
    """
    if not os.path.exists(RISK_OFF_FLAG):
        return []
    try:
        with open(RISK_OFF_FLAG, encoding="utf-8") as fh:
            payload = json.load(fh)
        reasons = payload.get("reasons") or ["RISK_OFF flag set (no reason recorded)"]
        return [str(r) for r in reasons]
    except Exception as exc:  # noqa: BLE001
        return [f"RISK_OFF flag present but unreadable ({exc}) — treating as set"]


def set_flag(reasons: List[str]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    payload = {
        "set_at_utc": datetime.now(timezone.utc).isoformat(),
        "reasons": reasons,
    }
    tmp = RISK_OFF_FLAG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, RISK_OFF_FLAG)
    logger.error("RISK-OFF SET: %s", "; ".join(reasons))


def clear_flag() -> None:
    if os.path.exists(RISK_OFF_FLAG):
        os.remove(RISK_OFF_FLAG)
        logger.info("RISK-OFF cleared: no blocking freshness breaches remain")


def refuse_reasons(now: Optional[datetime] = None) -> List[str]:
    """Why the producer must not emit right now. Empty list == clear to emit.

    ORs the live contract evaluation with the flag file. Non-blocking breaches are
    logged but deliberately excluded — they are alerts, not gates.
    """
    reasons = list(flag_reasons())
    for breach in evaluate_contracts(now):
        if breach.blocking:
            reasons.append(f"{breach.contract.name}: {breach.detail}")
        else:
            logger.warning(
                "freshness ALERT (non-blocking) %s: %s",
                breach.contract.name,
                breach.detail,
            )
    return reasons
