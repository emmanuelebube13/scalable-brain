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

GRANULARITY = "D1"


def load_full_history(pair: str) -> Optional[pd.DataFrame]:
    """One instrument's complete D1 history from the fixed anchor, sorted, tz-aware."""
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
            params={"pair": pair, "gran": GRANULARITY, "anchor": ANCHOR_DATE},
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
            f"{pair} {GRANULARITY} has {dupes} duplicate timestamps in "
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
        S.VOL_ZSCORE_WINDOW, min_periods=S.VOL_ZSCORE_WINDOW
    ).mean()
    roll_std = atr_pct.rolling(
        S.VOL_ZSCORE_WINDOW, min_periods=S.VOL_ZSCORE_WINDOW
    ).std(ddof=0)
    roll_std = roll_std.replace(0, np.nan)
    vol_z = (atr_pct - roll_mean) / roll_std

    label = pd.Series(S.UNKNOWN, index=d1.index, dtype="object")
    label[(adx > S.ADX_TREND_THRESHOLD) & (ema_fast > ema_slow)] = "Trending-Up"
    label[(adx > S.ADX_TREND_THRESHOLD) & (ema_fast <= ema_slow)] = "Trending-Down"
    label[(adx <= S.ADX_TREND_THRESHOLD) & (vol_z > 0)] = "High-Vol"
    label[(adx <= S.ADX_TREND_THRESHOLD) & (vol_z <= 0)] = "Ranging"
    label.iloc[: S.VOL_ZSCORE_WINDOW] = S.UNKNOWN
    shifted = label.shift(1).fillna(S.UNKNOWN)
    return pd.DataFrame(
        {
            "bar_time": pd.to_datetime(d1.index, utc=True),
            "regime": shifted.to_numpy(),
        }
    ).reset_index(drop=True)


UPSERT = f"""
INSERT INTO {CANONICAL_TABLE}
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


def write_labels(asset_id: int, labels: pd.DataFrame) -> int:
    now = datetime.now(timezone.utc)
    rows = [
        (
            asset_id,
            GRANULARITY,
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
        execute_values(cur, UPSERT, rows, page_size=5000)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def run(dry_run: bool = False, compare_legacy: bool = False) -> Dict[str, Any]:
    ensure_tables()
    pairs = active_pairs()
    logger.info("Labelling %d instruments from anchor %s", len(pairs), ANCHOR_DATE)

    summary: Dict[str, Any] = {
        "anchor": ANCHOR_DATE,
        "labeller_version": S.LABELLER_VERSION,
        "instruments": {},
        "written": 0,
    }
    diffs: List[pd.DataFrame] = []

    for asset_id, pair in pairs:
        d1 = load_full_history(pair)
        if d1 is None or d1.empty:
            logger.warning("%s: no D1 history", pair)
            continue

        new = S.build_structural_labels(d1, return_indicators=True)
        info: Dict[str, Any] = {
            "bars": int(len(new)),
            "first_bar": str(new["bar_time"].iloc[0]),
            "last_bar": str(new["bar_time"].iloc[-1]),
            "coverage": S.regime_coverage(new),
        }

        if compare_legacy:
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

        if not dry_run:
            summary["written"] += write_labels(asset_id, new)

        summary["instruments"][pair] = info
        logger.info(
            "%s: %d bars%s",
            pair,
            len(new),
            f", {info['changed']} changed" if compare_legacy else "",
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
    p.add_argument("--out", default=None, help="write the summary JSON here")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    summary = run(dry_run=args.dry_run, compare_legacy=args.compare_legacy)
    text = json.dumps(summary, indent=2, default=str)
    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
