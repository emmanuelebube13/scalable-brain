from datetime import timedelta

from src.layer0.ingest_data.ingest_oanda_prices import (
    get_interval_delta,
    to_oanda_granularity,
)


def test_weekly_granularity_alias_is_supported() -> None:
    assert get_interval_delta("W") == timedelta(weeks=1)
    assert get_interval_delta("W1") == timedelta(weeks=1)
    assert to_oanda_granularity("W") == "W"
    assert to_oanda_granularity("W1") == "W"


from datetime import datetime
from unittest.mock import MagicMock
from src.layer0.ingest_data.ingest_oanda_prices import fetch_candles_window, CONFIG


def test_fetch_candles_window_price_param() -> None:
    client = MagicMock()
    # default price
    fetch_candles_window(
        client, "EUR_USD", "H1", datetime(2026, 1, 1), datetime(2026, 1, 2)
    )
    called_request = client.request.call_args[0][0]
    assert called_request.params["price"] == CONFIG.OANDA_PRICE

    # overridden price
    fetch_candles_window(
        client, "EUR_USD", "H1", datetime(2026, 1, 1), datetime(2026, 1, 2), price="MBA"
    )
    called_request = client.request.call_args[0][0]
    assert called_request.params["price"] == "MBA"
