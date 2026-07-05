"""MODEL-001 — Multi-timeframe OANDA ingestion orchestrator (D1 / H4 / W1).

Reuses the proven primitives in ``src/layer0/ingest_oanda_prices.py`` (OANDA client,
paged fetch with exponential backoff, RFC3339 parsing, resume-from-MAX cursor) and adds
the MODEL-001 contract on top:

  * lineage on every row (source / ingest_run_id / ingested_at_utc / complete),
  * pre-commit DQ checks with quarantine (rows are never silently dropped),
  * FX-calendar-aware gap detection + per-run DQ/gap report,
  * per-run lineage manifest + resumable cursor state.

Idempotent: re-running produces zero duplicate bars (``INSERT … ON CONFLICT`` on the
natural key ``(asset_id, granularity, "timestamp")``).

Usage:
    python -m src.system1.ingestion.multi_timeframe_ingest --granularity W1
    python -m src.system1.ingestion.multi_timeframe_ingest --symbol EUR_USD --granularity W1
    python -m src.system1.ingestion.multi_timeframe_ingest --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import execute_values

from src.layer0.ingest_oanda_prices import (
    CONFIG,
    create_oanda_client,
    fetch_candles_with_retry,
    get_assets,
    get_db_connection,
    get_interval_delta,
    get_resume_timestamp,
    parse_rfc3339_to_datetime,
    read_env,
)
from src.system1.ingestion import dq, reports, schema

logger = logging.getLogger("system1.ingestion.multi_timeframe")

# Canonical System-1 modeling granularities (additive over legacy H1/H4).
DEFAULT_GRANULARITIES = ["D1", "H4", "W1"]
SOURCE = "OANDA"

# Per-instrument earliest-history overrides (OANDA practice depth varies). Forex majors
# generally reach back to ~2005; override here if a pair starts later. Documented in
# the manifest. Default backfill start is CONFIG.DEFAULT_START_DATE.
HISTORY_START_OVERRIDE: Dict[str, str] = {}


def _as_utc(dt: datetime) -> datetime:
    """Return a tz-aware UTC datetime (layer-0 cursors are naive UTC)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _normalize_candle(c: dict, asset_id: int, granularity: str) -> Optional[dq.Bar]:
    """OANDA candle -> normalized bar dict. Returns None if unparseable/incomplete."""
    if not c.get("complete", False):
        return None
    t = parse_rfc3339_to_datetime(c.get("time", ""))
    if t is None:
        return None
    mid = c.get("mid") or {}
    try:
        bar: dq.Bar = {
            "asset_id": asset_id,
            "granularity": granularity,
            "bar_time_utc": _as_utc(t),
            "open": float(mid["o"]),
            "high": float(mid["h"]),
            "low": float(mid["l"]),
            "close": float(mid["c"]),
            "volume": int(c.get("volume", 0)),
            "complete": True,
        }
    except (KeyError, ValueError, TypeError):
        return None
    return bar


def upsert_bars_with_lineage(conn, bars: List[dq.Bar], run_id: str) -> Tuple[int, int]:
    """Idempotent upsert of clean bars into fact_market_prices, with lineage columns."""
    if not bars:
        return 0, 0
    now = datetime.now(timezone.utc)
    rows = [
        (
            b["asset_id"],
            b["bar_time_utc"],
            b["open"],
            b["high"],
            b["low"],
            b["close"],
            b["volume"],
            b["granularity"],
            True,
            SOURCE,
            run_id,
            now,
        )
        for b in bars
    ]
    sql = """
        INSERT INTO fact_market_prices
            (asset_id, "timestamp", "Open", high, low, "Close", volume, granularity,
             complete, source, ingest_run_id, ingested_at_utc)
        VALUES %s
        ON CONFLICT ("timestamp", asset_id, granularity) DO UPDATE SET
            "Open" = EXCLUDED."Open",
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            "Close" = EXCLUDED."Close",
            volume = EXCLUDED.volume,
            complete = EXCLUDED.complete,
            source = EXCLUDED.source,
            ingest_run_id = EXCLUDED.ingest_run_id,
            ingested_at_utc = EXCLUDED.ingested_at_utc
        RETURNING (xmax = 0) AS inserted
    """
    cur = conn.cursor()
    returned = execute_values(cur, sql, rows, page_size=1000, fetch=True)
    conn.commit()
    inserted = sum(1 for r in returned if r[0])
    return inserted, len(returned) - inserted


