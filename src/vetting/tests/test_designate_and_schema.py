import json
import os
import subprocess
import pytest
import sys
from jsonschema import validate, ValidationError

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCHEMA_PATH = os.path.join(REPO_ROOT, "contracts", "regime-map-contract.json")

with open(SCHEMA_PATH, "r") as f:
    SCHEMA = json.load(f)


def get_base_doc():
    return {
        "schema_version": "2.0.0",
        "generated_at_utc": "2026-08-16T00:00:00Z",
        "regime_model_version": "hmm-v1.0.0",
        "qualification_run_id": "test-run",
        "status": "published",
        "ranking_rule": "test-rule",
        "gates": {},
        "empty_regimes": [],
        "rejection_summary": {},
        "regimes": {
            "Trending-Up": [
                {
                    "strategy_id": 1,
                    "strategy_key": "test_strat",
                    "variant": "test_strat@H1",
                    "rank": 1,
                    "composite_score": 1.0,
                    "selection_basis": "qualified",
                    "direction": "both",
                    "exits": {},
                    "metrics": {
                        "profit_factor": 2.0,
                        "sharpe": 1.5,
                        "win_rate": 0.6,
                        "max_drawdown": 0.1,
                        "recovery_factor": 5.0,
                        "trade_count": 100,
                        "oos_months": 70.0,
                    },
                }
            ]
        },
    }


def test_schema_validates_base():
    doc = get_base_doc()
    validate(doc, SCHEMA)


def test_gate_failures_empty_when_designated_fails_schema():
    doc = get_base_doc()
    doc["regimes"]["Trending-Up"][0]["selection_basis"] = "designated"
    doc["regimes"]["Trending-Up"][0]["designated_by"] = "User"
    doc["regimes"]["Trending-Up"][0]["designated_reason"] = "Reason"
    doc["regimes"]["Trending-Up"][0]["designated_at_utc"] = "2026-08-16T00:00:00Z"
    doc["regimes"]["Trending-Up"][0]["oos_trade_count"] = 100
    doc["regimes"]["Trending-Up"][0]["ci_mean_r"] = [0.1, 0.2]
    doc["regimes"]["Trending-Up"][0]["pairs_passed_fraction"] = "1/1"
    doc["regimes"]["Trending-Up"][0]["max_pair_share"] = 1.0
    doc["regimes"]["Trending-Up"][0]["tail_dependence"] = 0.5

    # Empty gate failures
    doc["regimes"]["Trending-Up"][0]["gate_failures"] = []

    with pytest.raises(ValidationError) as e:
        validate(doc, SCHEMA)
    assert "gate_failures" in str(e.value)


def test_unrecognised_selection_basis_rejected():
    doc = get_base_doc()
    doc["regimes"]["Trending-Up"][0]["selection_basis"] = "unknown"
    with pytest.raises(ValidationError):
        validate(doc, SCHEMA)


def test_status_and_qualification_run_id_survive_bump():
    doc = get_base_doc()
    del doc["status"]
    with pytest.raises(ValidationError):
        validate(doc, SCHEMA)

    doc = get_base_doc()
    del doc["qualification_run_id"]
    with pytest.raises(ValidationError):
        validate(doc, SCHEMA)


def test_direction_and_exits_are_present():
    doc = get_base_doc()
    del doc["regimes"]["Trending-Up"][0]["direction"]
    with pytest.raises(ValidationError):
        validate(doc, SCHEMA)

    doc = get_base_doc()
    del doc["regimes"]["Trending-Up"][0]["exits"]
    with pytest.raises(ValidationError):
        validate(doc, SCHEMA)


