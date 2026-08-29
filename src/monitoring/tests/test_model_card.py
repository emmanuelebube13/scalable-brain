"""Model-card pure-computation tests (no DB, no network, no model artifact).

The defect these guard against is not a crash — it is a *plausible wrong number*. A
flatlined calibration curve and a 0.0% metric column both rendered without error for
weeks. So the assertions here are mostly about missing data staying missing.
"""

from __future__ import annotations

import pytest

from src.monitoring import model_card as mc
from src.monitoring.model_card import (
    METRIC_SEMANTICS,
    aggregate_importance,
    brier_score,
    collapse_encoded_name,
    live_map_coverage,
    operating_point_metrics,
    reliability_bins,
)


# --- name collapsing -------------------------------------------------------------------
def test_collapse_strips_transformer_prefix_and_onehot_suffix():
    assert collapse_encoded_name("num__atr_value") == "atr_value"
    assert collapse_encoded_name("cat__strategy_id_12") == "strategy_id"
    assert collapse_encoded_name("cat__regime_causal_Trending-Down") == "regime_causal"
    assert collapse_encoded_name("cat__entry_signal_type_market") == "entry_signal_type"


def test_collapse_does_not_mangle_an_unprefixed_name():
    assert collapse_encoded_name("adx_over_atr") == "adx_over_atr"


# --- importance aggregation ------------------------------------------------------------
def test_onehot_columns_sum_back_onto_their_source_feature():
    names = ["num__atr_value", "cat__strategy_id_1", "cat__strategy_id_2"]
    out = aggregate_importance({"f0": 10.0, "f1": 60.0, "f2": 30.0}, names)
    ranked = {f["feature"]: f["importance"] for f in out["features"]}
    assert ranked["strategy_id"] == 0.9  # 60 + 30 of 100
    assert ranked["atr_value"] == 0.1
    assert out["features"][0]["feature"] == "strategy_id"  # sorted by importance


def test_unsplit_columns_are_reported_as_zero_not_omitted():
    """A feature the booster ignored must say 0.0. Omitting it lets a renderer infer
    'no data' about a feature we measured precisely and found worthless."""
    names = ["num__atr_value", "num__adx_value"]
    out = aggregate_importance({"f0": 5.0}, names)
    ranked = {f["feature"]: f["importance"] for f in out["features"]}
    assert ranked["adx_value"] == 0.0
    assert ranked["atr_value"] == 1.0


def test_zero_total_gain_reports_unavailable_rather_than_a_flat_chart():
    out = aggregate_importance({}, ["num__atr_value"])
    assert out["available"] is False
    assert "reason" in out


def test_importance_is_normalised_to_one():
    names = ["num__a", "num__b", "num__c"]
    out = aggregate_importance({"f0": 1.0, "f1": 2.0, "f2": 7.0}, names)
    assert abs(sum(f["importance"] for f in out["features"]) - 1.0) < 1e-9


# --- reliability bins ------------------------------------------------------------------
def test_empty_bins_carry_null_not_zero():
    """The bug this replaces: an unpopulated bucket plotted at 0% actual win rate, which
    reads as 'the model is always wrong' rather than 'nothing landed here'."""
    bins = reliability_bins([0.85, 0.86], [1, 0])
    empty = [b for b in bins if b["n"] == 0]
    assert empty, "expected unpopulated buckets"
    assert all(b["observed_win_rate"] is None for b in empty)
    assert all(b["mean_predicted"] is None for b in empty)


def test_populated_bin_reports_observed_rate():
    bins = reliability_bins([0.85, 0.86, 0.87, 0.88], [1, 1, 1, 0])
    top = [b for b in bins if b["bin_lower"] == 0.8][0]
    assert top["n"] == 4
    assert top["observed_win_rate"] == 0.75


def test_probability_of_exactly_one_lands_in_the_top_bin():
    bins = reliability_bins([1.0], [1])
    assert sum(b["n"] for b in bins) == 1
    assert [b for b in bins if b["bin_lower"] == 0.9][0]["n"] == 1


def test_every_observation_is_binned_exactly_once():
    probs = [i / 100 for i in range(101)]
    bins = reliability_bins(probs, [1] * 101)
    assert sum(b["n"] for b in bins) == 101


# --- operating-point metrics -----------------------------------------------------------
def test_precision_and_recall_at_the_shipped_operating_point():
    approved = [1, 1, 1, 0]
    outcomes = [1, 0, 0, 1]
    m = operating_point_metrics(approved, outcomes, [1.0, -1.0, -1.0, 1.0])
    assert m["n_approved"] == 3
    assert m["precision"] == round(1 / 3, 6)  # 1 winner of 3 approved
    assert m["recall"] == 0.5  # 1 of 2 winners approved
    assert m["approval_rate"] == 0.75


def test_no_approvals_yields_null_precision_not_zero():
    """Zero approvals means precision is undefined. Reporting 0.0 would claim the gate
    approved trades and got them all wrong."""
    m = operating_point_metrics([0, 0], [1, 0], [1.0, -1.0])
    assert m["precision"] is None
    assert m["f1"] is None
    assert m["n_approved"] == 0