def write_quarantine(conn, quarantined: List[dq.Quarantined], run_id: str) -> int:
    """Persist DQ failures to fact_market_prices_quarantine."""
    if not quarantined:
        return 0
    rows = [
        (
            b["asset_id"],
            b["granularity"],
            b["bar_time_utc"],
            b["open"],
            b["high"],
            b["low"],
            b["close"],
            b["volume"],
            b.get("complete", True),
            SOURCE,
            run_id,
            reason,
            detail,
        )
        for (b, reason, detail) in quarantined
    ]
    sql = """
        INSERT INTO fact_market_prices_quarantine
            (asset_id, granularity, "timestamp", "Open", high, low, "Close", volume,
             complete, source, ingest_run_id, quarantine_reason_code, quarantine_detail)
        VALUES %s
    """
    cur = conn.cursor()
    execute_values(cur, sql, rows, page_size=1000)
    conn.commit()
    return len(rows)


def ingest_instrument_granularity(
    conn, client, asset: Dict[str, Any], granularity: str, run_id: str
) -> Dict[str, Any]:
    """Page through OANDA for one (instrument, granularity), DQ-check, upsert, report."""
    symbol = asset["Symbol"]
    asset_id = asset["Asset_ID"]
    interval = get_interval_delta(granularity)
    chunk_days = CONFIG.CHUNK_DAYS.get(granularity, 30)

    from_ts = _as_utc(get_resume_timestamp(conn, asset_id, granularity))
    override = HISTORY_START_OVERRIDE.get(symbol)
    if override:
        ov = _as_utc(datetime.fromisoformat(override))
        from_ts = max(from_ts, ov)
    now = datetime.now(timezone.utc)

    stats = {
        "instrument": symbol,
        "granularity": granularity,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_quarantined": 0,
        "candles_fetched": 0,
        "api_requests": 0,
        "failed_windows": 0,
        "start_cursor": from_ts.isoformat(),
        "quarantine_reason_counts": {},
        "history_start_override": override,
    }
    all_clean: List[dq.Bar] = []

    if from_ts >= now - interval:
        logger.info("%s %s already up to date (cursor %s)", symbol, granularity, from_ts)
        stats["end_cursor"] = from_ts.isoformat()
        return stats

    last_bar: Optional[datetime] = None

    while from_ts < now:
        to_ts = min(from_ts + timedelta(days=chunk_days), now)
        candles, success, attempts = fetch_candles_with_retry(
            client, symbol, granularity, from_ts, to_ts
        )
        stats["api_requests"] += attempts
        if not success:
            logger.error("Failed window %s %s %s→%s", symbol, granularity, from_ts, to_ts)
            stats["failed_windows"] += 1
            from_ts = to_ts
            continue

        stats["candles_fetched"] += len(candles)
        bars = [
            nb
            for c in candles
            if (nb := _normalize_candle(c, asset_id, granularity)) is not None
        ]
        if bars:
            ok, quarantined = dq.run_dq_checks(bars)
            ins, upd = upsert_bars_with_lineage(conn, ok, run_id)
            qn = write_quarantine(conn, quarantined, run_id)
            stats["rows_inserted"] += ins
            stats["rows_updated"] += upd
            stats["rows_quarantined"] += qn
            for (_, reason, _) in quarantined:
                stats["quarantine_reason_counts"][reason] = (
                    stats["quarantine_reason_counts"].get(reason, 0) + 1
                )
            all_clean.extend(ok)
            last_bar = max(b["bar_time_utc"] for b in bars)
            from_ts = last_bar + interval
        else:
            from_ts = to_ts
        time.sleep(CONFIG.REQUEST_SLEEP_SECONDS)

    # Gap detection over everything ingested this run for this series.
    stats["gap_report"] = dq.detect_gaps(all_clean, granularity, interval)
    stats["end_cursor"] = (last_bar or from_ts).isoformat()

    reports.update_cursor(
        symbol, granularity, last_bar, backfill_complete=True,
        history_start_override=override,
    )
    logger.info(
        "%s %s done: +%d ins, %d upd, %d quarantined, %d unexpected gaps",
        symbol, granularity, stats["rows_inserted"], stats["rows_updated"],
        stats["rows_quarantined"], stats["gap_report"]["unexpected_gaps"],
    )
    return stats


