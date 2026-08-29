"""S1-EXPORT-003 — the instrument universe and its price coverage.

Why this exists
---------------
On 2026-08-23 the dashboard's Assets page rendered a full-width banner reading:

    System Idle — strategy payload unavailable
    The live regime→strategy map currently holds 0 qualified strategies.
    Asset telemetry and execution metrics are intentionally paused.

Three claims, none of them true. The map held six cells, three of them genuinely
qualified. Nothing was paused, by anyone, on purpose. And the page had reached that state
because a downstream ``/api/v1/assets`` route returned ``[]`` — an empty API response
narrated as a deliberate system posture.

The root confusion is worth stating plainly, because it is the thing this module exists to
make impossible:

    **An asset is not a strategy.** The instrument universe is a *dimension* — the five
    pairs System 1 ingests and models. It does not shrink when a strategy fails its gates,
    and it would be exactly the same list if zero strategies qualified forever.

Gating the asset list on strategy qualification couples two things that have no
relationship, and it produces the worst possible failure: a page that is confidently wrong
rather than merely empty. The earlier gray "no data" box was better, because it did not
make a claim.

So System 1 publishes the universe itself. It owns this data — it maintains ``dim_asset``
and runs the price ingest — and publishing it means no consumer has to seed its own copy
or infer the list from something unrelated.

What this is NOT
----------------
Not live market data. Bid/ask, spread, session state and open positions are System 2's —
it holds the broker connection. This is the *inventory*: what instruments exist, how much
history each has, how fresh that history is, and how each behaves in the regime model.
A consumer joins the two on ``symbol``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
from sqlalchemy import text

#: Granularities System 1 actually models. Everything else in ``fact_market_prices`` is
#: stored history that no feature, regime or strategy consumes — see ``modelled`` below.
#: Publishing the distinction stops a consumer inferring a capability from a row count:
#: M15 has half a million bars per pair and is used by nothing.
MODELLED_GRANULARITIES = ("D1", "H1", "H4")

#: A price series older than this is flagged. Generous on purpose — it is meant to catch a
#: dead feed, not a weekend. The forex week closes ~21:00 UTC Friday and reopens ~21:00
#: Sunday, so anything under ~72h is unremarkable.
STALE_AFTER_HOURS = 96.0


def load_price_coverage(engine) -> pd.DataFrame:
    """Rows, first bar and last bar per (asset, granularity) from ``fact_market_prices``."""
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                "SELECT asset_id, granularity, count(*) AS bars, "
                'min("timestamp") AS first_bar, max("timestamp") AS last_bar '
                "FROM fact_market_prices GROUP BY asset_id, granularity"
            ),
            conn,
        )


def load_asset_dim(engine) -> pd.DataFrame:
    """The instrument dimension. This is the universe — independent of everything else."""
    with engine.connect() as conn:
        return pd.read_sql(
            text(
                "SELECT asset_id, symbol, market_type, is_active FROM dim_asset "
                "ORDER BY asset_id"
            ),
            conn,
        )


def _iso(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return str(ts.tz_convert("UTC").isoformat())


def _age_hours(value: Any, now: datetime) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return round((now - ts.to_pydatetime()).total_seconds() / 3600.0, 1)


def map_reference_note(regime_map: Dict[str, Any]) -> Dict[str, Any]:
    """State, as data, whether the regime→strategy map references assets at all.

    It does not: its cells are keyed by (strategy × regime × granularity) and never name
    an instrument. That fact is the strongest available argument against gating an Assets
    page on the map, so it ships explicitly.

    Deliberately NOT an empty list of symbols. An empty array is precisely the shape a
    consumer misreads as "no assets" — which is the failure this module was written after.
    """
    cells = sum(len(v or []) for v in (regime_map.get("regimes") or {}).values())
    return {
        "map_references_assets": False,
        "map_cell_count": cells,
        "explanation": (
            "The regime→strategy map is keyed by (strategy × regime × granularity) and "
            "names no instrument, so it cannot tell you which assets exist or which are "
            "active. There is no join between it and this inventory. A qualified-strategy "
            "count of zero says nothing whatsoever about the asset universe."
        ),
    }


def build_asset_inventory(
    asset_dim: pd.DataFrame,
    coverage: pd.DataFrame,
    occupancy: pd.DataFrame,
    tagged: pd.DataFrame,
    regime_map: Dict[str, Any],
    generated_at: str,
    now: Optional[datetime] = None,
    modelled: Sequence[str] = MODELLED_GRANULARITIES,
) -> Dict[str, Any]:
    """Assemble the instrument universe with per-asset coverage, regimes and OOS stats.

    Pure: every argument is already-loaded data, so the shape is testable without a
    database. ``occupancy`` and ``tagged`` may be empty — an asset with no regime labels
    and no trades is still an asset, and still appears.
    """
    now = now or datetime.now(timezone.utc)
    modelled = tuple(modelled)
    assets: List[Dict[str, Any]] = []

    for row in asset_dim.to_dict("records"):
        aid = int(row["asset_id"])
        symbol = str(row["symbol"])

        cov = coverage[coverage["asset_id"] == aid] if len(coverage) else coverage
        grans: List[Dict[str, Any]] = []
        for c in cov.sort_values("granularity").to_dict("records"):
            age = _age_hours(c["last_bar"], now)
            gran = str(c["granularity"])
            grans.append(
                {
                    "granularity": gran,
                    "bars": int(c["bars"]),
                    "first_bar_utc": _iso(c["first_bar"]),
                    "last_bar_utc": _iso(c["last_bar"]),
                    "age_hours": age,
                    "stale": None if age is None else age > STALE_AFTER_HOURS,
                    # The load-bearing flag: bars exist for M15/M30/W1 and nothing in
                    # System 1 reads them. Row count is not evidence of use.
                    "modelled": gran in modelled,
                }
            )

        occ = occupancy[occupancy["asset_id"] == aid] if len(occupancy) else occupancy
        regimes: Dict[str, Dict[str, float]] = {}
        for o in occ.to_dict("records"):
            regimes.setdefault(str(o["granularity"]), {})[str(o["regime"])] = round(
                float(o["occupancy"]), 6
            )

        trades = tagged[tagged["asset_id"] == aid] if len(tagged) else tagged
        n_trades = int(len(trades))
        oos: Dict[str, Any] = {"trades": n_trades}
        if n_trades:
            oos["win_rate"] = round(float(trades["is_winner"].mean()), 6)
            oos["mean_r"] = round(float(trades["r_multiple"].mean()), 6)
            oos["strategies"] = int(trades["strategy_id"].nunique())

        modelled_grans = [g for g in grans if g["modelled"]]
        assets.append(
            {
                "asset_id": aid,
                "symbol": symbol,
                "market_type": str(row.get("market_type") or ""),
                "is_active": bool(row.get("is_active")),
                "price_coverage": grans,
                "modelled_granularities": [g["granularity"] for g in modelled_grans],
                "stale_modelled_granularities": [
                    g["granularity"] for g in modelled_grans if g["stale"]
                ],
                "regime_occupancy": regimes,
                "oos": oos,
            }
        )

    return {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "assets": assets,
        "asset_count": len(assets),
        "active_count": sum(1 for a in assets if a["is_active"]),
        "modelled_granularities": list(modelled),
        "stale_after_hours": STALE_AFTER_HOURS,
        "regime_map_relationship": map_reference_note(regime_map),
        "semantics": (
            "This is the instrument universe: what System 1 ingests and models. It is a "
            "DIMENSION and is independent of strategy qualification — it does not shrink "
            "when strategies fail their gates, and would be identical if zero strategies "
            "ever qualified. Never gate this list, or an Assets page, on the "
            "regime-strategy map or on a qualified-strategy count: they answer different "
            "questions. An empty array here means the feed is broken, not that the "
            "system is idle."
        ),
        "not_included": (
            "No live market data. Bid/ask, spread, session state and open positions are "
            "System 2's — it holds the broker connection. Join on `symbol`."
        ),
    }
