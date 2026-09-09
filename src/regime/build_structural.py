"""R2.3(b) / R2.4 — the ONE place structural labels are computed.

Why a single computation path is the real fix
---------------------------------------------
The labeller is deterministic, but it is not lookback-invariant: ``ewm(adjust=False)``
seeds from the first row of whatever frame it is handed, and callers were handing it
different frames — ``signals/run.py`` three years, ``analytics/publish_strategy_stats.py``
twenty-five, the Gatekeeper full history. Measured agreement between those was 0.998-0.999,
so the same bar could carry different labels depending on who asked.

R2.3(a) shrinks that by seeding the EMA with an SMA. **This module removes it.** Labels are
computed here, over each instrument's FULL history from a fixed anchor, written to
``fact_regime_structural``, and every consumer reads the table instead of recomputing.
Drift cannot survive a design where the value is computed once.

``ANCHOR_DATE`` matters as much as the code: computing "full history" as
``NOW() - N years`` would move the frame's start every single day, reintroducing exactly
the variability this module exists to remove.

Usage::

    python -m src.regime.build_structural                 # backfill/refresh all pairs
    python -m src.regime.build_structural --dry-run       # compute, write nothing
    python -m src.regime.build_structural --compare-legacy  # R2.4 diff report
    python -m src.regime.build_structural --incremental   # scheduled mode, see below

Scheduled operation (``--incremental``)
---------------------------------------
The label for bar *t* depends on the whole series back to ``ANCHOR_DATE``, so there is no
such thing as computing "only the new bars" — the frame is always full history and that is
deliberate. What ``--incremental`` changes is the **write**: it compares the computed rows
against what is stored and upserts only those that are new or whose label, indicators,
source bar or labeller version actually differ.

Without it, an hourly schedule rewrites ~30,000 rows an hour to record the five bars a day
that carry new information, and stamps a fresh ``computed_at_utc`` across twenty years of
history every time — which destroys the one thing that column is for. ``rows_affected`` in
``fact_job_runs`` becomes meaningful for the same reason: on a normal day it is 0-5, and a
large number means a labeller change actually moved historical labels.

``--incremental`` also treats an active instrument that produced no labels as a FAILURE
rather than a logged warning. Under a schedule those are not the same thing: the table's
max ``bar_time_utc`` is taken across all instruments, so one pair that silently stopped
labelling leaves every freshness check green while its labels rot.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from psycopg2.extras import execute_values

from src.common.db import get_engine, get_psycopg2_connection
from src.regime import structural as S
from src.regime.structural_schema import CANONICAL_TABLE, ensure_tables

logger = logging.getLogger("system1.regime.build_structural")

#: Fixed anchor for "full history". NOT a rolling window: a frame that starts at
#: ``NOW() - N years`` begins on a different bar every day, and with a seeded recursion
#: that means the label for a fixed historical bar changes over time for no reason
#: connected to the market. Earliest D1 data in fact_market_prices is 2005.
ANCHOR_DATE = "2005-01-01"

#: Job name under which a scheduled run books itself into ``fact_job_runs``. Registered in
#: ``job_runs.EXPECTED_INTERVAL_HOURS`` so that a run that never happens is reported by
#: ``python -m src.monitoring.job_runs check`` — absence of a record is the alarm.
JOB_NAME = "structural_labels"

#: Relative tolerance for deciding an indicator value is unchanged. The labeller is
#: deterministic over identical input, so a genuine no-op re-run differs by 0.0; this only
#: absorbs float round-tripping through DOUBLE PRECISION.
_FLOAT_TOL = 1e-9


def load_full_history(pair: str, gran: str) -> Optional[pd.DataFrame]:
    """One instrument's complete history from the fixed anchor, sorted, tz-aware."""
    from sqlalchemy import text

    sql = text("""
        SELECT p."timestamp", p."Open", p.high, p.low, p."Close", p.volume
        FROM fact_market_prices p
        JOIN dim_asset a ON a.asset_id = p.asset_id
        WHERE a.symbol = :pair
          AND p.granularity = :gran
          AND p."timestamp" >= :anchor
        ORDER BY p."timestamp"
        """)
    with get_engine().connect() as conn:
        df = pd.read_sql(
            sql,
            conn,
            params={"pair": pair, "gran": gran, "anchor": ANCHOR_DATE},
        )
    if df.empty:
        return None
    df = df.rename(columns={"high": "High", "low": "Low", "volume": "Volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Duplicates would trip the labeller's guard, which is correct -- but a duplicate here
    # is an ingest defect, not a labeller input problem, so surface it distinctly.
    dupes = int(df["timestamp"].duplicated().sum())
    if dupes:
        raise ValueError(
            f"{pair} {gran} has {dupes} duplicate timestamps in "
            "fact_market_prices — fix ingest before labelling"
        )
    return df.set_index("timestamp")


def active_pairs() -> List[Tuple[int, str]]:
    from sqlalchemy import text

    with get_engine().connect() as conn:
        return [
            (int(r[0]), str(r[1]))
            for r in conn.execute(
                text(
                    "SELECT asset_id, symbol FROM dim_asset "
                    "WHERE is_active = true ORDER BY asset_id"
                )
            )
        ]


def _legacy_labels(d1: pd.DataFrame) -> pd.DataFrame:
    """The labeller EXACTLY as it behaved before R2.3, for the R2.4 comparison.

    Reproduced here rather than kept behind a flag in ``structural.py``: a second live code
    path is a maintenance liability, and this only needs to exist for one measurement. It
    is deliberately a verbatim copy of the old body, including
    ``pd.to_datetime(index, utc=True)`` and the unguarded, unsorted assumptions.
    """
    from src.layer0.data_access.indicators import adx as calc_adx, atr as calc_atr

    close, high, low = d1["Close"], d1["High"], d1["Low"]
    ema_fast = close.ewm(span=50, adjust=False).mean()
    ema_slow = close.ewm(span=200, adjust=False).mean()
    adx = calc_adx(high, low, close, period=14)
    atr = calc_atr(high, low, close, period=14)
    atr_pct = atr / close
    roll_mean = atr_pct.rolling(
        252, min_periods=252
    ).mean()
    roll_std = atr_pct.rolling(
        252, min_periods=252
    ).std(ddof=0)
    roll_std = roll_std.replace(0, np.nan)
    vol_z = (atr_pct - roll_mean) / roll_std

    label = pd.Series(S.UNKNOWN, index=d1.index, dtype="object")
    label[(adx > S.ADX_TREND_THRESHOLD) & (ema_fast > ema_slow)] = "Trending-Up"
    label[(adx > S.ADX_TREND_THRESHOLD) & (ema_fast <= ema_slow)] = "Trending-Down"
    label[(adx <= S.ADX_TREND_THRESHOLD) & (vol_z > 0)] = "High-Vol"
    label[(adx <= S.ADX_TREND_THRESHOLD) & (vol_z <= 0)] = "Ranging"
    label.iloc[: 252] = S.UNKNOWN
    shifted = label.shift(1).fillna(S.UNKNOWN)
    return pd.DataFrame(
        {
            "bar_time": pd.to_datetime(d1.index, utc=True),
            "regime": shifted.to_numpy(),
        }
    ).reset_index(drop=True)


UPSERT = f"""
INSERT INTO {{CANONICAL_TABLE}}
    (asset_id, granularity, bar_time_utc, regime, source_bar_time_utc,
     adx, ema_fast, ema_slow, atr_pct, vol_zscore, labeller_version, computed_at_utc)
VALUES %s
ON CONFLICT (asset_id, granularity, bar_time_utc) DO UPDATE SET
    regime = EXCLUDED.regime,
    source_bar_time_utc = EXCLUDED.source_bar_time_utc,
    adx = EXCLUDED.adx,
    ema_fast = EXCLUDED.ema_fast,
    ema_slow = EXCLUDED.ema_slow,
    atr_pct = EXCLUDED.atr_pct,
    vol_zscore = EXCLUDED.vol_zscore,
    labeller_version = EXCLUDED.labeller_version,
    computed_at_utc = EXCLUDED.computed_at_utc
"""


def _opt(v: Any) -> Optional[float]:
    if v is None:
        return None
    f = float(v)
    return f if np.isfinite(f) else None


def _utc(ts: Any) -> Optional[pd.Timestamp]:
    """Any timestamp-ish value as tz-aware UTC, or None. Naive input is *localised*, never
    relabelled — the same distinction that made ``tz_convert`` the fix in R2.3(c)."""
    if ts is None:
        return None
    t = pd.Timestamp(ts)
    if pd.isna(t):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _same_float(new: Any, stored: Any) -> bool:
    a, b = _opt(new), (None if stored is None else _opt(stored))
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= _FLOAT_TOL * max(1.0, abs(a), abs(b))


def existing_labels(asset_id: int, gran: str) -> Dict[pd.Timestamp, Tuple[Any, ...]]:
    """Stored label + indicators per bar for one instrument, keyed by UTC bar time."""
    from sqlalchemy import text

    sql = text(
        f"""
        SELECT bar_time_utc, regime, source_bar_time_utc, adx, ema_fast, ema_slow,
               atr_pct, vol_zscore, labeller_version
        FROM {CANONICAL_TABLE}
        WHERE asset_id = :aid AND granularity = :gran
        """
    )
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"aid": asset_id, "gran": gran}).fetchall()
    return {_utc(r[0]): tuple(r) for r in rows}