def run(
    symbol_filter: Optional[str] = None,
    granularity_filter: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    granularities = (
        [granularity_filter] if granularity_filter else list(DEFAULT_GRANULARITIES)
    )
    logger.info("MODEL-001 ingest run %s | granularities=%s | dry_run=%s",
                run_id, granularities, dry_run)

    env = read_env()

    # Additive, idempotent schema migration before any write.
    migration = schema.migrate()
    logger.info("Schema migration: %s", migration)

    conn = get_db_connection(env)
    try:
        assets = get_assets(conn, symbol_filter)
    except Exception:
        conn.close()
        raise

    if dry_run:
        conn.close()
        create_oanda_client(env)  # validate creds
        result = {
            "status": "dry_run_success",
            "ingest_run_id": run_id,
            "assets": [a["Symbol"] for a in assets],
            "granularities": granularities,
            "migration": migration,
        }
        logger.info("Dry run OK: %d assets x %d granularities", len(assets), len(granularities))
        return result

    client = create_oanda_client(env)
    per_series: List[Dict[str, Any]] = []
    try:
        for asset in assets:
            for g in granularities:
                per_series.append(
                    ingest_instrument_granularity(conn, client, asset, g, run_id)
                )
    finally:
        conn.close()

    ended = datetime.now(timezone.utc)
    totals = {
        "rows_inserted": sum(s["rows_inserted"] for s in per_series),
        "rows_updated": sum(s["rows_updated"] for s in per_series),
        "rows_quarantined": sum(s["rows_quarantined"] for s in per_series),
        "candles_fetched": sum(s["candles_fetched"] for s in per_series),
        "api_requests": sum(s["api_requests"] for s in per_series),
        "failed_windows": sum(s["failed_windows"] for s in per_series),
    }

    manifest = {
        "ingest_run_id": run_id,
        "started_utc": started.isoformat(),
        "ended_utc": ended.isoformat(),
        "duration_seconds": (ended - started).total_seconds(),
        "instruments": [a["Symbol"] for a in assets],
        "granularities": granularities,
        "source": SOURCE,
        "migration": migration,
        "totals": totals,
        "per_series": [
            {k: v for k, v in s.items() if k != "gap_report"} for s in per_series
        ],
    }
    manifest_path = reports.write_manifest(manifest)

    dq_report = {
        "ingest_run_id": run_id,
        "generated_utc": ended.isoformat(),
        "totals": {
            "rows_quarantined": totals["rows_quarantined"],
            "failed_windows": totals["failed_windows"],
        },
        "quarantine_reason_counts": _merge_reason_counts(per_series),
        "gap_reports": [
            {
                "instrument": s["instrument"],
                "granularity": s["granularity"],
                **s.get("gap_report", {}),
            }
            for s in per_series
        ],
        "max_missing_expected_bar_ratio": max(
            (s.get("gap_report", {}).get("missing_expected_bar_ratio", 0.0) for s in per_series),
            default=0.0,
        ),
    }
    dq_path = reports.write_dq_gap_report(dq_report)

    summary = {
        "status": "completed",
        "ingest_run_id": run_id,
        "totals": totals,
        "manifest": manifest_path,
        "dq_gap_report": dq_path,
        "max_missing_expected_bar_ratio": dq_report["max_missing_expected_bar_ratio"],
    }
    logger.info("MODEL-001 run %s complete: %s", run_id, summary)
    return summary


def _merge_reason_counts(per_series: List[Dict[str, Any]]) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for s in per_series:
        for reason, n in s.get("quarantine_reason_counts", {}).items():
            merged[reason] = merged.get(reason, 0) + n
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-001 multi-timeframe OANDA ingestion")
    parser.add_argument("--symbol", default=None, help="Single instrument, e.g. EUR_USD")
    parser.add_argument(
        "--granularity", choices=["D1", "H4", "W1", "H1"], default=None,
        help="Single granularity (default: D1, H4, W1)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without ingesting")
    parser.add_argument("--log-file", default="model001_ingest.log")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(args.log_file)],
    )
    try:
        summary = run(args.symbol, args.granularity, args.dry_run)
        print(summary)
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        logger.error("Fatal: %s", e, exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
