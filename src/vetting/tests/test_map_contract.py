"""R1 — the regime map's provenance contract, freeze switch and routing admissibility.

What these tests are actually defending
---------------------------------------
On 2026-08-24 a regime map selected under the HMM's ``regime_causal`` was published and
then executed against the **structural** label. Their agreement is 19-36% with kappa near
zero, so every cell in that map authorised a strategy under conditions that never fired it.

Nothing detected this, and the reason is precise: the artifact did not record which label
it had been selected under, so there was no assumption written down that could be checked.
The map also had no expiry, so when the labelling job stalled on 2026-08-24 the map simply
kept trading for the next twelve days.

Both of those are now refusals. The tests below exist so that neither can be quietly
reintroduced — particularly :func:`test_the_actual_2026_08_24_map_is_refused`, which runs
the real published artifact through the real check.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from src.vetting import map_contract as MC

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _map(**overrides):
    """An admissible map, mutated by whatever a test overrides."""
    m = {
        "regimes": {"Trending-Up": [{"strategy_id": 1}]},
        **MC.provenance_header(
            run_id="run-1",
            source_label=MC.ROUTING_SOURCE_LABEL,
            labeller_version="structural-v1.0.0",
            built_at=NOW - timedelta(days=1),
        ),
    }
    m.update(overrides)
    return m


# --------------------------------------------------------------------------- #
# The freeze (R1.1)
# --------------------------------------------------------------------------- #
def test_writes_are_frozen_by_default(monkeypatch):
    """Absent configuration, the answer is NO. Fail-closed applies to writes too."""
    monkeypatch.delenv("REGIME_MAP_WRITES_FROZEN", raising=False)
    assert MC.map_writes_frozen() is True
    with pytest.raises(MC.MapWritesFrozen):
        MC.assert_map_writes_allowed("vet --live")


def test_freeze_names_the_blocked_caller(monkeypatch):
    """A refusal that does not say what it blocked sends the reader hunting."""
    monkeypatch.delenv("REGIME_MAP_WRITES_FROZEN", raising=False)
    with pytest.raises(MC.MapWritesFrozen, match="vetting.designate"):
        MC.assert_map_writes_allowed("vetting.designate")


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no"])
def test_freeze_can_be_lifted_deliberately(monkeypatch, value):
    monkeypatch.setenv("REGIME_MAP_WRITES_FROZEN", value)
    assert MC.map_writes_frozen() is False
    MC.assert_map_writes_allowed("vet --live")  # must not raise


@pytest.mark.parametrize("value", ["true", "yes", "1", "", "banana"])
def test_anything_that_is_not_explicitly_false_stays_frozen(monkeypatch, value):
    """A typo in the override must fail SAFE, not silently unfreeze the map."""
    monkeypatch.setenv("REGIME_MAP_WRITES_FROZEN", value)
    assert MC.map_writes_frozen() is True


# --------------------------------------------------------------------------- #
# Provenance (R1.2)
# --------------------------------------------------------------------------- #
def test_provenance_header_carries_every_required_field():
    h = MC.provenance_header(
        run_id="r", source_label="regime_structural", labeller_version="v1"
    )
    for field in MC.REQUIRED_PROVENANCE_FIELDS:
        assert field in h, f"provenance header is missing {field}"


def test_expiry_is_built_at_plus_max_age():
    built = NOW
    h = MC.provenance_header(
        run_id="r",
        source_label="regime_structural",
        labeller_version="v1",
        built_at=built,
        max_age_days=7,
    )
    assert datetime.fromisoformat(h["expires_at_utc"]) == built + timedelta(days=7)


def test_git_sha_is_none_or_a_sha_never_a_placeholder():
    """An absent provenance value must read as absent, not as a fake commit."""
    sha = MC.git_sha()
    assert sha is None or (len(sha) == 40 and all(c in "0123456789abcdef" for c in sha))


# --------------------------------------------------------------------------- #
# Admissibility (R1.3)
# --------------------------------------------------------------------------- #
def test_a_well_formed_current_matching_map_is_admissible():
    assert MC.routing_refusals(_map(), now=NOW) == []


def test_missing_map_is_refused():
    assert MC.routing_refusals(None, now=NOW) == ["map is missing or unparseable"]
    assert MC.routing_refusals({}, now=NOW) == ["map is missing or unparseable"]


def test_label_mismatch_is_refused():
    """THE defect. A map selected on the HMM label may not route structural signals."""
    refusals = MC.routing_refusals(_map(source_label="regime_causal"), now=NOW)
    assert any(
        "SELECTED under" in r and "ROUTED under" in r for r in refusals
    ), refusals


def test_expired_map_is_refused():
    m = _map(
        **MC.provenance_header(
            run_id="r",
            source_label=MC.ROUTING_SOURCE_LABEL,
            labeller_version="v1",
            built_at=NOW - timedelta(days=30),
        )
    )
    refusals = MC.routing_refusals(m, now=NOW)
    assert any("expired" in r for r in refusals), refusals
    assert any("days old" in r for r in refusals), refusals


def test_map_older_than_max_age_is_refused_even_without_an_expiry_field():
    """Age is checked independently, so a map cannot buy time by omitting its expiry."""
    m = _map(built_at_utc=(NOW - timedelta(days=9)).isoformat())
    m.pop("expires_at_utc")
    refusals = MC.routing_refusals(m, now=NOW)
    assert any("days old" in r for r in refusals), refusals


def test_each_missing_provenance_field_is_refused():
    for field in MC.REQUIRED_PROVENANCE_FIELDS:
        m = _map()
        m.pop(field)
        refusals = MC.routing_refusals(m, now=NOW)
        assert any(field in r for r in refusals), f"{field} removal was not refused"


def test_naive_timestamps_are_refused_not_assumed_utc():
    """Assuming naive == UTC would silently shift expiry by the local offset.

    On a host at UTC-3 that would grant a dead map three extra hours of life, which is
    exactly the kind of small, invisible leniency this module exists to remove.
    """
    m = _map(built_at_utc="2026-09-05T12:00:00")  # no offset
    refusals = MC.routing_refusals(m, now=NOW)
    assert any("naive" in r for r in refusals), refusals


def test_unrecognised_source_label_is_refused_not_assumed_compatible():
    refusals = MC.routing_refusals(_map(source_label="regime_vibes"), now=NOW)
    assert any("not a recognised label" in r for r in refusals), refusals


def test_all_reasons_are_reported_not_just_the_first():
    """One run's log should say everything that is wrong, not one defect per deploy."""
    m = _map(source_label="regime_causal")
    m["built_at_utc"] = (NOW - timedelta(days=40)).isoformat()
    m["expires_at_utc"] = (NOW - timedelta(days=33)).isoformat()
    refusals = MC.routing_refusals(m, now=NOW)
    assert len(refusals) >= 3, refusals


def test_a_map_with_no_regimes_is_refused():
    """An empty map routes nothing anyway, but it must SAY so rather than look normal."""
    refusals = MC.routing_refusals(_map(regimes={}), now=NOW)
    assert any("regimes" in r for r in refusals), refusals


# --------------------------------------------------------------------------- #
# The regression pin: the real artifact that was trading
# --------------------------------------------------------------------------- #
def test_the_actual_2026_08_24_map_is_refused():
    """The genuine published map from the incident, run through the real check.

    Synthetic fixtures prove the logic; this proves the logic catches the thing that
    actually happened. If this ever starts passing, the guard has been defeated.
    """
    path = os.path.join(
        _REPO_ROOT, "audit", "baseline", "regime_strategy_map_pre_R2_PUBLISHED.json"
    )
    if not os.path.exists(
        path
    ):  # pragma: no cover - evidence file not kept in all trees
        pytest.skip("pre-R2 published map snapshot not present")
    with open(path, encoding="utf-8") as fh:
        live_map = json.load(fh)

    refusals = MC.routing_refusals(live_map, now=NOW)
    assert refusals, "the map that caused the incident was judged admissible"
    # It carries no provenance at all, so the refusal is on the missing block.
    assert any("provenance" in r for r in refusals), refusals