def _unchanged(new_row: Any, stored: Optional[Tuple[Any, ...]]) -> bool:
    """True when the stored row already says exactly what this run computed.

    Compares the label, its provenance (source bar, labeller version) AND every indicator.
    Comparing only the label would let a price revision that moved the indicators but not
    the verdict go unwritten, leaving the audit values in the table describing a bar that
    no longer exists — and the whole point of storing them is that a label can be disputed.
    """
    if stored is None:
        return False
    _bt, regime, src, adx, ema_f, ema_s, atr_p, vol_z, version = stored
    if str(new_row.regime) != str(regime):
        return False
    if S.LABELLER_VERSION != str(version):
        return False
    if _utc(new_row.source_bar_time) != _utc(src):
        return False
    return all(
        _same_float(n, s)
        for n, s in (
            (new_row.adx, adx),
            (new_row.ema_fast, ema_f),
            (new_row.ema_slow, ema_s),
            (new_row.atr_pct, atr_p),
            (new_row.vol_zscore, vol_z),
        )
    )


def changed_rows(asset_id: int, gran: str, labels: pd.DataFrame) -> pd.DataFrame:
    """The subset of ``labels`` that differs from what is already stored."""
    stored = existing_labels(asset_id, gran)
    keep = [
        not _unchanged(r, stored.get(_utc(r.bar_time)))
        for r in labels.itertuples(index=False)
    ]
    return labels[pd.Series(keep, index=labels.index)]


