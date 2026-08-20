"""Two guarantees this package must never lose: it cannot see the future, and it cannot write.

Causality
---------
``contract_v2``'s ``assert_no_lookahead_v2`` is unavailable here (this experiment deliberately
runs on the legacy engine so the A/B is like-for-like — see the package docstring), so the same
idea is reproduced directly: truncate the frame at bar *t* and confirm the signal at *t* is
unchanged. A strategy that reads ahead produces a different answer when the future is removed.

Isolation
---------
The read-only guarantee is enforced by PostgreSQL, so the test asserts the database itself
refuses a write rather than trusting a code-level convention. It also greps the package source
for write verbs, which catches a future contributor adding an INSERT that never runs in tests.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.regime_aware.context import UNKNOWN, attach_regime
from src.regime_aware.strategies.donchian_vcp import build_baseline, build_regime_aware

_PKG = Path(__file__).resolve().parents[1]


def _frame(n: int = 900, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    vol = np.where((np.arange(n) // 120) % 2 == 0, 0.0004, 0.0025)
    close = 1.30 * np.exp(np.cumsum(rng.normal(0, 1, n) * vol))
    spread = np.abs(rng.normal(0, 1, n)) * vol * close
    idx = pd.date_range("2019-01-01", periods=n, freq="4h", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close + spread,
            "Low": close - spread,
            "Close": close,
            "Volume": 500.0,
        },
        index=idx,
    )
    labels = ["Ranging", "High-Vol", "Trending-Up", "Trending-Down"]
    df["regime"] = [labels[(i // 90) % 4] for i in range(n)]
    return df


@pytest.mark.parametrize("build", [build_baseline, build_regime_aware])
def test_signal_at_t_does_not_change_when_the_future_is_removed(build):
    """Truncation probe: the decision at bar t must not depend on bars after t."""
    df = _frame()
    strategy = build()

    full = strategy.generate_signals(
        strategy.calculate_indicators(df.copy(), "EUR_USD", "H4"), "EUR_USD", "H4"
    )

    for cut in (400, 550, 700, 860):
        prefix = df.iloc[:cut].copy()
        truncated = strategy.generate_signals(
            strategy.calculate_indicators(prefix, "EUR_USD", "H4"), "EUR_USD", "H4"
        )
        # Compare only bars past indicator warm-up, where both series are well-defined.
        start = 200
        assert (
            truncated.iloc[start:].to_numpy() == full.iloc[start:cut].to_numpy()
        ).all(), f"signals changed when history was truncated at {cut} — look-ahead"


def test_regime_join_is_backward_only():
    """A bar must never receive a label stamped after it."""
    idx = pd.date_range("2020-01-01", periods=6, freq="4h", tz="UTC")
    prices = pd.DataFrame({"Close": range(6)}, index=idx)
    labels = pd.DataFrame(
        {
            "bar_time": [idx[2], idx[4]],
            "regime": ["High-Vol", "Ranging"],
        }
    )
    out = attach_regime(prices, labels)
    assert list(out["regime"]) == [
        UNKNOWN,
        UNKNOWN,
        "High-Vol",
        "High-Vol",
        "Ranging",
        "Ranging",
    ]


def test_warmup_bars_are_unknown_not_forward_filled():
    """Pre-label bars are UNKNOWN — never back-filled from the first known label."""
    idx = pd.date_range("2020-01-01", periods=4, freq="4h", tz="UTC")
    prices = pd.DataFrame({"Close": range(4)}, index=idx)
    labels = pd.DataFrame({"bar_time": [idx[3]], "regime": ["Trending-Up"]})
    assert list(attach_regime(prices, labels)["regime"]) == [
        UNKNOWN,
        UNKNOWN,
        UNKNOWN,
        "Trending-Up",
    ]


def test_attach_regime_does_not_mutate_its_input():
    """Frames are shared between arms; poisoning one would silently corrupt the other."""
    idx = pd.date_range("2020-01-01", periods=3, freq="4h", tz="UTC")
    prices = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)
    before = prices.copy(deep=True)
    attach_regime(prices, None)
    pd.testing.assert_frame_equal(prices, before)


def test_smoothed_regime_column_is_refused():
    """regime_smoothed leaks future bars into past labels — the guard must be a hard error."""
    from src.regime_aware.context import load_regime_labels

    with pytest.raises(ValueError, match="not permitted"):
        load_regime_labels(conn=None, granularity="H4", column="regime_smoothed")


#: The single table this package is allowed to write. R1 (2026-08-16) gave the trial its
#: own outcomes table; everything else — prices, regimes, the live fact tables — stays
#: strictly read-only. The exemption is one table wide on purpose.
_WRITABLE_TABLE = "fact_regime_trial_outcomes"


def test_package_source_writes_only_to_the_trial_table():
    """No INSERT/UPDATE/DELETE/CREATE/DROP/TRUNCATE except against the trial's own table.

    Originally this forbade writes outright. R1 introduced a legitimate writer, so the
    rule narrowed rather than lapsed: a write naming any other table is still a failure,
    because the value of this guard is stopping the package touching the live data it
    reads.
    """
    pattern = re.compile(
        r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+TABLE|DROP\s+TABLE|TRUNCATE)\b",
        re.IGNORECASE,
    )
    offenders = []
    for path in _PKG.rglob("*.py"):
        if path.name == Path(__file__).name:
            continue  # this file names the verbs in order to forbid them
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # prose describing the rule is not an executable statement
            if not pattern.search(line):
                continue
            if _WRITABLE_TABLE in line:
                continue
            offenders.append(f"{path.relative_to(_PKG)}:{i}: {line.strip()}")
    assert not offenders, (
        f"writes to tables other than {_WRITABLE_TABLE} in a read-only package:\n"
        + "\n".join(offenders)
    )


def test_no_unqualified_delete_of_the_trial_table():
    """A DELETE on the trial table must carry a WHERE clause.

    An ``autouse`` fixture in test_outcomes.py once ran
    ``DELETE FROM fact_regime_trial_outcomes`` with no predicate, so running the suite
    destroyed a completed 65,942-row R3 run. Tests may only delete rows they created.
    """
    pattern = re.compile(rf"DELETE\s+FROM\s+{_WRITABLE_TABLE}", re.IGNORECASE)
    offenders = []
    for path in _PKG.rglob("*.py"):
        if path.name == Path(__file__).name:
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # prose describing the rule is not an executable statement
            if pattern.search(line) and "WHERE" not in line.upper():
                offenders.append(f"{path.relative_to(_PKG)}:{i}: {line.strip()}")
    assert not offenders, "unqualified DELETE of the trial table:\n" + "\n".join(offenders)


def test_database_itself_refuses_a_write():
    """The isolation guarantee is PostgreSQL's, not a convention — prove it against the DB."""
    psycopg2 = pytest.importorskip("psycopg2")
    from src.regime_aware.context import readonly_connection

    try:
        conn = readonly_connection()
    except Exception as exc:  # pragma: no cover - no DB in this environment
        pytest.skip(f"database unavailable: {exc}")
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM fact_market_regime_v2")
        assert cur.fetchone()[0] > 0, "read path is broken"
        with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
            cur.execute("CREATE TABLE regime_aware_should_not_exist (x int)")
    finally:
        conn.close()
