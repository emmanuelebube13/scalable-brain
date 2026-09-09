"""Change detection for the scheduled (``--incremental``) labelling run.

These cover the decision "is this row already correct in the table?" in isolation. The
write path itself is exercised live; what is worth pinning down here is that the
comparison looks at more than the label, because a comparison that only checked ``regime``
would silently leave stale audit values behind a correct verdict.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.regime import build_structural as B
from src.regime import structural as S

VER = S.LABELLER_VERSION
BAR = pd.Timestamp("2026-09-03T21:00:00Z")
SRC = pd.Timestamp("2026-09-02T21:00:00Z")


def _row(**over):
    base = dict(
        bar_time=BAR,
        regime="Trending-Up",
        source_bar_time=SRC,
        adx=27.5,
        ema_fast=1.101,
        ema_slow=1.099,
        atr_pct=0.004,
        vol_zscore=-0.31,
    )
    base.update(over)
    return next(pd.DataFrame([base]).itertuples(index=False))


def _stored(**over):
    base = dict(
        bar_time_utc=BAR,
        regime="Trending-Up",
        source_bar_time_utc=SRC,
        adx=27.5,
        ema_fast=1.101,
        ema_slow=1.099,
        atr_pct=0.004,
        vol_zscore=-0.31,
        labeller_version=VER,
    )
    base.update(over)
    return tuple(base.values())


def test_identical_row_is_not_rewritten():
    assert B._unchanged(_row(), _stored()) is True


def test_absent_row_is_written():
    assert B._unchanged(_row(), None) is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("regime", "Ranging"),
        ("labeller_version", "structural-v0.0.1"),
        ("source_bar_time_utc", pd.Timestamp("2026-09-01T21:00:00Z")),
        ("adx", 27.6),
        ("ema_fast", 1.102),
        ("ema_slow", 1.098),
        ("atr_pct", 0.005),
        ("vol_zscore", -0.30),
    ],
)
def test_any_differing_field_forces_a_write(field, value):
    """Including the indicators. A price revision can move these while leaving the label
    alone; leaving them stale would make the stored evidence describe a bar that no longer
    exists, and the table exists so a label can be disputed from that evidence."""
    assert B._unchanged(_row(), _stored(**{field: value})) is False


def test_float_roundtrip_noise_is_not_a_change():
    """DOUBLE PRECISION round-tripping must not manufacture a 30,000-row rewrite."""
    assert B._unchanged(_row(), _stored(adx=27.5 + 1e-13)) is True


def test_naive_stored_timestamp_is_localised_not_relabelled():
    """The R2.3(c) hazard: treating a naive UTC timestamp as local time shifts it hours."""
    assert B._utc(BAR.tz_localize(None)) == BAR


def test_null_indicator_matches_null_but_not_a_value():
    assert B._unchanged(_row(adx=None), _stored(adx=None)) is True
    assert B._unchanged(_row(adx=None), _stored(adx=27.5)) is False