def write_labels(asset_id: int, gran: str, labels: pd.DataFrame) -> int:
    now = datetime.now(timezone.utc)
    rows = [
        (
            asset_id,
            gran,
            r.bar_time.to_pydatetime(),
            str(r.regime),
            (
                r.source_bar_time.to_pydatetime()
                if pd.notna(r.source_bar_time)
                else None
            ),
            _opt(r.adx),
            _opt(r.ema_fast),
            _opt(r.ema_slow),
            _opt(r.atr_pct),
            _opt(r.vol_zscore),
            S.LABELLER_VERSION,
            now,
        )
        for r in labels.itertuples(index=False)
    ]
    conn = get_psycopg2_connection()
    try:
        cur = conn.cursor()
        execute_values(cur, UPSERT.format(CANONICAL_TABLE=CANONICAL_TABLE), rows, page_size=5000)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def run(
    dry_run: bool = False,
    compare_legacy: bool = False,
    incremental: bool = False,
    granularities: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not granularities:
        granularities = ["D1"]
    ensure_tables()
    pairs = active_pairs()
    logger.info("Labelling %d instruments from anchor %s", len(pairs), ANCHOR_DATE)

    summary: Dict[str, Any] = {
        "anchor": ANCHOR_DATE,
        "labeller_version": S.LABELLER_VERSION,
        "incremental": incremental,
        "granularities": granularities,
        "instruments": {},
        "written": 0,
    }
    diffs: List[pd.DataFrame] = []
    no_history: List[str] = []

    for gran in granularities:
        logger.info(f"Processing granularity: {gran}")
        for asset_id, pair in pairs:
            d1 = load_full_history(pair, gran)
            if d1 is None or d1.empty:
                logger.warning("%s: no %s history", pair, gran)
                no_history.append(f"{pair} ({gran})")
                continue

            new = S.build_structural_labels(d1, return_indicators=True, granularity=gran)
            info: Dict[str, Any] = {
                "granularity": gran,
                "bars": int(len(new)),
                "first_bar": str(new["bar_time"].iloc[0]),
                "last_bar": str(new["bar_time"].iloc[-1]),
                "coverage": S.regime_coverage(new),
            }

            if compare_legacy and gran == "D1":
                old = _legacy_labels(d1)
                d = pd.DataFrame(
                    {
                        "instrument": pair,
                        "position": np.arange(len(new)),
                        "bar_time": new["bar_time"].to_numpy(),
                        "old": old["regime"].to_numpy(),
                        "new": new["regime"].to_numpy(),
                    }
                )
                d["changed"] = d["old"] != d["new"]
                diffs.append(d)
                info["changed"] = int(d["changed"].sum())
                info["changed_pct"] = round(100.0 * d["changed"].mean(), 4)

            to_write = changed_rows(asset_id, gran, new) if incremental else new
            info["rows_to_write"] = int(len(to_write))
            if incremental and len(to_write):
                info["oldest_rewritten"] = str(to_write["bar_time"].iloc[0])

            if not dry_run and len(to_write):
                summary["written"] += write_labels(asset_id, gran, to_write)

            if pair not in summary["instruments"]:
                summary["instruments"][pair] = []
            summary["instruments"][pair].append(info)
            logger.info(
                "%s (%s): %d bars, %d to write%s",
                pair,
                gran,
                len(new),
                len(to_write),
                f", {info.get('changed', 0)} changed vs legacy" if compare_legacy and gran == "D1" else "",
            )

    # An active instrument that produced nothing is a defect, but only a SCHEDULED run can
    # act on that knowledge, and only if it is loud. Left as a warning it is invisible:
    # the freshness contract reads max(bar_time_utc) across all instruments, so four
    # healthy pairs keep the check green while the fifth silently stops being labelled.
    # Manual backfills keep the old warn-and-continue behaviour — a partially-populated DB
    # is a normal state to backfill *into*, and failing there would be unhelpful.
    if incremental and no_history:
        raise RuntimeError(
            f"active instruments with no history: {', '.join(no_history)} — "
            "refusing to report success on a partial labelling run"
        )

    if compare_legacy and diffs:
        summary["diff"] = _diff_report(pd.concat(diffs, ignore_index=True))
    return summary


def _diff_report(d: pd.DataFrame) -> Dict[str, Any]:
    """R2.4's required breakdown: totals, transitions, and by bar position."""
    total = int(len(d))
    changed = int(d["changed"].sum())

    def bucket(pos: int) -> str:
        if pos < 253:
            return "0-252 (warm-up)"
        if pos <= 400:
            return "253-400"
        if pos <= 600:
            return "401-600"
        return "601+"

    d = d.copy()
    d["bucket"] = d["position"].map(bucket)

    by_bucket = {}
    for name, g in d.groupby("bucket"):
        by_bucket[name] = {
            "bars": int(len(g)),
            "changed": int(g["changed"].sum()),
            "changed_pct": round(100.0 * g["changed"].mean(), 4),
        }

    ch = d[d["changed"]]
    transitions = (
        ch.groupby(["old", "new"])
        .size()
        .sort_values(ascending=False)
        .head(20)
        .to_dict()
    )

    by_instrument = {}
    for name, g in d.groupby("instrument"):
        by_instrument[str(name)] = {
            "bars": int(len(g)),
            "changed": int(g["changed"].sum()),
            "changed_pct": round(100.0 * g["changed"].mean(), 4),
            "past_600_changed_pct": (
                round(100.0 * g[g["position"] > 600]["changed"].mean(), 4)
                if (g["position"] > 600).any()
                else 0.0
            ),
        }

    past600 = d[d["position"] > 600]
    return {
        "total_bars": total,
        "changed": changed,
        "changed_pct": round(100.0 * changed / total, 4) if total else 0.0,
        "by_position_bucket": by_bucket,
        "transitions_old_to_new": {
            f"{k[0]} -> {k[1]}": int(v) for k, v in transitions.items()
        },
        "by_instrument": by_instrument,
        "past_600_changed_pct": (
            round(100.0 * past600["changed"].mean(), 4) if len(past600) else 0.0
        ),
        "TOLERANCE_past_600_pct": 5.0,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="R2.3/R2.4 canonical structural labeller")
    p.add_argument("--dry-run", action="store_true", help="compute, write nothing")
    p.add_argument(
        "--compare-legacy",
        action="store_true",
        help="also compute pre-R2.3 labels and report the diff",
    )
    p.add_argument(
        "--incremental",
        action="store_true",
        help="scheduled mode: write only new/changed rows, fail on a silent partial run",
    )
    p.add_argument("--granularity", choices=["D1", "H4", "H1"], help="Granularity to label")
    p.add_argument("--all", action="store_true", help="Label all traded granularities (D1, H4, H1)")
    p.add_argument("--out", default=None, help="write the summary JSON here")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    granularities = []
    if args.all:
        granularities = ["D1", "H4", "H1"]
    elif args.granularity:
        granularities = [args.granularity]
    else:
        granularities = ["D1"]

    # A dry run is deliberately NOT booked. Recording it would let someone verifying by
    # hand paper over the absence of the real scheduled run, which is the one thing
    # fact_job_runs exists to detect.
    if args.dry_run:
        summary = run(dry_run=True, compare_legacy=args.compare_legacy, granularities=granularities)
    else:
        from src.monitoring.job_runs import record_job

        with record_job(JOB_NAME) as job:
            summary = run(
                dry_run=False,
                compare_legacy=args.compare_legacy,
                incremental=args.incremental,
                granularities=granularities,
            )
            job.rows_affected = int(summary["written"])
            job.detail = f"incremental={args.incremental} anchor={ANCHOR_DATE} granularities={granularities}"

    text = json.dumps(summary, indent=2, default=str)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