def test_expectancy_is_computed_over_approved_trades_only():
    m = operating_point_metrics([1, 0], [1, 0], [2.0, -10.0])
    assert m["expectancy_r_approved"] == 2.0
    assert m["expectancy_r_all"] == -4.0


def test_empty_input_does_not_raise():
    m = operating_point_metrics([], [], [])
    assert m["n"] == 0
    assert m["precision"] is None
    assert m["approval_rate"] is None


# --- brier -----------------------------------------------------------------------------
def test_brier_is_zero_for_perfect_confident_predictions():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0


def test_brier_penalises_confident_and_wrong():
    assert brier_score([1.0], [0]) == 1.0


def test_brier_of_no_observations_is_null():
    assert brier_score([], []) is None


# --- live map vs gatekeeper cross-check --------------------------------------------------
_MAP = {
    "regimes": {
        "Trending-Up": [
            {"strategy_id": 58, "strategy_key": "xard", "selection_basis": "designated"}
        ],
        "High-Vol": [
            {
                "strategy_id": 56,
                "strategy_key": "gap_fade",
                "selection_basis": "ranked",
            },
            {
                "strategy_id": 55,
                "strategy_key": "weekly_rev",
                "selection_basis": "ranked",
            },
        ],
    }
}


def test_a_cell_with_no_published_approval_rate_is_unmeasured_not_zero():
    """MIN_REGIME_N excludes thin cells from the manifest. Absent must not become 0.0 —
    'we never measured this' and 'this never approves' need different responses."""
    cov = live_map_coverage(_MAP, {"58|Trending-Up": 0.0, "56|High-Vol": 0.09})
    by_key = {(c["strategy_id"], c["regime"]): c for c in cov["cells"]}
    assert by_key[(55, "High-Vol")]["state"] == "unmeasured"
    assert by_key[(55, "High-Vol")]["gatekeeper_approval"] is None
    assert cov["n_unmeasured"] == 1


def test_a_zero_approval_cell_is_flagged_as_always_rejected():
    cov = live_map_coverage(_MAP, {"58|Trending-Up": 0.0, "56|High-Vol": 0.09})
    by_key = {(c["strategy_id"], c["regime"]): c for c in cov["cells"]}
    assert by_key[(58, "Trending-Up")]["state"] == "always_rejected"
    assert cov["n_always_rejected"] == 1
    assert cov["tradeable_cells"] == 1  # only 56|High-Vol can actually fire


def test_coverage_counts_sum_to_the_cell_total():
    cov = live_map_coverage(_MAP, {"58|Trending-Up": 0.0, "56|High-Vol": 0.09})
    assert (
        cov["n_unmeasured"] + cov["n_always_rejected"] + cov["tradeable_cells"]
        == cov["n_cells"]
        == 3
    )


def test_an_empty_map_does_not_raise():
    cov = live_map_coverage({}, {})
    assert cov["n_cells"] == 0


# --- semantics contract ----------------------------------------------------------------
def test_recall_is_declared_unmeasurable_live():
    """Live recall is pinned at 1.0 because rejected signals never become trades. The
    payload must say so; the dashboard drew 100.0% and it was read as a finding."""
    assert METRIC_SEMANTICS["recall"]["measurable_live"] is False
    assert METRIC_SEMANTICS["f1"]["measurable_live"] is False


def test_brier_direction_is_declared_lower_is_better():
    assert METRIC_SEMANTICS["brier"]["direction"] == "LOWER_is_better"
    assert METRIC_SEMANTICS["precision"]["direction"] == "higher_is_better"


def test_expectancy_is_declared_an_r_multiple_not_a_percentage():
    assert METRIC_SEMANTICS["expectancy_r"]["format"] == "r_multiple"


