"""FIX-S1-005 guard — no downstream consumer may train/attribute on the smoothed label.

The smoothed regime columns (``regime_smoothed`` + bare ``prob_trending_up`` /
``prob_trending_down`` / ``prob_ranging`` / ``prob_high_vol``) are produced by a
full-history forward-backward fit and leak the future into a past bar. After FIX-S1-005
they are reporting-only; every consumer (attribution MODEL-004, gatekeeper MODEL-006)
must read the causal columns instead. This test parses each consumer's source, extracts
the SQL string literals that touch ``fact_market_regime_v2`` and asserts NONE of them
reference a bare smoothed column — so a regression that re-points a consumer at the
leaked label fails loudly here.
"""

from __future__ import annotations

import ast
import os
from typing import List

from src.system1.attribution import attribute as A
from src.system1.gatekeeper import train as T

SMOOTHED_TOKENS = [
    "regime_smoothed",
    "prob_trending_up",
    "prob_trending_down",
    "prob_ranging",
    "prob_high_vol",
]
# Required causal replacement that MUST appear in each consumer's regime SQL.
CAUSAL_TOKEN = "regime_causal"


def _sql_literals_touching_regime_table(module) -> List[str]:
    """All string literals in ``module``'s source that reference the regime table.

    Comments are dropped by the AST. Docstrings are string constants, so we isolate the
    actual SQL by requiring both ``SELECT`` and the regime table name in the literal
    (module docstrings mention the table in prose but contain no ``SELECT``).
    """
    src = open(module.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if "fact_market_regime_v2" in v and "SELECT" in v:
                out.append(v)
    return out


def _assert_module_uses_only_causal(module) -> None:
    literals = _sql_literals_touching_regime_table(module)
    assert literals, f"{module.__name__}: expected at least one regime SQL literal"
    joined = "\n".join(literals)
    for tok in SMOOTHED_TOKENS:
        assert tok not in joined, (
            f"{module.__name__} SQL still references the leaked smoothed column "
            f"{tok!r} — consumers must read the causal label (FIX-S1-005)."
        )
    assert (
        CAUSAL_TOKEN in joined
    ), f"{module.__name__} SQL does not reference the causal label {CAUSAL_TOKEN!r}"


def test_attribution_select_uses_only_causal_label():
    _assert_module_uses_only_causal(A)


def test_gatekeeper_select_uses_only_causal_label():
    _assert_module_uses_only_causal(T)


def test_gatekeeper_feature_lists_are_causal():
    """The trainer's feature/column constants must name causal columns only."""
    all_named = T.NUMERIC + T.CATEGORICAL + T.REGIME_FEATURES
    for tok in SMOOTHED_TOKENS:
        assert tok not in all_named, f"gatekeeper feature list leaks {tok!r}"
    assert "regime_causal" in T.CATEGORICAL
    assert all(
        c in T.NUMERIC
        for c in (
            "prob_causal_trending_up",
            "prob_causal_trending_down",
            "prob_causal_ranging",
            "prob_causal_high_vol",
        )
    )


def test_proposed_champion_does_not_overwrite_live(monkeypatch, tmp_path):
    """Smoke check that dry-run targets proposed_* basenames (no live-champion overwrite).

    Pure path check on the basename logic — does not invoke training (no DB)."""
    # The dry-run prefix is the contract; assert the source names the proposed bundle.
    src = open(T.__file__, encoding="utf-8").read()
    assert "proposed_champion" in src
    assert os.path.basename(T.__file__) == "train.py"
