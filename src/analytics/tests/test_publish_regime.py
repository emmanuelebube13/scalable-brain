import pytest
from unittest.mock import patch, MagicMock
from src.analytics.publish_regime import build_document


def test_build_document_repairs_r3_removal():
    """
    Test that publish_regime works even after the regime_aware package was deleted.
    It should return a valid document where every strategy is 'unclassified' and has a permissive mask,
    since the ML gatekeeper now decides gating rather than hardcoded family masks.
    """
    # Just checking it doesn't crash on import and builds correctly
    # We mock out database and data loading to make it a fast unit test
    with patch("src.analytics.publish_regime.get_engine"), patch(
        "src.analytics.extract.load_asset_symbols", return_value={1: "EUR_USD"}
    ), patch("src.analytics.extract.load_regime_strategy_map", return_value={}), patch(
        "src.layer0.strategies.research_data.load_ohlcv_readonly", return_value=None
    ), patch(
        "src.analytics.publish_regime._write_json"
    ), patch(
        "src.analytics.publish_regime._sha256", return_value="dummy_sha"
    ):

        payload, path = build_document()
        assert payload["status"] == "published"
        assert "regimes" in payload
