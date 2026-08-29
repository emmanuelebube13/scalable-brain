"""S1-EXPORT-003 — asset inventory tests (pure; no DB).

The defect these guard is a category error, not a crash: treating the instrument universe
as if it were derived from strategy qualification. That produced a full-width "System Idle
— 0 qualified strategies" banner on a page listing five live, fully-ingested pairs.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.analytics.assets import build_asset_inventory, map_reference_note

NOW = datetime(2026, 8, 23, 20, 0, tzinfo=timezone.utc)


def _dim(n=2):
    return pd.DataFrame(
        [
            {
                "asset_id": i,
                "symbol": s,
                "market_type": "Forex",
                "is_active": True,
            }
            for i, s in list(enumerate(["EUR_USD", "GBP_USD"], start=1))[:n]
        ]
    )


def _coverage(rows):
    return pd.DataFrame(
        [
            {
                "asset_id": a,
                "granularity": g,
                "bars": b,
                "first_bar": pd.Timestamp("2006-01-01", tz="UTC"),
                "last_bar": pd.Timestamp(last, tz="UTC"),
            }
            for a, g, b, last in rows
        ]
    )


_EMPTY_OCC = pd.DataFrame(columns=["granularity", "asset_id", "regime", "occupancy"])
_EMPTY_TRADES = pd.DataFrame(
    columns=["asset_id", "is_winner", "r_multiple", "strategy_id"]
)


def _build(dim=None, coverage=None, occupancy=None, tagged=None, regime_map=None):
    return build_asset_inventory(
        asset_dim=_dim() if dim is None else dim,
        coverage=(
            _coverage([(1, "H1", 100, "2026-08-21T20:00")])
            if coverage is None
            else coverage
        ),
        occupancy=_EMPTY_OCC if occupancy is None else occupancy,
        tagged=_EMPTY_TRADES if tagged is None else tagged,
        regime_map={} if regime_map is None else regime_map,
        generated_at="2026-08-23T20:00:00Z",
        now=NOW,
    )


# --- the category error this exists to prevent -------------------------------------------
def test_the_universe_is_identical_when_no_strategy_qualifies():
    """The whole point. An empty regime map must not change the asset list by one row."""
    full = _build(regime_map={"regimes": {"Ranging": [{"strategy_id": 1}]}})
    empty = _build(regime_map={"regimes": {}})
    assert full["assets"] == empty["assets"]
    assert full["asset_count"] == empty["asset_count"] == 2


def test_an_asset_with_no_trades_and_no_regimes_still_appears():
    """Absence of results is not absence of the instrument."""
    out = _build()
    assert out["asset_count"] == 2
    gbp = [a for a in out["assets"] if a["symbol"] == "GBP_USD"][0]
    assert gbp["oos"]["trades"] == 0
    assert gbp["regime_occupancy"] == {}
    assert gbp["is_active"] is True


def test_the_payload_states_that_the_map_cannot_filter_assets():
    note = map_reference_note({"regimes": {"Ranging": [{"strategy_id": 1}]}})
    assert note["map_references_assets"] is False
    assert note["map_cell_count"] == 1


def test_map_relationship_is_not_an_empty_symbol_list():
    """An empty array is the shape a consumer misreads as 'no assets'. It must not be
    possible to read a list-of-nothing out of this field."""
    rel = _build()["regime_map_relationship"]
    assert not isinstance(rel, list)
    assert rel["map_references_assets"] is False


# --- coverage and staleness ---------------------------------------------------------------
def test_stored_but_unmodelled_granularities_are_flagged():
    """M15 has half a million bars per pair and nothing reads it. Row count must not be
    mistaken for capability."""
    out = _build(
        coverage=_coverage(
            [(1, "H1", 100, "2026-08-21T20:00"), (1, "M15", 500000, "2026-05-01T20:45")]
        )
    )
    cov = {g["granularity"]: g for g in out["assets"][0]["price_coverage"]}
    assert cov["H1"]["modelled"] is True
    assert cov["M15"]["modelled"] is False
    assert cov["M15"]["bars"] == 500000
    assert out["assets"][0]["modelled_granularities"] == ["H1"]


def test_a_fresh_modelled_series_is_not_stale():
    out = _build(coverage=_coverage([(1, "H1", 100, "2026-08-21T20:00")]))
    assert out["assets"][0]["price_coverage"][0]["stale"] is False
    assert out["assets"][0]["stale_modelled_granularities"] == []


def test_a_dead_feed_on_a_modelled_granularity_is_surfaced():
    """The failure worth alarming on: a granularity the models depend on stopped updating."""
    out = _build(coverage=_coverage([(1, "H1", 100, "2026-01-01T00:00")]))
    assert out["assets"][0]["price_coverage"][0]["stale"] is True
    assert out["assets"][0]["stale_modelled_granularities"] == ["H1"]


def test_age_is_measured_in_hours_from_the_last_bar():
    out = _build(coverage=_coverage([(1, "H1", 100, "2026-08-23T00:00")]))
    assert out["assets"][0]["price_coverage"][0]["age_hours"] == 20.0


# --- per-asset stats ----------------------------------------------------------------------
def test_oos_stats_are_computed_per_asset():
    tagged = pd.DataFrame(
        [
            {"asset_id": 1, "is_winner": True, "r_multiple": 2.0, "strategy_id": 7},
            {"asset_id": 1, "is_winner": False, "r_multiple": -1.0, "strategy_id": 8},
            {"asset_id": 2, "is_winner": True, "r_multiple": 1.0, "strategy_id": 7},
        ]
    )
    out = _build(tagged=tagged)
    by_symbol = {a["symbol"]: a for a in out["assets"]}
    assert by_symbol["EUR_USD"]["oos"] == {
        "trades": 2,
        "win_rate": 0.5,
        "mean_r": 0.5,
        "strategies": 2,
    }
    assert by_symbol["GBP_USD"]["oos"]["trades"] == 1


def test_regime_occupancy_is_nested_by_granularity():
    occ = pd.DataFrame(
        [
            {
                "granularity": "D1",
                "asset_id": 1,
                "regime": "Ranging",
                "occupancy": 0.6,
            },
            {
                "granularity": "D1",
                "asset_id": 1,
                "regime": "High-Vol",
                "occupancy": 0.4,
            },
        ]
    )
    out = _build(occupancy=occ)
    assert out["assets"][0]["regime_occupancy"]["D1"] == {
        "Ranging": 0.6,
        "High-Vol": 0.4,
    }


def test_active_count_counts_only_active_assets():
    dim = _dim()
    dim.loc[dim["asset_id"] == 2, "is_active"] = False
    out = _build(dim=dim)
    assert out["asset_count"] == 2
    assert out["active_count"] == 1
