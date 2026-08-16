import pandas as pd
import pytest

from src.layer0.strategies.contract_v2 import assert_no_lookahead_v2
from src.layer0.strategies.research.pinbar_nose_eyes import PinbarNoseEyes

# ---------------------------------------------------------------------------
# 1. The bars
# ---------------------------------------------------------------------------

BARS_DATA = []
# 0-2
for _ in range(3):
    BARS_DATA.append((1.1050, 1.1070, 1.1030, 1.1050))
# 3-7 (swing low at 5)
BARS_DATA.extend(
    [
        (1.1040, 1.1060, 1.1020, 1.1040),
        (1.1030, 1.1050, 1.1010, 1.1030),
        (1.1020, 1.1040, 1.1000, 1.1020),  # 5 - Swing low 1.1000
        (1.1030, 1.1050, 1.1010, 1.1030),
        (1.1040, 1.1060, 1.1020, 1.1040),
    ]
)
# 8-13
for _ in range(6):
    BARS_DATA.append((1.1060, 1.1080, 1.1040, 1.1060))
# 14-15
BARS_DATA.extend(
    [
        (1.1060, 1.1070, 1.1030, 1.1040),  # 14 - LE long
        (1.1050, 1.1060, 1.1000, 1.1055),  # 15 - N long
    ]
)
# 16-17
BARS_DATA.extend(
    [
        (1.1150, 1.1170, 1.1130, 1.1150),
        (1.1160, 1.1180, 1.1140, 1.1160),
    ]
)
# 18-22 (swing high at 20)
BARS_DATA.extend(
    [
        (1.1160, 1.1180, 1.1140, 1.1160),
        (1.1170, 1.1190, 1.1150, 1.1170),
        (1.1180, 1.1200, 1.1160, 1.1180),  # 20 - Swing high 1.1200
        (1.1170, 1.1190, 1.1150, 1.1170),
        (1.1160, 1.1180, 1.1140, 1.1160),
    ]
)
# 23-24
BARS_DATA.extend(
    [
        (1.1140, 1.1160, 1.1120, 1.1140),
        (1.1140, 1.1160, 1.1120, 1.1140),
    ]
)
# 25-26
BARS_DATA.extend(
    [
        (1.1140, 1.1170, 1.1130, 1.1160),  # 25 - LE short
        (1.1150, 1.1200, 1.1140, 1.1145),  # 26 - N short
    ]
)
# 27-39
for _ in range(13):
    BARS_DATA.append((1.1130, 1.1150, 1.1110, 1.1130))


class _FixtureScale(PinbarNoseEyes):
    SWING_PERIOD = 2
    ATR_PERIOD = 5

    @property
    def warmup_bars(self) -> int:
        return 10


@pytest.fixture(scope="module")
def frames() -> dict:
    idx = pd.date_range("2020-01-01", periods=len(BARS_DATA), freq="4h", tz="UTC")
    h4 = pd.DataFrame(
        BARS_DATA,
        columns=["Open", "High", "Low", "Close"],
        index=idx,
    )
    h4["Volume"] = 1.0
    return {"H4": h4}


@pytest.fixture(scope="module")
def orders(frames) -> list:
    return list(_FixtureScale().generate_orders(frames))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_emits_expected_orders(orders) -> None:
    # §4 and §5 expect two specific orders to fire.
    assert len(orders) == 2
    # At bars 15 and 26.
    assert str(orders[0].decision_bar) == "2020-01-03 12:00:00+00:00"
    assert str(orders[1].decision_bar) == "2020-01-05 08:00:00+00:00"


def test_long_order_matches_arithmetic(orders) -> None:
    """Check the long order on bar 15."""
    o = orders[0]

    # §4.6 S/R filter: S_level = 1.1000, Low(N) = 1.1000, distance = 0 <= 0.5 * ATR.
    # §4 entry type: buy_stop
    # §4 entry level: High(N) = 1.1060. entry_price = 1.1060 + 0.0001 = 1.1061.
    # §6 stop: min(S_level, Low(N)) - 1 pip = min(1.1000, 1.1000) - 0.0001 = 1.0999.
    # §7 exit TP1: High(LE) = 1.1070. tp_price = 1.1070 + 0.0001 = 1.1071.
    # §7 exit leg fraction: 1.0.

    assert o.direction == 1
    assert o.entry == "buy_stop"
    assert o.entry_price == pytest.approx(1.1061, abs=1e-9)
    assert o.stop.price == pytest.approx(1.0999, abs=1e-9)

    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(1.1071, abs=1e-9)
    # §7 fraction sums to 1.0
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_short_order_matches_arithmetic(orders) -> None:
    """Check the short order on bar 26."""
    o = orders[1]

    # §5.6 S/R filter: R_level = 1.1200, High(N) = 1.1200, distance = 0 <= 0.5 * ATR.
    # §5 entry type: sell_stop
    # §5 entry level: Low(N) = 1.1140. entry_price = 1.1140 - 0.0001 = 1.1139.
    # §6 stop: max(R_level, High(N)) + 1 pip = max(1.1200, 1.1200) + 0.0001 = 1.1201.
    # §7 exit TP1: Low(LE) = 1.1130. tp_price = 1.1130 - 0.0001 = 1.1129.
    # §7 exit leg fraction: 1.0.

    assert o.direction == -1
    assert o.entry == "sell_stop"
    assert o.entry_price == pytest.approx(1.1139, abs=1e-9)
    assert o.stop.price == pytest.approx(1.1201, abs=1e-9)

    assert len(o.exits) == 1
    assert o.exits[0].label == "TP1"
    assert o.exits[0].price == pytest.approx(1.1129, abs=1e-9)
    # §7 fraction sums to 1.0
    assert o.exits[0].fraction == pytest.approx(1.0, abs=1e-9)


def test_no_lookahead(frames) -> None:
    assert_no_lookahead_v2(_FixtureScale(), frames)
