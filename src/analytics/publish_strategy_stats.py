"""D6 — publish per-strategy risk statistics for System 3.

Writes a SELF-CONTAINED document (not a pointer) to a fixed key:

    risk/strategy_stats/latest.json

    {
      "produced_at": "<iso8601>",
      "checksum":    "<sha256 over the strategies map only>",
      "strategies": {"<id>": {"win_rate", "avg_win", "avg_loss", "expectancy"}}
    }

``checksum`` is ``sha256(json.dumps(strategies, sort_keys=True, separators=(",",":")))``
— over the ``strategies`` map ONLY, so it is invariant to how the enclosing document is
formatted. System 3 recomputes it from the parsed map and rejects on mismatch. This was
verified against the pre-existing hand-seeded object, whose checksum this recipe
reproduces exactly.

Publish ordering (the MODEL-007 contract, applied to a content document):

  1. compute the checksum + the artifact's SHA256 locally
  2. upload to an immutable versioned key ``risk/strategy_stats/<version>/strategy_stats.json``
  3. round-trip verify that uploaded object's SHA256 against the local value
  4. **only then** write the live ``latest.json``
  5. on ANY mismatch: delete the partial version, abort, and leave the previous
     ``latest.json`` byte-for-byte untouched

The upload-then-verify step cannot be performed against ``latest.json`` itself: writing
to the live key IS going live, so a post-hoc verification there would already have exposed
consumers to a corrupt document. Staging to a versioned key first is what makes
"abort and leave the previous latest.json untouched" achievable at all. The versioned
copies also give System 3 a rollback target.

UNITS — read before changing anything here
------------------------------------------
Values are **R-multiples** (profit/loss as a multiple of the amount risked), because
``fact_trade_outcomes.r_multiple`` is the only P/L representation System 1 stores; there
is no currency or pip column in the schema. ``avg_win`` is therefore ~1.0, not ~40.

The hand-seeded paper prior this replaced used a currency/pip scale
(``avg_win: 40.0, avg_loss: 30.0``). Anything downstream that multiplies these values by
a position size will behave ~40x differently against R-multiples. Converting R to
currency requires account equity and risk-per-trade, both of which are System 3's to own
(System 1 emits weights and R, never sizes) — so the conversion belongs there, not here.
``unit`` is stamped in the document so a consumer can assert on it rather than assume.

``avg_loss`` is a POSITIVE magnitude, matching the seed's convention and preserving the
identity ``expectancy == win_rate*avg_win - (1-win_rate)*avg_loss``.

Usage:
    python -m src.analytics.publish_strategy_stats --dry-run   # print, no writes
    python -m src.analytics.publish_strategy_stats             # publish
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.common.db import get_engine
from src.common.storage import build_storage

logger = logging.getLogger("system1.strategy_stats")

SCHEMA_VERSION = "1"
REMOTE_ROOT = "risk/strategy_stats"
POINTER_KEY = f"{REMOTE_ROOT}/latest.json"
ARTIFACT_NAME = "strategy_stats.json"
UNIT = "r_multiple"
# Gate metrics are OOS-only everywhere else in System 1 (Axiom 1: only out-of-sample
# survival is evidence). Risk parameters feeding System 3 are held to the same standard —
# in-sample stats would overstate the edge System 3 sizes against.
OOS_ONLY = True
MIN_TRADES = 1
# Same sentinel MODEL-004 uses, so an unresolvable cell reads identically in both places.
UNKNOWN_REGIME = "UNKNOWN"

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAGING_DIR = os.path.join(_REPO_ROOT, "results", "state", "strategy_stats_staging")


class StrategyStatsRefused(Exception):
    """Raised when the document cannot be produced or verified (never publishes)."""


def canonical_checksum(strategies: Dict[str, Dict[str, float]]) -> str:
    """``sha256`` over the strategies map in canonical JSON — the System 3 contract.

    Canonical form is ``sort_keys=True, separators=(",",":")``: no whitespace, stable key
    order. Computing it over the map ALONE (not the whole document) is what lets the
    enclosing file be pretty-printed, re-serialized, or gain metadata keys without
    invalidating the integrity check.
    """
    blob = json.dumps(strategies, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_trades(engine) -> pd.DataFrame:
    sql = "SELECT strategy_id, is_winner, r_multiple, is_oos FROM fact_trade_outcomes"
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["is_oos"] = df["is_oos"].fillna(False).astype(bool)
    return df


def _cell_key(regime: str, strategy_id: Any, granularity: str) -> str:
    """The lookup key System 3 builds from a live signal's own fields.

    A ScoredSignal carries ``regime``, ``strategy_id`` and ``granularity``, so the key is
    assembled from exactly those three and nothing else. Pipe-separated because none of
    the three can contain a pipe (regimes are a fixed vocabulary, ids are integers,
    granularities are an enum), which keeps the key reversible by a plain split.
    """
    return f"{regime}|{int(strategy_id)}|{granularity}"


def compute_cell_stats(tagged: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Per (regime x strategy x granularity) risk stats, same shape as ``compute_stats``.

    This is the dimension System 3 was missing. The flat per-strategy map answers "what
    is strategy 43's edge overall"; it cannot answer "what is strategy 43's edge *in
    Trending-Down*", which is the only question that matters when the live map routes by
    regime. Every lookup System 3 could not satisfy became "unmeasured".

    ``trade_count`` is included deliberately. Without it a consumer cannot distinguish
    "no measurement exists for this cell" from "a measurement exists but rests on five
    trades" — and those warrant very different sizing. It is reported, never gated on
    here: System 1 publishes the measurement, System 3 decides what is enough.

    The regime label comes from ``attribution.tag_regime_at_entry``, i.e. the SAME
    point-in-time causal join MODEL-004 uses. Recomputing it here with a second
    implementation is how train/serve skew gets reintroduced quietly.
    """
    out: Dict[str, Dict[str, float]] = {}
    for (regime, sid, gran), g in tagged.groupby(
        ["regime", "strategy_id", "granularity"]
    ):
        r = g["r_multiple"].to_numpy(dtype="float64")
        r = r[np.isfinite(r)]
        if len(r) < MIN_TRADES:
            continue
        wins, losses = r[r > 0], r[r < 0]
        out[_cell_key(str(regime), sid, str(gran))] = {
            "win_rate": round(float(g["is_winner"].mean()), 6),
            "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 6),
            "avg_loss": round(float(abs(losses.mean())) if len(losses) else 0.0, 6),
            "expectancy": round(float(r.mean()), 6),
            "trade_count": int(len(r)),
        }
    return out


