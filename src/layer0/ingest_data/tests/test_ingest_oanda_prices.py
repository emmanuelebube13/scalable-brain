from datetime import timedelta

from src.layer0.ingest_data.ingest_oanda_prices import get_interval_delta, to_oanda_granularity


def test_weekly_granularity_alias_is_supported() -> None:
    assert get_interval_delta("W") == timedelta(weeks=1)
    assert get_interval_delta("W1") == timedelta(weeks=1)
    assert to_oanda_granularity("W") == "W"
    assert to_oanda_granularity("W1") == "W"