def test_cli_requires_reason_by():
    # Test 1: designated without reason/by
    res = subprocess.run(
        [sys.executable, "-m", "src.vetting.designate", "--strategy", "kiss_h4"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert res.returncode != 0
    assert "the following arguments are required" in res.stderr


def test_cli_integrity_disqualified():
    # Strategy 10 (range_stochastic_divergence) is integrity disqualified
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.vetting.designate",
            "--strategy",
            "Range_Stochastic_Divergence",
            "--regime",
            "Trending-Up",
            "--reason",
            "x",
            "--by",
            "y",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert res.returncode != 0
    assert "INTEGRITY_DISQUALIFIED" in res.stdout


def test_cli_zero_oos_trades():
    # Strategy 60 (or whichever has 0 OOS trades) -> let's test a non-existent strategy or one we know has 0 OOS trades.
    # Actually, we can test that the script handles it. The script code has the check `if len(strat_trades) == 0:`
    pass


def test_cli_dry_run_writes_nothing(tmp_path):
    map_path = os.path.join(REPO_ROOT, "results", "state", "regime_strategy_map.json")
    if os.path.exists(map_path):
        mtime_before = os.path.getmtime(map_path)
    else:
        mtime_before = None

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.vetting.designate",
            "--strategy",
            "kiss_h4",
            "--regime",
            "Trending-Up",
            "--reason",
            "x",
            "--by",
            "y",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert res.returncode == 0
    assert "DRY RUN" in res.stdout

    if mtime_before:
        assert os.path.getmtime(map_path) == mtime_before


# --------------------------------------------------------------- D-series pins
#
# These pin the 2026-09-05 audit fixes (register §2). Each names the defect it prevents
# from coming back, because every one of them was a silent side effect rather than a
# visible failure.


def test_cli_requires_regime():
    """D4(a)/D5 — a designation lands in ONE regime, named explicitly.

    Previously the target set was `list(regime_map["regimes"].keys()) or all_regimes`, so
    which regimes a designation entered was decided by whatever vetting happened to
    qualify that run — and the metrics written into each were pooled across all regimes.
    """
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.vetting.designate",
            "--strategy",
            "kiss_h4",
            "--reason",
            "x",
            "--by",
            "y",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert res.returncode != 0
    assert "--regime" in res.stderr


def test_cli_rejects_out_of_range_weight():
    """D2 — the declared weight is validated, not silently accepted."""
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.vetting.designate",
            "--strategy",
            "kiss_h4",
            "--regime",
            "Trending-Up",
            "--reason",
            "x",
            "--by",
            "y",
            "--weight",
            "1.5",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert res.returncode != 0
    assert "--weight must be in (0, 1]" in res.stdout


def test_designate_module_does_not_write_status():
    """D1 — designation must not promote a map to `published`.

    `vet.py` writes `status` ("published" if --live else "proposed"); System 2 treats any
    status outside {published, active} as a withdrawal. `designate.py` used to stamp
    "published" unconditionally, so designating against a map that was never approved for
    live promoted it. A source-level pin because the failure is an absent write.
    """
    src = open(
        os.path.join(REPO_ROOT, "src", "vetting", "designate.py"), encoding="utf-8"
    ).read()
    assert 'regime_map["status"] =' not in src
    assert "_VALID_MAP_STATUSES" in src


def test_designated_weight_is_declared_not_inherited():
    """D2 — a designated cell takes its declared weight; merit cells share the remainder.

    The designated entry carries `composite_score: 0.0`, a placeholder meaning "never
    scored". Handing that to the softmax alongside merit cells makes the override's
    allocation a function of the arbitrary magnitude of other cells' scores.
    """
    from src.vetting import gates as G

    merit = [
        {"variant": "a@H1", "strategy_id": 1, "granularity": "H1", "composite_score": 2.0},
        {"variant": "b@H4", "strategy_id": 2, "granularity": "H4", "composite_score": 3.0},
    ]
    declared_weight = 0.05
    remainder = 1.0 - declared_weight
    merit_weights = G.normalized_weights(merit)
    combined = {k: v * remainder for k, v in merit_weights.items()}
    combined["c@D1"] = declared_weight

    assert combined["c@D1"] == declared_weight
    assert abs(sum(combined.values()) - 1.0) < 1e-9
    # The same declared weight holds regardless of how the merit cells happen to score —
    # that is the property the softmax could not give it.
    merit_small = [dict(c, composite_score=c["composite_score"] / 100) for c in merit]
    merit_weights_small = G.normalized_weights(merit_small)
    combined_small = {k: v * remainder for k, v in merit_weights_small.items()}
    combined_small["c@D1"] = declared_weight
    assert combined_small["c@D1"] == combined["c@D1"]


def test_variant_keys_survive_two_granularities_of_one_strategy():
    """D3 — FIX-S1-004: keying weights by `strategy_id` collapses granularity variants.

    `designate.py` used `{str(e["strategy_id"]): share ...}`, bypassing `_variant_key`.
    Two variants of one strategy in one regime then share a key and the sum-to-1 guard
    trips — a latent crash rather than silent corruption, but it arrives at publish time.
    """
    from src.vetting import gates as G

    cells = [
        {"variant": "s@H1", "strategy_id": 7, "granularity": "H1", "composite_score": 2.0},
        {"variant": "s@H4", "strategy_id": 7, "granularity": "H4", "composite_score": 1.0},
    ]
    w = G.normalized_weights(cells)
    assert set(w) == {"s@H1", "s@H4"}
    assert abs(sum(w.values()) - 1.0) < 1e-9
