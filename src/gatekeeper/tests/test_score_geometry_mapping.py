"""O-32 — a 2.0.0 bundle must be scorable live, and the live 1.0.0 champion untouched.

Three things are pinned here:

* The serve-side geometry mapping adopts the TRAINING definition —
  ``src/outcomes/geometry.py::multiples`` (lines 138/142), UNSIGNED ATR distances — and
  is exercised on the exact case where the ledger's signed ``rr_ratio`` (build.py)
  disagrees: an inverted range, where signed rr is ``None`` but the unsigned multipliers
  are perfectly well defined. Adopting the signed definition there would feed the model a
  feature it was never fit on precisely on the pathological trades (the O-24 shape).
* A 2.0.0-shaped bundle (geometry features in, ``strategy_id`` out BY DESIGN — WO-04B)
  loads without the strategy_id RuntimeError and scores a live signal dict. A genuinely
  corrupt 1.0.0 (strategy_id in the artifact's own feature list, categories missing)
  still raises at load.
* The CURRENT live champion at models/ produces the identical score for the identical
  probe before and after this change. The standing probe scored 0.4284968376159668
  (rounds to the 0.4285 recorded in task/OPEN.md O-32) — measured against the local
  bundle before the mapping landed, re-asserted here after it.
"""

import numpy as np
import pandas as pd
import joblib
import pytest

from src.gatekeeper import train as T
from src.gatekeeper.score import Scorer, _geometry_from_signal
from src.outcomes.geometry import multiples

ATR = 0.01

LONG_SIGNAL = {
    "signal_id": "x",
    "strategy_id": "58",
    "instrument": "EUR_USD",
    "granularity": "H4",
    "direction": "long",
    "entry": 1.2500,
    "stop": 1.2350,
    "target": 1.2800,
    "atr": ATR,
    "atr_value": ATR,
    "adx_value": 24.0,
    "regime_structural": "Trending-Up",
}

SHORT_SIGNAL = dict(
    LONG_SIGNAL, direction="short", entry=1.2500, stop=1.2650, target=1.2200
)

# A long whose target sits BELOW entry. build.py's signed rr_ratio is None here
# (reward < 0); the unsigned training definition still yields defined multipliers.
INVERTED_SIGNAL = dict(LONG_SIGNAL, target=1.2400)


def _signed_rr(direction, entry, stop, target):
    """build.py:512-521 verbatim — the definition the mapping must NOT adopt."""
    if direction == "long":
        risk, reward = entry - stop, target - entry
    else:
        risk, reward = stop - entry, entry - target
    return round(reward / risk, 4) if risk > 0 and reward > 0 else None


# --- the mapping matches the training definition ----------------------------------


def test_long_multipliers_match_geometry_py():
    """geometry.py:138 — abs(entry - stop)/atr; :142 — abs(target - entry)/atr."""
    out = _geometry_from_signal(LONG_SIGNAL)
    assert out["atr_sl_multiplier"] == pytest.approx(abs(1.2500 - 1.2350) / ATR)  # 1.5
    assert out["atr_tp_multiplier"] == pytest.approx(abs(1.2800 - 1.2500) / ATR)  # 3.0
    assert (out["atr_sl_multiplier"], out["atr_tp_multiplier"]) == pytest.approx(
        multiples(1.2500, 1.2350, 1.2800, ATR)
    )


def test_short_multipliers_match_geometry_py():
    out = _geometry_from_signal(SHORT_SIGNAL)
    assert out["atr_sl_multiplier"] == pytest.approx(1.5)
    assert out["atr_tp_multiplier"] == pytest.approx(3.0)
    assert (out["atr_sl_multiplier"], out["atr_tp_multiplier"]) == pytest.approx(
        multiples(1.2500, 1.2650, 1.2200, ATR)
    )


def test_inverted_range_uses_unsigned_training_definition_not_signed_rr():
    """THE trap. Signed rr (build.py) is None on this trade; training saw 1.0x ATR."""
    assert _signed_rr("long", 1.2500, 1.2350, 1.2400) is None
    out = _geometry_from_signal(INVERTED_SIGNAL)
    assert out["atr_sl_multiplier"] == pytest.approx(1.5)
    assert out["atr_tp_multiplier"] == pytest.approx(1.0)
    assert (out["atr_sl_multiplier"], out["atr_tp_multiplier"]) == pytest.approx(
        multiples(1.2500, 1.2350, 1.2400, ATR)
    )


