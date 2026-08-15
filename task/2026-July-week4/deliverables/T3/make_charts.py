"""T3 deliverable charts — all values measured, none illustrative.

`gates_dashboard.png` reads the real gate evaluation
(`results/state/t3_evidence_20260729.json`) produced by running the actual
pipeline and the actual `deployment_gates()` against the live GCS incumbent.

`map_diff_heatmap.png` compares the regenerated strategy map against the live
one (git HEAD), across the full 10-strategy x 4-regime grid.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
EVIDENCE = REPO / "results" / "state" / "t3_evidence_20260729.json"

INK = "#1f2933"
MUTED = "#7b8794"
RED = "#c0392b"
AMBER = "#b9770e"
GREEN = "#1e8449"
BLUE = "#2471a3"
PALE = "#eef1f4"

# The 10 strategies the qualification engine evaluates, in roster order.
STRATEGIES = [
    "Trend_EMA_ADX_H1", "Trend_EMA_ADX_H4", "Trend_EMA_ADX_MultiTF",
    "Trend_Donchian_H1", "Trend_Donchian_H4", "Trend_Donchian_VCP",
    "Range_Bollinger_H1", "Range_Bollinger_H4", "Range_Bollinger_Aggressive",
    "Range_Stochastic_Divergence",
]
REGIMES = ["Trending-Up", "Trending-Down", "Ranging", "High-Vol"]


def chart_gates_dashboard():
    ev = json.loads(EVIDENCE.read_text())
    cand, gates = ev["candidate"], ev["gates"]
    detail = gates["beats_incumbent_detail"]
    thr = ev["thresholds"]

    # (label, measured, threshold, passed, note)
    rows = [
        ("regime_accuracy", cand["regime_accuracy"], thr["REGIME_ACCURACY_FLOOR"],
         gates["regime_accuracy_ok"], "absolute floor"),
        ("beats_incumbent", detail["candidate_regime_accuracy"], detail["required"],
         gates["beats_incumbent"],
         f"live incumbent {detail['incumbent_regime_accuracy']} x {detail['tolerance']}"),
        ("oos_uplift", cand["oos_uplift"], thr["MIN_UPLIFT"],
         gates["oos_uplift_ok"],
         f"significant={cand['oos_uplift_significant']}"),
        ("map coverage", cand["n_qualified_strategies"], 1,
         gates["non_empty_map"], "qualified cells, min 1"),
    ]

    fig, axes = plt.subplots(1, 4, figsize=(13.5, 4.6))
    for ax, (label, measured, threshold, passed, note) in zip(axes, rows):
        colour = GREEN if passed else RED
        # Scale each panel to its own units — these gates are not comparable.
        top = max(measured, threshold) * 1.45 or 1.0
        ax.bar([0], [measured], width=0.5, color=colour, alpha=0.85, zorder=2)
        ax.axhline(threshold, color=RED, lw=1.6, ls="--", zorder=3)
        ax.text(0, measured + top * 0.045, f"{measured:g}", ha="center",
                fontsize=11, color=colour, fontweight="bold")
        ax.text(0.42, threshold + top * 0.015, f"threshold {threshold:g}",
                ha="right", fontsize=8, color=RED)
        ax.set_ylim(0, top)
        ax.set_xlim(-0.45, 0.45)
        ax.set_xticks([])
        ax.set_title(f"{label}\n{'PASS' if passed else 'FAIL'}",
                     fontsize=11, color=colour, pad=8)
        ax.set_xlabel(note, fontsize=8, color=MUTED)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)

    verdict = "all four gates PASS" if ev["would_promote"] else "promotion BLOCKED"
    fig.suptitle(
        f"Deployment gates — candidate on post-T1 data, {ev['evaluated_at_utc'][:16]}Z\n"
        f"{verdict}  ·  incumbent {ev['incumbent']['bundle_version']} "
        f"(resolved: {ev['incumbent']['resolution']})  ·  "
        + (f"PROMOTED -> {ev['promoted_bundle']}" if ev.get("promoted_bundle")
           else "NOT promoted — awaiting sign-off"),
        fontsize=12, color=INK, x=0.01, ha="left", y=0.99)
    fig.tight_layout(rect=(0, 0.02, 1, 0.86))
    fig.savefig(OUT / "gates_dashboard.png", dpi=160)
    plt.close(fig)
    print("wrote gates_dashboard.png")


def _load_map(ref: str | None):
    if ref is None:
        data = json.loads((REPO / "results/state/regime_strategy_map.json").read_text())
    else:
        raw = subprocess.run(
            ["git", "show", f"{ref}:results/state/regime_strategy_map.json"],
            capture_output=True, text=True, cwd=REPO,
        ).stdout
        data = json.loads(raw)
    out = {}
    for regime, entries in data["regimes"].items():
        for e in entries:
            strat, _, gran = e["variant"].partition("@")
            out.setdefault((strat, regime), []).append(gran)
    return out


def chart_map_diff_heatmap():
    live = _load_map("HEAD")
    cand = _load_map(None)

    fig, ax = plt.subplots(figsize=(11.5, 6.8))

    # 0 never · 1 both · 2 newly qualified · 3 dropped
    for si, strat in enumerate(STRATEGIES):
        for ri, regime in enumerate(REGIMES):
            in_live = (strat, regime) in live
            in_cand = (strat, regime) in cand
            if in_live and in_cand:
                colour, label = GREEN, "+".join(sorted(cand[(strat, regime)]))
            elif in_cand:
                colour, label = BLUE, "+".join(sorted(cand[(strat, regime)]))
            elif in_live:
                colour, label = AMBER, "dropped"
            else:
                colour, label = PALE, ""
            ax.add_patch(plt.Rectangle((ri, si), 1, 1, facecolor=colour,
                                       edgecolor="white", lw=2,
                                       alpha=0.85 if label else 1.0))
            if label:
                ax.text(ri + 0.5, si + 0.5, label, ha="center", va="center",
                        fontsize=9, color="white", fontweight="bold")

    ax.set_xlim(0, len(REGIMES))
    ax.set_ylim(0, len(STRATEGIES))
    ax.set_xticks([i + 0.5 for i in range(len(REGIMES))])
    ax.set_xticklabels(REGIMES, fontsize=10, color=INK)
    ax.set_yticks([i + 0.5 for i in range(len(STRATEGIES))])
    ax.set_yticklabels(STRATEGIES, fontsize=9, color=INK)
    ax.invert_yaxis()
    ax.tick_params(length=0, colors=MUTED)
    for s in ax.spines.values():
        s.set_visible(False)

    n_cand, n_live = len(cand), len(live)
    e_cand = sum(len(v) for v in cand.values())
    e_live = sum(len(v) for v in live.values())
    ax.set_title(
        f"Strategy x regime qualification — candidate vs live\n"
        f"{e_cand} qualified entries across {n_cand} of 40 strategy x regime cells "
        f"(live: {e_live} across {n_live}) — Ranging holds both H1 and H4",
        fontsize=13, color=INK, loc="left", pad=14)

    ax.legend(handles=[
        mpatches.Patch(color=GREEN, label="qualified before and after"),
        mpatches.Patch(color=BLUE, label="newly qualified"),
        mpatches.Patch(color=AMBER, label="dropped"),
        mpatches.Patch(color=PALE, label="never qualified"),
    ], frameon=False, fontsize=9, ncol=4, loc="upper center",
        bbox_to_anchor=(0.5, -0.06))

    fig.text(0.012, 0.015,
             "High-Vol has no qualifying strategy in either map (starvation, finding A/C). "
             "All qualified cells are the same single strategy.",
             fontsize=8.5, color=MUTED, style="italic")

    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUT / "map_diff_heatmap.png", dpi=160)
    plt.close(fig)
    print("wrote map_diff_heatmap.png")


if __name__ == "__main__":
    chart_gates_dashboard()
    chart_map_diff_heatmap()