# --- reproducibility quarantine (requirement 4) -------------------------------------------
class _Frame:
    """Minimal stand-in for the joined frame — only what _training_data reads.

    The column names are the ones ``train.build_frame`` actually emits: plain
    ``asset_id`` / ``granularity``, not the ``_x`` suffixes an earlier version of this
    stub carried. Both point-in-time joins select a non-overlapping right-hand side, so
    ``merge_asof`` never suffixes them. Verified against the live frame (18,023 rows).
    A stub that fakes a column name the real frame does not have tests nothing.
    """

    def __init__(self, rows: int):
        self._rows = rows

    def __len__(self):
        return self._rows

    def __getitem__(self, col):
        import pandas as pd

        if col == "entry_time":
            return pd.Series(pd.to_datetime(["2024-08-23T03:00:00Z"] * self._rows))
        if col == "asset_id":
            return pd.Series([1] * self._rows)
        if col == "granularity":
            return pd.Series(["H1"] * self._rows)
        if col == "strategy_id":
            return pd.Series(["12"] * self._rows)
        if col == "is_winner":
            return pd.Series([1, 0] * (self._rows // 2) or [1])
        raise KeyError(col)


@pytest.fixture
def offline_symbols(monkeypatch):
    """Keep this module's no-DB promise real.

    ``_training_data`` resolves surrogate asset ids through ``dim_asset``. It already
    falls back to stringified ids when the lookup fails, so these tests pass either way
    — which is exactly the problem: on a machine with the database up they would open a
    connection and nobody would notice the dependency until CI had none.
    """
    monkeypatch.setattr(mc, "_asset_symbols", lambda ids: ["EUR_USD"])


def test_a_count_that_matches_the_frame_is_published_as_verified(offline_symbols):
    out = mc._training_data({"n_train": 10, "calibration": {}}, _Frame(10))
    assert out["verified"]["pairs"] == ["EUR_USD"]
    assert out["verified"]["rows"] == 10
    assert out["verified"]["n_train"] == 10
    assert out["verified"]["reproducible"] is True
    assert "unverified" not in out


def test_a_count_that_does_not_match_the_frame_is_quarantined_and_flagged(
    offline_symbols,
):
    """n_train=92994 against an 18023-row frame is the live case. It must never appear as
    a plain field a renderer could mistake for a measured one."""
    out = mc._training_data({"n_train": 92994, "calibration": {}}, _Frame(18024))
    assert "n_train" not in out["verified"]
    entry = out["unverified"]["n_train"]
    assert entry["reproducible"] is False
    assert entry["claimed"] == 92994
    assert entry["measured"] == 18024
    assert "warning" in out


def test_counts_with_no_frame_equivalent_are_quarantined_not_shown(offline_symbols):
    """n_fit/n_calibration describe a split of a frame that cannot be rebuilt, so they are
    unverifiable by construction rather than merely mismatched."""
    out = mc._training_data(
        {"n_train": 10, "calibration": {"n_fit": 8, "n_calibration": 2}}, _Frame(10)
    )
    assert out["unverified"]["n_fit"]["reproducible"] is False
    assert out["unverified"]["n_fit"]["measured"] is None
    assert "n_fit" not in out["verified"]


def test_no_unverified_number_ever_escapes_into_the_verified_block(offline_symbols):
    out = mc._training_data(
        {"n_train": 92994, "calibration": {"n_fit": 74395, "n_calibration": 18599}},
        _Frame(18024),
    )
    for name in ("n_train", "n_fit", "n_calibration"):
        assert name not in out["verified"], f"{name} leaked out of quarantine"
        assert out["unverified"][name]["reproducible"] is False


# --- atomicity: the card is structurally part of the set ----------------------------------
def test_model_card_is_a_required_artifact_of_every_model_set():
    """This listing is the whole enforcement mechanism: _collect() aborts the publish when
    a named artifact is absent, so a set cannot reach the pointer without its card."""
    from src.serializer.publish_model_set import S1_ARTIFACTS

    assert mc.CARD_ARTIFACT_NAME in S1_ARTIFACTS


def test_build_refuses_when_the_set_is_missing_an_artifact():
    """No degraded card. A set that cannot be fully described must not ship at all."""

    class _Storage:
        def get_object(self, key, local):
            raise AssertionError("should not be reached")

    pointer = {"model_set_id": "x", "artifacts": [{"name": "champion_model.pkl"}]}
    with pytest.raises(mc.ModelCardRefused) as exc:
        mc.build(_Storage(), pointer)
    assert "missing" in str(exc.value)


def test_pinned_card_carries_no_wall_clock_field():
    """A clock reading inside the card would change its SHA256 on every build, breaking
    both manifest-digest stability and publish idempotency."""
    import inspect

    src = inspect.getsource(mc.build)
    assert '"as_of"' not in src


def _sample_identity():
    return mc._identity(
        {
            "model_set_id": "s1_gk-abc",
            "published_at": "2026-08-23T18:12:54Z",
            "status": "published",
            "code_commit": "deadbeef",
        },
        {"created_at_utc": "2026-08-20T21:25:57Z"},
    )


def test_publish_event_fields_are_excluded_from_the_pinned_card():
    identity = _sample_identity()
    for field in ("model_set_published_at", "model_set_status", "code_commit"):
        assert field not in identity
    assert identity["model_set_id"] == "s1_gk-abc"
    assert identity["trained_at_utc"] == "2026-08-20T21:25:57Z"


def test_identity_carries_no_short_string_that_is_really_an_instruction():
    """A `label_this_page_with: "gatekeeper_version + trained_at_utc"` field shipped once
    and the dashboard rendered its value straight into the VERSION tile. Guidance goes in
    `note` (unmistakably prose); every other value here must be renderable as-is."""
    identity = _sample_identity()
    assert "label_this_page_with" not in identity
    for key, value in identity.items():
        if key == "note" or not isinstance(value, str):
            continue
        assert "_version" not in value and " + " not in value, (
            f"identity[{key!r}] = {value!r} names other fields — it reads as an "
            f"instruction, and a renderer cannot tell it from a value"
        )