def test_degenerate_atr_leaves_the_multipliers_absent_not_nan():
    """Absent means MISSING_FEATURE ("no input, no opinion"); NaN would read as
    corrupt data and drop the signal."""
    out = _geometry_from_signal(dict(LONG_SIGNAL, atr=0.0))
    assert "atr_sl_multiplier" not in out
    assert "atr_tp_multiplier" not in out


def test_entry_signal_type_matches_the_outcome_writers_values():
    """Training's categories come from persist_trade_outcomes.py:321 and
    persist_all.py:257/351 — "long" if direction > 0 else "short", lowercase.
    build.py:398 emits the same words, so the mapping is verbatim."""
    assert _geometry_from_signal(LONG_SIGNAL)["entry_signal_type"] == "long"
    assert _geometry_from_signal(SHORT_SIGNAL)["entry_signal_type"] == "short"
    assert "entry_signal_type" not in _geometry_from_signal(
        dict(LONG_SIGNAL, direction="sideways")
    )


# --- a 2.0.0-shaped bundle loads and scores ---------------------------------------


def _training_frame():
    """A tiny frame in the 2.0.0 basis, through the real _derive_features."""
    rows = []
    rng = np.random.default_rng(42)
    for i in range(40):
        rows.append(
            {
                "atr_value": 0.001 + 0.0001 * (i % 7),
                "adx_value": 15.0 + i % 25,
                "atr_sl_multiplier": 0.5 + 0.1 * (i % 10),
                "atr_tp_multiplier": (1.0 + 0.2 * (i % 8)) if i % 9 else np.nan,
                "regime_structural": ["Trending-Up", "Trending-Down", "Ranging"][i % 3],
                "entry_signal_type": ["long", "short"][i % 2],
            }
        )
    frame = T._derive_features(pd.DataFrame(rows))
    y = (rng.random(len(frame)) > 0.5).astype(int)
    y[:2] = [0, 1]  # both classes guaranteed
    return frame, y


@pytest.fixture(scope="module")
def v2_models_dir(tmp_path_factory):
    """A REAL fitted 2.0.0 bundle: T._make_preprocessor() (no strategy_id anywhere)
    plus a small XGB, dumped where Scorer expects the champion files."""
    from xgboost import XGBClassifier

    frame, y = _training_frame()
    cols = T.NUMERIC_DERIVED + T.CATEGORICAL
    pre = T._make_preprocessor().fit(frame[cols])
    model = XGBClassifier(
        n_estimators=5, max_depth=2, random_state=42, eval_metric="logloss"
    ).fit(pre.transform(frame[cols]), y)

    d = tmp_path_factory.mktemp("v2_bundle")
    joblib.dump(model, d / "champion_model.pkl")
    joblib.dump(pre, d / "champion_preprocessor.pkl")
    return str(d)


def test_a_2_0_0_bundle_loads_without_the_strategy_id_runtime_error(v2_models_dir):
    """strategy_id is absent from the artifact BY DESIGN (WO-04B); an empty
    known_strategies is its correct loaded state, not corruption."""
    scorer = Scorer(v2_models_dir)
    assert scorer.model is not None
    assert scorer.known_strategies == set()
    assert "strategy_id" not in list(scorer.preprocessor.feature_names_in_)


def test_a_2_0_0_bundle_scores_the_live_signal_shape(v2_models_dir):
    """The exact dict build_signals produces — no geometry columns by name — must
    score, not refuse MISSING_FEATURE. This is the whole of O-32."""
    scorer = Scorer(v2_models_dir)
    res = scorer.score(dict(LONG_SIGNAL))
    assert res["status"] == "scored", res
    assert 0.0 <= res["score"] <= 1.0
    res_short = scorer.score(dict(SHORT_SIGNAL))
    assert res_short["status"] == "scored", res_short


