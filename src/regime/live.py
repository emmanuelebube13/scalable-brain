"""R2.2 / R2.3(b) — resolve the routing regime from the canonical table, and record it.

Two responsibilities, deliberately separated:

:func:`current_regimes`
    Reads the newest label per instrument from ``fact_regime_structural``. It does **not**
    recompute. Before this, ``signals/run.py`` called ``build_structural_labels`` on a
    3-year window of its own while ``publish_strategy_stats.py`` used 25 years and the
    Gatekeeper used full history — three callers, three frames, three answers for the same
    bar (agreement 0.998-0.999). Computing once and reading everywhere removes the drift
    rather than shrinking it.

:func:`record_live_labels`
    Appends what was just read to ``fact_regime_structural_live``, so the label that
    routed a signal leaves a durable record. Until now it left none:
    ``system1/regime_status/latest.json`` is overwritten every run, so after the fact there
    was no way to answer "what did we think the regime was when we placed that trade?"

The second must never be able to break the first. It is called inside its own try/except
at the call site, and the table is an observer with no vote in routing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from src.common.db import get_engine
from src.regime import structural as S
from src.regime.structural_schema import CANONICAL_TABLE, LIVE_TABLE

logger = logging.getLogger("system1.regime.live")

#: Bar duration per granularity, used to decide whether the newest bar has actually
#: closed. Structural labels are D1-only today.
_BAR_HOURS = {"D1": 24.0, "H4": 4.0, "H1": 1.0}


def _latest_rows(granularity: str = "D1") -> List[Dict[str, Any]]:
    """Newest labelled bar per instrument, with its indicators and frame provenance."""
    sql = text(f"""
        SELECT DISTINCT ON (r.asset_id)
               r.asset_id, a.symbol, r.granularity, r.bar_time_utc, r.regime,
               r.source_bar_time_utc, r.adx, r.ema_fast, r.ema_slow, r.atr_pct,
               r.vol_zscore, r.labeller_version,
               (SELECT count(*) FROM {CANONICAL_TABLE} c
                 WHERE c.asset_id = r.asset_id AND c.granularity = r.granularity)
                 AS frame_row_count
        FROM {CANONICAL_TABLE} r
        JOIN dim_asset a ON a.asset_id = r.asset_id
        WHERE r.granularity = :g
        ORDER BY r.asset_id, r.bar_time_utc DESC
        """)
    with get_engine().connect() as conn:
        return [dict(m) for m in conn.execute(sql, {"g": granularity}).mappings()]


def current_regimes(
    granularity: str = "D1", now: Optional[datetime] = None
) -> Tuple[Dict[str, str], Dict[str, Dict[str, float]], List[Dict[str, Any]]]:
    """``(regimes, probs, rows)`` for routing, read from the canonical table.

    ``probs`` is a one-hot. The structural label is a deterministic rule, not a posterior,
    so a one-hot is the honest encoding: it says "this label, per the rule" rather than
    inventing a distribution nobody computed.

    ``rows`` carries the provenance needed by :func:`record_live_labels`; callers routing
    signals only need the first two.
    """
    now = now or datetime.now(timezone.utc)
    rows = _latest_rows(granularity)
    regimes: Dict[str, str] = {}
    probs: Dict[str, Dict[str, float]] = {}

    for row in rows:
        label = str(row["regime"])
        inst = str(row["symbol"])
        # UNKNOWN means "no label could be formed". It is not a tradable regime and must
        # never be offered to the router as one.
        if label == S.UNKNOWN:
            logger.warning(
                "%s newest structural label is UNKNOWN (bar %s) — not routable",
                inst,
                row["bar_time_utc"],
            )
            continue
        regimes[inst] = label
        probs[inst] = {
            "trending_up": 1.0 if label == "Trending-Up" else 0.0,
            "trending_down": 1.0 if label == "Trending-Down" else 0.0,
            "ranging": 1.0 if label == "Ranging" else 0.0,
            "high_vol": 1.0 if label == "High-Vol" else 0.0,
        }
    return regimes, probs, rows


def _bar_is_complete(bar_time: datetime, granularity: str, now: datetime) -> bool:
    """Has the newest bar actually closed, or is it still forming?

    In backtest the frame ends at the last complete bar; in live it may end at today's
    forming bar. Because of the ``shift(1)`` those two cases produce different labels for
    the same trading moment — the same code, the same instant, a different answer. Recorded
    per row rather than assumed, so the question is answerable from the data later.
    """
    hours = _BAR_HOURS.get(granularity, 24.0)
    return bar_time + timedelta(hours=hours) <= now


INSERT_LIVE = f"""
INSERT INTO {LIVE_TABLE}
    (asset_id, granularity, bar_time_utc, regime, source_bar_time_utc,
     frame_last_bar_time_utc, frame_last_bar_complete, frame_row_count,
     computed_at_utc, code_git_sha, labeller_version, indicator_snapshot)
VALUES (:asset_id, :granularity, :bar_time_utc, :regime, :source_bar_time_utc,
        :frame_last_bar_time_utc, :frame_last_bar_complete, :frame_row_count,
        :computed_at_utc, :code_git_sha, :labeller_version, CAST(:snapshot AS jsonb))
ON CONFLICT ON CONSTRAINT uq_regime_structural_live DO NOTHING
"""


def record_live_labels(
    rows: List[Dict[str, Any]], now: Optional[datetime] = None
) -> int:
    """Append one row per instrument to the append-only live record. Returns rows written.

    ``ON CONFLICT DO NOTHING`` — never ``DO UPDATE``. The unique key includes
    ``computed_at_utc``, so two runs that label the same bar differently at different times
    keep BOTH rows. That divergence is the entire reason this table exists; deduplicating
    it would destroy the evidence.
    """
    from src.vetting.map_contract import git_sha

    now = now or datetime.now(timezone.utc)
    sha = git_sha()
    written = 0

    with get_engine().begin() as conn:
        for row in rows:
            snapshot = {
                k: (float(row[k]) if row.get(k) is not None else None)
                for k in ("adx", "ema_fast", "ema_slow", "atr_pct", "vol_zscore")
            }
            conn.execute(
                text(INSERT_LIVE),
                {
                    "asset_id": int(row["asset_id"]),
                    "granularity": str(row["granularity"]),
                    "bar_time_utc": row["bar_time_utc"],
                    "regime": str(row["regime"]),
                    "source_bar_time_utc": row.get("source_bar_time_utc"),
                    # The canonical table IS the frame the live path reads, so its newest
                    # bar and row count are the frame provenance.
                    "frame_last_bar_time_utc": row["bar_time_utc"],
                    "frame_last_bar_complete": _bar_is_complete(
                        row["bar_time_utc"], str(row["granularity"]), now
                    ),
                    "frame_row_count": int(row.get("frame_row_count") or 0),
                    "computed_at_utc": now,
                    "code_git_sha": sha,
                    "labeller_version": str(
                        row.get("labeller_version") or S.LABELLER_VERSION
                    ),
                    "snapshot": json.dumps(snapshot),
                },
            )
            written += 1
    return written
