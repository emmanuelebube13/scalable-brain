"""trade_returns builder: OOS-only honesty, per-pair/ALL reconciliation, ordering."""

from __future__ import annotations

import pandas as pd
import pytest

from src.system1.analytics.returns import build_trade_returns, qualified_cells

ASSETS = {1: "EUR_USD", 2: "GBP_USD"}


def _tagged(rows):
    df = pd.DataFrame(
        rows,
        columns=[
            "strategy_id",
            "regime",
            "granularity",
            "asset_id",
            "entry_time",
            "r_multiple",
            "is_oos",
            "fold_id",
        ],
    )
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
    df["fold_id"] = df["fold_id"].astype("Int64")
    return df


@pytest.fixture
def tagged():
    return _tagged(
        [
            # OOS trades, deliberately out of chronological order
            (10, "Ranging", "H1", 1, "2024-02-01", 1.5, True, 1),
            (10, "Ranging", "H1", 1, "2024-01-01", -1.0, True, 1),
            (10, "Ranging", "H1", 2, "2024-03-01", 2.0, True, 1),
            # in-sample row in the same cell — must NEVER be exported
            (10, "Ranging", "H1", 1, "2020-01-01", 99.0, False, pd.NA),
            # OOS trade in a NON-qualified cell — must not appear either
            (7, "Ranging", "H1", 1, "2024-01-01", 1.0, True, 1),
        ]
    )


CELLS = {(10, "Ranging", "H1")}


def test_in_sample_rows_never_exported(tagged):
    out = build_trade_returns(tagged, CELLS, ASSETS, {})
    for cell in out["cells"]:
        assert 99.0 not in cell["r_multiples"]
    assert out["oos_only"] is True


def test_only_qualified_cells_exported(tagged):
    out = build_trade_returns(tagged, CELLS, ASSETS, {})
    assert {c["strategy_id"] for c in out["cells"]} == {"10"}


def test_all_cell_equals_sum_of_pairs_and_is_chronological(tagged):
    out = build_trade_returns(tagged, CELLS, ASSETS, {})
    by_pair = {c["pair"]: c for c in out["cells"]}
    assert by_pair["ALL"]["n_trades"] == (
        by_pair["EUR_USD"]["n_trades"] + by_pair["GBP_USD"]["n_trades"]
    )
    for cell in out["cells"]:
        assert cell["trade_timestamps"] == sorted(cell["trade_timestamps"])
        assert len(cell["r_multiples"]) == len(cell["trade_timestamps"])
    # chronological r ordering follows timestamps, not input order
    assert by_pair["EUR_USD"]["r_multiples"] == [-1.0, 1.5]


def test_qualified_cells_parses_variant_granularity():
    regime_map = {
        "regimes": {
            "Ranging": [
                {"strategy_id": 10, "variant": "Range_Stochastic_Divergence@H1"},
                {"strategy_id": 10, "variant": "Range_Stochastic_Divergence@H4"},
            ],
            "Trending-Up": [
                {"strategy_id": 10, "variant": "Range_Stochastic_Divergence@H1"}
            ],
        }
    }
    assert qualified_cells(regime_map) == {
        (10, "Ranging", "H1"),
        (10, "Ranging", "H4"),
        (10, "Trending-Up", "H1"),
    }