def test_a_2_0_0_bundle_scores_the_inverted_range_signal(v2_models_dir):
    """Where the signed rr is None. If the mapping had adopted build.py's definition,
    this signal would refuse — exactly the trade the model most needs to see."""
    scorer = Scorer(v2_models_dir)
    res = scorer.score(dict(INVERTED_SIGNAL))
    assert res["status"] == "scored", res


def test_a_2_0_0_bundle_does_not_gate_on_strategy_identity(v2_models_dir):
    """The identity gate belongs to bundles that consume strategy_id. A 2.0.0 never
    asked; refusing UNKNOWN_STRATEGY_ID here would refuse every live signal."""
    scorer = Scorer(v2_models_dir)
    res = scorer.score(dict(LONG_SIGNAL, strategy_id="999999"))
    assert res["status"] == "scored", res


def test_scoring_never_mutates_the_callers_signal_dict(v2_models_dir):
    """The caller's dict is the wire signal and System 3's contract is
    additionalProperties:false — leaked geometry keys would dead-letter it."""
    sig = dict(LONG_SIGNAL)
    before = dict(sig)
    Scorer(v2_models_dir).score(sig)
    assert sig == before


def test_a_2_0_0_signal_missing_its_inputs_still_refuses_missing_feature(
    v2_models_dir,
):
    """No entry/stop/target/atr means the geometry cannot be derived — the signal must
    stay unscorable (MISSING_FEATURE), never fabricated."""
    scorer = Scorer(v2_models_dir)
    sig = {
        k: v
        for k, v in LONG_SIGNAL.items()
        if k not in ("entry", "stop", "target", "atr")
    }
    res = scorer.score(sig)
    assert res["status"] == "refused"
    assert res["reason"].startswith("MISSING_FEATURE:")


# --- a genuinely corrupt 1.0.0 still refuses to load ------------------------------


def test_a_corrupt_1_0_0_bundle_still_raises_at_load(tmp_path):
    """The artifact's own feature list demands strategy_id but no categorical
    transformer carries its categories — the state the G2 guard exists for. Scoping
    the guard to 2.0.0 must not have disarmed it here."""
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import StandardScaler

    frame = pd.DataFrame(
        {"atr_value": [0.001, 0.002, 0.003], "strategy_id": [1.0, 2.0, 3.0]}
    )
    # strategy_id fed to a NUMERIC transformer: it appears in feature_names_in_ but no
    # transformer has categories_ for it — known_strategies cannot be resolved.
    pre = ColumnTransformer(
        [("num", StandardScaler(), ["atr_value", "strategy_id"])]
    ).fit(frame)
    assert "strategy_id" in list(pre.feature_names_in_)

    joblib.dump(object(), tmp_path / "champion_model.pkl")
    joblib.dump(pre, tmp_path / "champion_preprocessor.pkl")
    with pytest.raises(RuntimeError, match="strategy_id"):
        Scorer(str(tmp_path))


# --- the live 1.0.0 champion is untouched -----------------------------------------


def test_the_live_champion_score_is_unchanged_by_the_mapping():
    """The standing O-32 probe against the REAL local artifacts. Measured at
    0.4284968376159668 (task/OPEN.md records it rounded: 0.4285) immediately before
    the geometry mapping landed; the mapping is a no-op for a 1.0.0 basis, so the
    number must not move."""
    import os

    if not os.path.exists(os.path.join(T.MODELS_DIR, "champion_preprocessor.pkl")):
        pytest.skip("no live champion bundle on this machine")
    scorer = Scorer(T.MODELS_DIR)
    expected = list(scorer.preprocessor.feature_names_in_)
    if "strategy_id" not in expected:
        pytest.skip("local champion is not a 1.0.0 bundle; the pin no longer applies")

    probe = {
        "strategy_id": "58",
        "direction": "long",
        "entry": 1.3553,
        "stop": 1.3530,
        "target": 1.3600,
        "atr": 0.0012,
        "atr_value": 0.0012,
        "adx_value": 24.0,
        "regime_structural": "Trending-Up",
    }
    res = scorer.score(probe)
    assert res["status"] == "scored", res
    assert res["score"] == pytest.approx(0.4284968376159668, abs=1e-9)
