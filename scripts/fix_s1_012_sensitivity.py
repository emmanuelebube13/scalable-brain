#!/usr/bin/env python
"""FIX-S1-012 — tau sensitivity report for the regime state→label mapping.

Read-only. Loads ``models/hmm_model.joblib`` for the fitted component means and prints,
for each granularity and each candidate ``tau``, what
:func:`src.system1.regime.mapping.map_states_to_labels` produces:

  * the label assigned to each state, with its mean direction value,
  * which of the four semantic labels end up UNUSED,
  * the resulting share of bars per label.

Per-state bar shares are taken from the label-distribution table in FIX-S1-012 §1 (the
2026-08-11 fit) and used as state weights — this script does **not** touch the database.

A second, clearly separated section reports the same table under a hypothetical
"trend-threshold-first, volatility-second" ordering. That is **measurement only** for the
deferred taxonomy question (fix doc §5 "Explicitly NOT in scope"); it is not wired into
production code and lives here rather than in ``src/``.

Usage (from the repo root, venv active):
    python scripts/fix_s1_012_sensitivity.py
    python scripts/fix_s1_012_sensitivity.py --stdout        # print instead of writing
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from typing import Dict, List

import joblib
import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.system1.regime import mapping as M  # noqa: E402

MODEL_PATH = os.path.join(_REPO_ROOT, "models", "hmm_model.joblib")
OUT_PATH = os.path.join(
    _REPO_ROOT,
    "docs",
    "proposed-fixes",
    "system-1",
    "FIX-S1-012-tau-sensitivity.txt",
)

TAUS: List[float] = [0.0, 0.10, 0.25, 0.50, 0.75]

# Share of bars per state, from the FIX-S1-012 §1 table (2026-08-11 fit). Used as the
# state weights so label shares can be reported without reading fact_market_regime_v2.
BAR_SHARES: Dict[str, Dict[int, float]] = {
    "D1": {0: 0.751, 1: 0.089, 3: 0.096, 2: 0.064},
    "H4": {2: 0.746, 0: 0.092, 1: 0.086, 3: 0.075},
    "H1": {3: 0.340, 0: 0.434, 1: 0.150, 2: 0.075},
}


def hypothetical_trend_first(
    means: np.ndarray,
    feature_names: List[str],
    direction_feature: str,
    tau: float,
) -> Dict[int, str]:
    """MEASUREMENT ONLY — the deferred "trend first, volatility second" taxonomy.

    Direction threshold is applied to *every* state first: ``> +tau`` → Trending-Up,
    ``< -tau`` → Trending-Down. Only the states left in the ``|d| <= tau`` band compete
    for High-Vol, which goes to the single highest ``volatility_20 + atr_14`` among them;
    the rest are Ranging. If no state is left in the band, High-Vol is unused.

    This is the ordering FIX-S1-012 §5 explicitly defers. It is NOT production behaviour
    and deliberately does not live in ``src/system1/regime/mapping.py``.
    """
    vol_i = feature_names.index("volatility_20")
    atr_i = feature_names.index("atr_14")
    ret_i = feature_names.index(direction_feature)
    vol_scores = means[:, vol_i] + means[:, atr_i]

    mapping: Dict[int, str] = {}
    undirected: List[int] = []
    for i in range(means.shape[0]):
        d = float(means[i, ret_i])
        if d > tau:
            mapping[i] = "Trending-Up"
        elif d < -tau:
            mapping[i] = "Trending-Down"
        else:
            undirected.append(i)
    if undirected:
        high_vol = max(undirected, key=lambda i: float(vol_scores[i]))
        for i in undirected:
            mapping[i] = "High-Vol" if i == high_vol else "Ranging"
    return dict(sorted(mapping.items()))


def _label_shares(mapping: Dict[int, str], shares: Dict[int, float]) -> Dict[str, float]:
    out = {label: 0.0 for label in M.SEMANTIC_ORDER}
    for state, label in mapping.items():
        out[label] += shares.get(state, 0.0)
    return out


def _render_block(
    out: io.StringIO,
    gran: str,
    means: np.ndarray,
    feature_names: List[str],
    direction_feature: str,
    shares: Dict[int, float],
    mapper,
) -> None:
    ret_i = feature_names.index(direction_feature)
    vol_i = feature_names.index("volatility_20")
    atr_i = feature_names.index("atr_14")
    n = means.shape[0]
    order = sorted(range(n), key=lambda i: -shares.get(i, 0.0))

    out.write(f"\n{gran}\n")
    out.write("-" * 78 + "\n")
    out.write("  states (sorted by share of bars)\n")
    out.write(
        f"    {'state':>5}  {direction_feature:>12}  {'vol+atr':>9}  {'share':>7}\n"
    )
    for i in order:
        out.write(
            f"    {i:>5}  {means[i, ret_i]:>+12.4f}  "
            f"{means[i, vol_i] + means[i, atr_i]:>9.3f}  "
            f"{shares.get(i, 0.0):>6.1%}\n"
        )

    out.write(
        "\n  label per state, and resulting share of bars per label\n"
    )
    out.write(
        f"    {'tau':>5}  "
        + "  ".join(f"s{i}".rjust(11) for i in order)
        + "  |  "
        + "  ".join(_SHORT[lbl].rjust(6) for lbl in M.SEMANTIC_ORDER)
        + "  |  unused labels\n"
    )
    out.write("    " + "-" * (7 + 13 * n + 40) + "\n")
    for tau in TAUS:
        mp = mapper(means, feature_names, direction_feature, tau)
        label_shares = _label_shares(mp, shares)
        used = set(mp.values())
        unused = [lbl for lbl in M.SEMANTIC_ORDER if lbl not in used]
        cells = "  ".join(_abbrev(mp[i]).rjust(11) for i in order)
        pct = "  ".join(f"{label_shares[lbl]:.1%}".rjust(6) for lbl in M.SEMANTIC_ORDER)
        out.write(
            f"    {tau:>5.2f}  {cells}  |  {pct}  |  "
            f"{', '.join(_SHORT[u] for u in unused) if unused else '(none)'}\n"
        )


_ABBREV = {
    "Trending-Up": "Trend-Up",
    "Trending-Down": "Trend-Down",
    "Ranging": "Ranging",
    "High-Vol": "High-Vol",
}
_SHORT = {
    "Trending-Up": "Tr-Up",
    "Trending-Down": "Tr-Dn",
    "Ranging": "Range",
    "High-Vol": "HiVol",
}


def _abbrev(label: str) -> str:
    return _ABBREV.get(label, label)


def build_report() -> str:
    bundle = joblib.load(MODEL_PATH)
    feature_names: List[str] = list(bundle["feature_names"])
    direction_feature: str = bundle["direction_feature"]

    out = io.StringIO()
    out.write("=" * 78 + "\n")
    out.write("FIX-S1-012 — tau sensitivity for the regime state->label mapping\n")
    out.write("=" * 78 + "\n")
    out.write(f"model      : {os.path.relpath(MODEL_PATH, _REPO_ROOT)}\n")
    out.write(f"version    : {bundle.get('model_version')}\n")
    out.write(f"direction  : {direction_feature} "
              f"(feature weight {bundle['feature_weights'][direction_feature]})\n")
    out.write(
        "units      : component means are in STANDARDISED and FEATURE-WEIGHTED space,\n"
        "             so tau=0.25 on a weight-3.0 trend_20 is ~0.083 SD of raw trend.\n"
    )
    out.write(
        "bar shares : from the FIX-S1-012 §1 label-distribution table (2026-08-11 fit);\n"
        "             no database was read to produce this report.\n"
    )
    out.write("read-only  : no fit, no DB write, model file untouched.\n")

    out.write("\n\n")
    out.write("#" * 78 + "\n")
    out.write("# SECTION 1 — PRODUCTION ordering: High-Vol first, then trend threshold\n")
    out.write("#   (this is what map_states_to_labels now does)\n")
    out.write("#" * 78 + "\n")

    def production(means, fn, df_, tau):
        return M.map_states_to_labels(means, fn, df_, tau=tau)

    for gran, entry in bundle["models"].items():
        model = entry["model"]
        means = getattr(model, "means_", None)
        if means is None:
            means = model.cluster_centers_
        _render_block(
            out, gran, np.asarray(means), feature_names, direction_feature,
            BAR_SHARES.get(gran, {}), production,
        )

    out.write("\n\n")
    out.write("#" * 78 + "\n")
    out.write("# SECTION 2 — HYPOTHETICAL ordering: trend threshold first, volatility\n")
    out.write("#   second. MEASUREMENT ONLY for the taxonomy question FIX-S1-012 §5\n")
    out.write("#   defers. NOT wired into production code. Rule: |d| > tau decides\n")
    out.write("#   direction for every state; only the leftover band competes for\n")
    out.write("#   High-Vol (highest vol+atr among them), the rest are Ranging.\n")
    out.write("#" * 78 + "\n")

    for gran, entry in bundle["models"].items():
        model = entry["model"]
        means = getattr(model, "means_", None)
        if means is None:
            means = model.cluster_centers_
        _render_block(
            out, gran, np.asarray(means), feature_names, direction_feature,
            BAR_SHARES.get(gran, {}), hypothetical_trend_first,
        )

    out.write("\n")
    return out.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser(description="FIX-S1-012 tau sensitivity report")
    ap.add_argument("--stdout", action="store_true", help="print instead of writing")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    report = build_report()
    if args.stdout:
        print(report)
        return
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"wrote {args.out} ({len(report)} chars)")


if __name__ == "__main__":
    main()