def tag_structural_regime_at_entry(trades: pd.DataFrame, engine) -> pd.DataFrame:
    """Point-in-time STRUCTURAL regime per trade (label bar <= entry_time).

    Structural, not causal, and the distinction decides whether this document is usable
    at all.

    ``attribution.tag_regime_at_entry`` joins on ``fact_market_regime_v2.regime_causal``,
    which is written only for bars inside a completed walk-forward fold. Measured here,
    that leaves 72% of trades (46,833 of 64,856) tagged UNKNOWN — so a per-cell map built
    on it answers almost nothing.

    More decisively: a live ScoredSignal's ``regime`` field is the STRUCTURAL label. It
    comes from ``signals.run.get_current_regimes`` -> ``regime.structural`` and never from
    ``regime_causal`` (which is NULL on the newest bars — that is FIX-S1-016). A cell keyed
    by causal regime could therefore never be found by a consumer looking up the regime the
    signal actually carries. Keying the history by the same label that routes the live
    signal is what makes the lookup mean anything.

    The label is built on D1 closes per instrument and applied to trades of every
    granularity, exactly as the live path applies one D1-derived label per instrument to
    its H1/H4/D1 signals.
    """
    from src.layer0.strategies.research_data import load_ohlcv_readonly
    from src.regime.structural import build_structural_labels

    symbols = pd.read_sql(text("SELECT asset_id, symbol FROM dim_asset"), engine)
    sym_by_id = dict(zip(symbols["asset_id"], symbols["symbol"]))

    parts = []
    for aid, ta in trades.groupby("asset_id"):
        symbol = sym_by_id.get(aid)
        labels = None
        if symbol:
            try:
                d1 = load_ohlcv_readonly(symbol, "D1", lookback_years=25)
                if d1 is not None and not d1.empty:
                    labels = build_structural_labels(d1)
            except Exception as e:  # a single bad instrument must not sink the document
                logger.warning("structural labels unavailable for %s: %s", symbol, e)
        if labels is None or labels.empty:
            parts.append(ta.assign(regime=UNKNOWN_REGIME))
            continue
        lab = pd.DataFrame(
            {
                "bar_time": pd.to_datetime(labels["bar_time"], utc=True),
                "regime_structural": labels["regime"].astype(str),
            }
        ).sort_values("bar_time")
        merged = pd.merge_asof(
            ta.sort_values("entry_time"),
            lab,
            left_on="entry_time",
            right_on="bar_time",
            direction="backward",
        )
        merged["regime"] = merged["regime_structural"].fillna(UNKNOWN_REGIME)
        parts.append(merged)
    return pd.concat(parts, ignore_index=True)


