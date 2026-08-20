"""T6 adversarial review — four attacks, each must be blocked by CODE.

The task asks whether an unvetted strategy can reach `qualified`, or whether
research code can touch live tables. These tests *attempt* each attack. A test
passing means the attack was refused by the implementation, not by convention.

Attacks:
  1. Promote straight from research to qualified, skipping the gates.
  2. Register two strategies with the same strategy_id.
  3. A look-ahead strategy (`shift(-1)`) passing the walk-forward.
  4. Research code writing to a `fact_*` table.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import List

import pandas as pd
import pytest

from src.layer0.strategies import promote as P
from src.layer0.strategies import registry as R
from src.layer0.strategies import research_data
from src.layer0.strategies.contract import (
    LookAheadError,
    Stage,
    Strategy,
    StrategyMetadata,
    assert_no_lookahead,
)


def _meta(sid: str = "attack_strategy") -> StrategyMetadata:
    return StrategyMetadata(
        strategy_id=sid,
        name="Attack",
        version="0.0.1",
        author="adversarial review",
        hypothesis="This strategy exists purely to attempt to bypass the promotion gates.",
        granularities=["H1"],
        pairs=["EUR_USD"],
    )


class _Honest(Strategy):
    @property
    def metadata(self):
        return _meta()

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        # Trailing-only: a simple rolling mean crossover.
        ma = df["Close"].rolling(5, min_periods=5).mean()
        return (df["Close"] > ma).astype(int).rename(None)


class _LookAhead(Strategy):
    """ATTACK 3: peeks one bar into the future."""

    @property
    def metadata(self):
        return _meta("lookahead_cheat")

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        future = df["Close"].shift(-1)  # <-- the cheat
        return (future > df["Close"]).astype(int)


class _WholeSeriesNorm(Strategy):
    """ATTACK 3b: subtler — normalises over the whole frame, so early bars know the end."""

    @property
    def metadata(self):
        return _meta("whole_series_norm")

    @property
    def required_indicators(self) -> List[str]:
        return []

    @property
    def warmup_bars(self) -> int:
        return 10

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        z = (df["Close"] - df["Close"].mean()) / df["Close"].std()
        return (z > 0).astype(int)


@pytest.fixture
def frame() -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=400, freq="h", tz="UTC")
    close = pd.Series(range(400), index=idx, dtype=float) % 37 + 100.0
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 1000,
        },
        index=idx,
    )


# --- ATTACK 1: skip the gates ------------------------------------------------


def test_cannot_promote_research_directly_to_qualified():
    """The whole point of the pipeline. Must be refused, with a reason."""
    reg = R.get_registry(refresh=True)
    entry = next((r for r in reg.list(Stage.RESEARCH)), None)
    if entry is None:
        pytest.skip("no research-stage strategy present to attack with")

    with pytest.raises(
        P.PromotionRefused, match="cannot be skipped|only legal next stage"
    ):
        P.promote(entry.strategy_id, Stage.QUALIFIED, registry=reg, dry_run=True)


def test_promotion_step_map_has_no_edge_from_research_to_qualified():
    """Source-level: the legal-transition table itself must not contain the shortcut."""
    assert P._NEXT_STAGE[Stage.RESEARCH] is Stage.STAGED
    assert P._NEXT_STAGE[Stage.STAGED] is Stage.QUALIFIED
    assert Stage.QUALIFIED not in P._NEXT_STAGE, "qualified must be terminal"


def test_qualification_imports_the_live_gates_rather_than_copying_thresholds():
    """A second copy of the thresholds is a second qualification path waiting to drift."""
    src = inspect.getsource(P.promote)
    assert "from src.vetting.gates import" in src
    assert "evaluate_gates(cell)" in src
    # None of the live numbers may be literal in this module.
    module_src = Path(P.__file__).read_text()
    for literal in ("1.5", "0.8", "0.25", "0.40", "3.0", "60"):
        assert (
            f"= {literal}" not in module_src
        ), f"threshold {literal} appears literally in promote.py — import GATES instead"


# --- ATTACK 2: duplicate strategy_id -----------------------------------------


def test_duplicate_strategy_id_is_rejected_loudly(monkeypatch):
    """FIX-S1-004 was a silent weight collapse from a duplicate id. Never again."""

    def fake_iter(stage):
        if stage is Stage.RESEARCH:
            yield ("mod_a", "A", _Honest)
        elif stage is Stage.STAGED:
            yield ("mod_b", "B", _Honest)  # same metadata.strategy_id

    monkeypatch.setattr(R, "_iter_stage_classes", fake_iter)

    with pytest.raises(R.DuplicateStrategyId, match="declared twice"):
        R.StrategyRegistry()


def test_duplicate_detection_spans_stages(monkeypatch):
    """An id used in research must block the same id in qualified, not just siblings."""

    def fake_iter(stage):
        if stage is Stage.RESEARCH:
            yield ("mod_a", "A", _Honest)
        elif stage is Stage.QUALIFIED:
            yield ("mod_c", "C", _Honest)

    monkeypatch.setattr(R, "_iter_stage_classes", fake_iter)
    with pytest.raises(R.DuplicateStrategyId):
        R.StrategyRegistry()


# --- ATTACK 3: look-ahead ----------------------------------------------------


def test_lookahead_strategy_is_caught(frame):
    with pytest.raises(LookAheadError, match="look-ahead"):
        assert_no_lookahead(_LookAhead(), frame)


def test_whole_series_normalisation_is_caught(frame):
    """The subtle case: no shift(-1), but early bars still depend on the whole frame."""
    with pytest.raises(LookAheadError):
        assert_no_lookahead(_WholeSeriesNorm(), frame)


def test_honest_strategy_passes_the_lookahead_check(frame):
    assert_no_lookahead(_Honest(), frame)  # must not raise


def test_promotion_runs_the_lookahead_check():
    """Source-level: the check is wired into the evaluation path, not optional."""
    assert "assert_no_lookahead(strategy, df)" in inspect.getsource(
        P.evaluate_walk_forward
    )


# --- ATTACK 4: research writing to live tables -------------------------------


def test_research_data_module_has_no_write_path():
    src = Path(research_data.__file__).read_text().upper()
    for verb in (
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "DROP ",
        "CREATE TABLE",
        "ALTER ",
    ):
        assert verb not in src, (
            f"research_data.py contains {verb!r} — the sandbox must be read-only; "
            "research that can mutate fact_* tables contaminates the live training set"
        )


def test_research_data_only_selects():
    src = Path(research_data.__file__).read_text()
    assert "SELECT" in src
    assert ".begin()" not in src, "no write transaction may be opened here"
    assert "to_sql" not in src, "pandas write path must not exist in the sandbox"


def test_strategy_contract_exposes_no_persistence_surface():
    """A Strategy gets data in and returns signals. Nothing else."""
    methods = {n for n, _ in inspect.getmembers(Strategy, inspect.isfunction)}
    forbidden = {"save", "write", "persist", "commit", "execute", "place_order"}
    assert not (
        methods & forbidden
    ), f"contract exposes persistence: {methods & forbidden}"


# --- the structural guarantee: only qualified is visible to the live path -----


def test_live_vetting_path_sees_only_qualified(monkeypatch):
    def fake_iter(stage):
        if stage is Stage.RESEARCH:
            yield ("mod_r", "R", _Honest)
        elif stage is Stage.STAGED:
            yield ("mod_s", "S", _LookAhead)
        elif stage is Stage.QUALIFIED:
            yield ("mod_q", "Q", _WholeSeriesNorm)

    monkeypatch.setattr(R, "_iter_stage_classes", fake_iter)

    reg = R.StrategyRegistry()
    assert len(reg) == 3
    qualified = reg.qualified()
    assert [q.strategy_id for q in qualified] == ["whole_series_norm"]
    assert all(q.stage is Stage.QUALIFIED for q in qualified)


def test_stage_is_derived_from_location_not_self_declared(monkeypatch):
    """A file cannot promote itself by editing metadata.stage."""

    class Liar(_Honest):
        @property
        def metadata(self):
            m = _meta("liar")
            return StrategyMetadata(**{**m.__dict__, "stage": Stage.QUALIFIED})

    def fake_iter(stage):
        if stage is Stage.RESEARCH:
            yield ("mod_l", "L", Liar)

    monkeypatch.setattr(R, "_iter_stage_classes", fake_iter)

    reg = R.StrategyRegistry()
    assert (
        reg.get("liar").stage is Stage.RESEARCH
    ), "the registry must trust the directory, not the strategy's own claim"
    assert reg.qualified() == []


# --- ATTACK 3b: look-ahead that hides in the gaps (FIX-S1-013) ----------------


class _RareLookAhead:
    """Fires rarely, and only via a centred window — the real strategy-10 shape.

    ``Range_Stochastic_Divergence`` fired 352 times in 130,299 bars and used
    ``rolling(center=True)`` for swing detection. The original windowed probe compared
    five 50-bar tails; on a strategy this sparse those windows contained no signals at
    all, so it compared zeros to zeros and passed. That is how the look-ahead reached
    production and became the ONLY strategy in the live regime map.
    """

    strategy_id = "rare_lookahead"
    warmup_bars = 20

    # Fires only in this early band. The windowed probe samples cuts in the LAST half of
    # the frame and compares 50-bar tails, so it never covers a firing bar here — the
    # sparseness is the whole point of the fixture.
    FIRE_BEFORE = 150

    def generate_signals(self, df):
        import numpy as np
        import pandas as pd

        out = pd.Series(0, index=df.index)
        if len(df) <= self.warmup_bars:
            return out
        # a centred window: bar t depends on bars after t
        centred = df["Close"].rolling(window=9, center=True).max()
        pos = np.arange(len(df))
        fires = (
            (df["Close"] == centred)
            & (pos > self.warmup_bars)
            & (pos < self.FIRE_BEFORE)
        )
        out[fires.fillna(False)] = 1
        return out


def test_sparse_lookahead_is_caught_even_when_windows_are_empty(frame):
    """The vacuous pass must be closed: probe firing bars when windows hold no signals."""
    with pytest.raises(LookAheadError, match="have not happened yet|look-ahead"):
        assert_no_lookahead(_RareLookAhead(), frame)


class _NeverFires:
    strategy_id = "never_fires"
    warmup_bars = 10

    def generate_signals(self, df):
        import pandas as pd

        return pd.Series(0, index=df.index)


def test_strategy_that_never_fires_cannot_qualify(frame):
    """Look-ahead freedom is unprovable on a strategy with no signals — refuse it."""
    with pytest.raises(LookAheadError, match="emits no signals"):
        assert_no_lookahead(_NeverFires(), frame)
