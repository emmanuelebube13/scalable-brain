"""Guard for `_atr_at` — the last step before a signal reaches the wire.

ATR is mandatory on every emitted signal (System 3 sizes against it), so if `_atr_at`
returns None the producer refuses to emit. That makes this function a single point of
total failure: it shipped calling `indicators.atr(frame, period=14)` when the real
signature is `atr(high, low, close, period)`, every call raised TypeError, a broad
`except` reported "ATR unavailable", and the producer dropped 100% of signals while
logging the same "No signals generated" line a quiet market produces.

These tests pin the call signature by using the real indicator — a mock would have
happily accepted the wrong arguments and reproduced the original bug.
"""

import numpy as np
import pandas as pd

from src.signals.build import _atr_at


def _frame(n: int = 60) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    base = np.linspace(1.10, 1.12, n)
    return pd.DataFrame(
        {
            "Open": base,
            "High": base + 0.0010,
            "Low": base - 0.0010,
            "Close": base + 0.0002,
            "Volume": 100.0,
        },
        index=idx,
    )


def test_returns_a_positive_atr_on_a_well_formed_frame():
    frame = _frame()
    value = _atr_at({"H1": frame}, "H1", frame.index[-1])
    assert value is not None, "a well-formed frame must yield an ATR, not None"
    assert value > 0
    # True range here is dominated by the 20-pip high/low spread.
    assert 0.0005 < value < 0.005


def test_evaluates_at_the_decision_bar_not_the_end_of_the_frame():
    """The bar under decision is mid-frame during a replay; later bars must not leak in."""
    frame = _frame()
    mid = frame.index[30]
    # Make everything after the decision bar wildly volatile.
    frame.loc[frame.index > mid, "High"] += 0.5
    frame.loc[frame.index > mid, "Low"] -= 0.5

    at_mid = _atr_at({"H1": frame}, "H1", mid)
    at_end = _atr_at({"H1": frame}, "H1", frame.index[-1])
    assert at_mid is not None and at_end is not None
    assert at_mid < at_end, "future bars leaked into the decision-bar ATR"


def test_missing_ohlc_columns_return_none_rather_than_raising():
    frame = _frame().drop(columns=["High"])
    assert _atr_at({"H1": frame}, "H1", frame.index[-1]) is None


def test_absent_or_empty_granularity_returns_none():
    frame = _frame()
    assert _atr_at({"H1": frame}, "H4", frame.index[-1]) is None
    assert _atr_at({"H1": frame.iloc[0:0]}, "H1", frame.index[-1]) is None


def test_bar_earlier_than_any_data_returns_none():
    frame = _frame()
    before = frame.index[0] - pd.Timedelta(days=1)
    assert _atr_at({"H1": frame}, "H1", before) is None