def build_cells(engine) -> Dict[str, Dict[str, float]]:
    """Load trades, tag each with the structural regime at entry, and reduce to cells."""
    # `_load_trades` is imported from attribution rather than reimplemented: it is
    # schema-aware about the FIX-S1-002 is_oos/fold_id columns, and a second copy of that
    # logic would drift. The regime JOIN is deliberately not reused — see
    # tag_structural_regime_at_entry for why causal is the wrong label here.
    from src.attribution.attribute import _load_trades as _load_trades_with_entry

    trades = _load_trades_with_entry(engine)
    if OOS_ONLY:
        trades = trades[trades["is_oos"]]
    if trades.empty:
        return {}
    tagged = tag_structural_regime_at_entry(trades, engine)
    known = int((tagged["regime"] != UNKNOWN_REGIME).sum())
    logger.info(
        "structural regime resolved for %d/%d trades (%.1f%%)",
        known,
        len(tagged),
        100.0 * known / max(len(tagged), 1),
    )
    return compute_cell_stats(tagged)


def compute_stats(trades: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Per-strategy {win_rate, avg_win, avg_loss, expectancy} in R-multiples.

    ``avg_win`` is the mean of positive R, ``avg_loss`` the mean ABSOLUTE value of
    negative R (positive magnitude). A strategy with no wins (or no losses) reports 0.0
    for that leg rather than NaN, so the document is always numerically valid JSON —
    NaN is not representable in JSON and would break System 3's parse.
    """
    out: Dict[str, Dict[str, float]] = {}
    for sid, g in trades.groupby("strategy_id"):
        r = g["r_multiple"].to_numpy(dtype="float64")
        r = r[np.isfinite(r)]
        if len(r) < MIN_TRADES:
            continue
        wins, losses = r[r > 0], r[r < 0]
        out[str(int(sid))] = {
            "win_rate": round(float(g["is_winner"].mean()), 6),
            "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 6),
            "avg_loss": round(float(abs(losses.mean())) if len(losses) else 0.0, 6),
            "expectancy": round(float(r.mean()), 6),
        }
    return out


def evidence_window(engine) -> Dict[str, Any]:
    """When the trades behind these stats stop, and when they were last written.

    ``produced_at`` is the moment this document was assembled — it says nothing about
    the age of the numbers inside it. This job runs daily; the outcomes writer did not
    run at all between 2026-08-16 and 2026-08-29. Across that fortnight every daily
    publication carried a fresh ``produced_at`` over frozen evidence, and System 3 had
    no field that would have let it notice.

    Reported, never gated on here: System 1 publishes the measurement, System 3 decides
    what is too old to size against. Absent rather than defaulted when unavailable — a
    fabricated freshness claim is worse than a missing one.
    """
    out: Dict[str, Any] = {}
    try:
        with engine.connect() as conn:
            latest = conn.execute(
                text('SELECT max("timestamp") FROM fact_trade_outcomes')
            ).scalar()
            written = conn.execute(
                text("SELECT max(created_at) FROM fact_trade_outcomes")
            ).scalar()
    except Exception as exc:  # noqa: BLE001 - provenance must not block the publish
        logger.warning("Could not derive the evidence window: %s", exc)
        return out
    now = datetime.now(timezone.utc)
    if latest is not None:
        out["data_through_utc"] = latest.isoformat()
        out["evidence_age_days"] = round((now - latest).total_seconds() / 86400.0, 2)
    if written is not None:
        out["outcomes_written_at_utc"] = written.isoformat()
    return out


def build_document(
    strategies: Dict[str, Dict[str, float]],
    cells: Optional[Dict[str, Dict[str, float]]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the published document. ``checksum`` covers ``strategies`` ONLY.

    That is deliberate and must stay true. System 3 already recomputes ``checksum`` over
    the parsed ``strategies`` map and rejects the document on mismatch. Folding ``cells``
    into the same checksum would invalidate every existing consumer the moment this
    version shipped — a silent, total outage of the risk document. ``cells`` therefore
    carries its own ``cells_checksum``, computed the same canonical way, so a consumer
    can verify it independently once it knows to look.

    Adding a key is safe for the same reason the docstring above gives: the checksum is
    over the map, not the enclosing document.
    """
    doc: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "produced_at": datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "source": "system1-model-004-trade-outcomes",
        # Outside the checksum by design (it covers `strategies` only), so adding these
        # cannot invalidate an existing consumer.
        **(evidence or {}),
        "unit": UNIT,
        "scope": "oos_only" if OOS_ONLY else "all_trades",
        "checksum": canonical_checksum(strategies),
        "strategies": strategies,
    }
    if cells is not None:
        doc["cells"] = cells
        doc["cells_checksum"] = canonical_checksum(cells)
        doc["cell_key_format"] = "<regime>|<strategy_id>|<granularity>"
    return doc


