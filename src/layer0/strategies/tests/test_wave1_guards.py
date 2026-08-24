"""Spec §9 #2 and #9 — the two structural guards the v2 build must never break.

1. **The incumbent path is frozen.** The v2 engine is a *parallel* path. The
   files that produced the live 134,520 ``fact_trade_outcomes`` rows, and the
   T6 sandbox that already has published verdicts on disk, must be untouched by
   this build. Byte-level, because "I only changed a comment" is how provenance
   is lost.

2. **Thresholds are imported, never copied.** A second copy of the gate numbers
   is a second qualification path waiting to drift. This has already been broken
   twice in this project's history — the T6 failure log records a reimplemented
   drawdown reporting MaxDD 1650%.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict

import pytest

from src.vetting.gates import GATES

REPO_ROOT = Path(__file__).resolve().parents[4]

#: SHA256 of every file the v2 build declares read-only (spec §1).
#: If one of these fails, the question is not "update the hash" — it is
#: "why did a parallel-path build modify the incumbent?". Update deliberately,
#: in the same change set that justifies the edit.
READONLY_SHA256: Dict[str, str] = {
    "src/layer0/core_engine/backtest_engine.py": "6864a3ddadeccc0b965f569bd85d1eefe2718f715dea6b66e22b23803e795226",
    "src/layer0/strategies/contract.py": "f59e0426b7a06c4f28ce3dcdb5e2868a471ba276dd36ed1b4e74384b39533313",
    "src/layer0/strategies/engine_adapter.py": "8c65fc4404d9e6b5b501578d6ae1afb158f9e3343301337c2cfb14008d3e6d6f",
    "src/layer0/strategies/promote.py": "2dc2cb6a1e2e3782e5358828a99a27c2ec496990b11125dce2fe5e76ad45b5c2",
    "src/layer0/strategies/registry.py": "dab8b90599fe44e744224e8d7782ed9771bf9d10ae19c3f9a21485e3f011417c",
    # research_data.py is deliberately NOT pinned: spec §7 requires adding "W1"
    # to _ALLOWED_GRANULARITIES, so it is a file this build is licensed to edit.
    # Its read-only guarantee is the narrower one asserted below — no write path.
    "src/vetting/gates.py": "2f1eeac175954075cd072c8ab89c9107eb413f899221eebfc028f3c1656669bb",
    "src/attribution/metrics.py": "a48c1e8ec9c4c028eb128988072e1971733000d2445d1e2b623a2ec6c203fc8d",
    "src/validation/walk_forward.py": "980810828dc31b3fedd67c5211d901d34dc21571a83cf753b334208f951e3693",
}

#: The modules this build added. Everything asserted below applies to these.
V2_MODULES = (
    "src/layer0/strategies/contract_v2.py",
    "src/layer0/strategies/position_engine.py",
    "src/layer0/strategies/causal_structure.py",
    "src/layer0/strategies/v2_harness.py",
)


@pytest.mark.parametrize("rel_path,expected", sorted(READONLY_SHA256.items()))
def test_readonly_incumbent_files_are_byte_identical(
    rel_path: str, expected: str
) -> None:
    path = REPO_ROOT / rel_path
    assert path.is_file(), f"{rel_path} is missing"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == expected, (
        f"{rel_path} was modified by the v2 build.\n"
        f"  expected {expected}\n  actual   {actual}\n"
        "The v2 engine is a PARALLEL path (spec §1). If this edit is intended, "
        "update READONLY_SHA256 in the same change set and say why."
    )


def test_research_data_is_readonly_and_now_allows_w1() -> None:
    """The one incumbent file this build may edit — but only in that one way.

    Its actual guarantee is stronger than a checksum: research reads, never
    writes. A write helper appearing here is a contamination path into the
    tables the live pipeline trains on.
    """
    from src.layer0.strategies import research_data as RD

    assert RD._ALLOWED_GRANULARITIES == {"H1", "H4", "D1", "W1"}

    src = (REPO_ROOT / "src/layer0/strategies/research_data.py").read_text().upper()
    for verb in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP ", "CREATE TABLE"):
        assert verb not in src, f"research_data.py grew a write path: {verb!r}"


def test_incumbent_does_not_import_the_v2_path() -> None:
    """Coupling in this direction would make the parallel path load-bearing."""
    banned = ("contract_v2", "position_engine", "causal_structure", "v2_harness")
    for rel_path in READONLY_SHA256:
        src = (REPO_ROOT / rel_path).read_text()
        for name in banned:
            if (
                rel_path == "src/layer0/strategies/registry.py"
                and name == "contract_v2"
            ):
                continue
            assert (
                f"import {name}" not in src and f"from .{name}" not in src
            ), f"{rel_path} imports {name} — the incumbent must not depend on v2"


@pytest.mark.parametrize("rel_path", V2_MODULES)
def test_no_gate_threshold_literals_in_v2_modules(rel_path: str) -> None:
    """None of the live gate numbers may be assigned as a literal in v2 code."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        pytest.skip(f"{rel_path} not present")
    src = path.read_text()
    for name, value in GATES.items():
        for literal in {str(value), f"{float(value):.1f}", f"{float(value):.2f}"}:
            assert f"= {literal}" not in src, (
                f"gate threshold {name}={value} appears as a literal assignment in "
                f"{rel_path} — import GATES from src.vetting.gates instead"
            )


def test_v2_qualification_imports_the_live_gates() -> None:
    """Whatever runs the gates must import them, not restate them."""
    harness = REPO_ROOT / "src/layer0/strategies/v2_harness.py"
    if not harness.is_file():
        pytest.skip("v2_harness.py not present")
    src = harness.read_text()
    assert "from src.vetting.gates import" in src
    assert "evaluate_gates" in src

    # Metrics must never be reimplemented (T6 failure log: a fresh drawdown
    # implementation reported MaxDD 1650%). Either import them directly, or —
    # better — reuse promote._aggregate_cell, which already routes every metric
    # through src.attribution.metrics.
    reuses_aggregator = "from .promote import _aggregate_cell" in src
    imports_metrics = "from src.attribution" in src
    assert reuses_aggregator or imports_metrics, (
        "v2_harness must reuse promote._aggregate_cell or import "
        "src.attribution.metrics — never restate metric math"
    )

    # Whichever route, no metric may be recomputed locally.
    for banned in ("def profit_factor", "def max_drawdown", "def annualized_sharpe"):
        assert banned not in src, f"v2_harness reimplements {banned!r}"