def build(engine=None) -> Dict[str, Any]:
    """Compute the document from the database (no writes)."""
    engine = engine or get_engine()
    trades = _load_trades(engine)
    n_all = len(trades)
    if OOS_ONLY:
        trades = trades[trades["is_oos"]]
    if trades.empty:
        raise StrategyStatsRefused(
            "no trades available to compute strategy stats — refusing to publish an "
            "empty risk document"
        )
    strategies = compute_stats(trades)
    if not strategies:
        raise StrategyStatsRefused("no strategy met MIN_TRADES — refusing empty map")

    # The per-cell map is an ADDITION, not a precondition. If the regime join fails or
    # the regime table is empty, the flat per-strategy document that System 3 already
    # depends on must still publish — degrading to the previous behaviour is far better
    # than withholding the risk document entirely.
    try:
        cells = build_cells(engine)
    except Exception as e:
        logger.error(
            "per-regime cell stats unavailable (%s) — publishing per-strategy map only",
            e,
        )
        cells = None

    logger.info(
        "computed stats for %d strategies and %s cells from %d/%d trades (%s)",
        len(strategies),
        len(cells) if cells is not None else "no",
        len(trades),
        n_all,
        "OOS only" if OOS_ONLY else "all trades",
    )
    evidence = evidence_window(engine)
    if evidence.get("evidence_age_days", 0) > 7:
        logger.warning(
            "publishing stats over evidence %.1f days old (trades stop %s) — the "
            "outcomes writer may be stalled; the document states its own age",
            evidence["evidence_age_days"],
            evidence.get("data_through_utc"),
        )
    return build_document(strategies, cells, evidence)


def publish(
    dry_run: bool = False, storage=None, staging_dir: str = STAGING_DIR
) -> Dict[str, Any]:
    """Publish the document under the verify-before-live contract (see module docstring)."""
    document = build()
    storage = storage or build_storage()

    os.makedirs(staging_dir, exist_ok=True)
    local_path = os.path.join(staging_dir, ARTIFACT_NAME)
    with open(local_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2, sort_keys=True)
    local_sha = _sha256_file(local_path)

    # Self-check: the checksum we are about to publish must validate the way System 3
    # will validate it. Catches any drift between build_document and the contract.
    if canonical_checksum(document["strategies"]) != document["checksum"]:
        raise StrategyStatsRefused("internal checksum self-check failed")

    if dry_run:
        logger.info("dry-run — nothing uploaded, live document untouched")
        return {**document, "published": False, "local_path": local_path}

    version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    remote_prefix = f"{REMOTE_ROOT}/{version}"
    versioned_key = f"{remote_prefix}/{ARTIFACT_NAME}"

    # 2. upload to the immutable versioned key -> 3. round-trip verify BEFORE going live.
    try:
        storage.put_object(versioned_key, local_path, encrypt=True)
        remote_sha = storage.sha256(versioned_key)
        if remote_sha != local_sha:
            raise StrategyStatsRefused(
                f"round-trip checksum mismatch on {versioned_key}: "
                f"local={local_sha} remote={remote_sha}"
            )
    except Exception:
        storage.delete_prefix(remote_prefix)  # no half-uploaded version survives
        logger.error(
            "upload/verify failed — aborted; live %s left untouched", POINTER_KEY
        )
        raise

    # 4. only now make it live. The document is written whole; ``checksum`` covers the
    # strategies map, so re-serialization by the backend cannot invalidate it.
    storage.atomic_pointer_update(POINTER_KEY, document)

    # 5. confirm what a consumer will actually read back.
    verified = _verify_live(storage, document["checksum"])
    logger.info(
        "published %s (version %s, %d strategies, live checksum verified=%s)",
        POINTER_KEY,
        version,
        len(document["strategies"]),
        verified,
    )
    return {
        **document,
        "published": True,
        "version": version,
        "versioned_key": versioned_key,
        "live_verified": verified,
    }


def _verify_live(storage, expected_checksum: str) -> bool:
    """Re-read the live document and recompute its checksum the way System 3 does."""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, ARTIFACT_NAME)
        storage.get_object(POINTER_KEY, p)
        with open(p, encoding="utf-8") as fh:
            live = json.load(fh)
    recomputed = canonical_checksum(live.get("strategies", {}))
    return bool(
        recomputed == expected_checksum and live.get("checksum") == expected_checksum
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="D6 — publish risk/strategy_stats")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print the document without uploading or going live.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    try:
        print(json.dumps(publish(dry_run=args.dry_run), indent=2))
    except StrategyStatsRefused as e:
        logger.error("STRATEGY STATS REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
