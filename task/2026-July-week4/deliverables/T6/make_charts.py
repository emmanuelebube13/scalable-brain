"""T6 deliverable charts.

`pipeline_diagram.png` renders the actual thresholds by importing them from the
live gates module — if the live bar moves, this picture moves with it.
`pilot_folds.png` plots the pilot's real per-fold OOS metrics from its report.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
sys.path.insert(0, str(REPO))

INK, MUTED = "#1f2933", "#7b8794"
RED, GREEN, AMBER, BLUE, PALE = "#c0392b", "#1e8449", "#b9770e", "#2471a3", "#eef1f4"


def chart_pipeline():
    from src.system1.vetting.gates import GATES  # live thresholds, not copied

    fig, ax = plt.subplots(figsize=(13.5, 7.2))
    ax.set_xlim(0, 10); ax.set_ylim(0, 6.6); ax.axis("off")

    def box(x, y, w, h, title, body, colour):
        ax.add_patch(mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06",
                                             fc=colour + "16", ec=colour, lw=2))
        ax.text(x + w/2, y + h - 0.32, title, ha="center", fontsize=11.5,
                color=colour, fontweight="bold")
        ax.text(x + w/2, y + h/2 - 0.28, body, ha="center", va="center",
                fontsize=8.5, color=INK, linespacing=1.5)

    box(0.3, 3.7, 2.5, 1.9, "research/",
        "implements the contract\nid unique · hypothesis stated\n\nINVISIBLE to live", BLUE)
    box(3.7, 3.7, 2.5, 1.9, "staged/",
        "no look-ahead (proven)\n≥1 OOS trade across folds\n\nINVISIBLE to live", AMBER)
    box(7.1, 3.7, 2.5, 1.9, "qualified/",
        "passed the LIVE gates\non OOS folds only\n\nthe ONLY thing vet.py sees", GREEN)

    for x0, x1 in ((2.85, 3.65), (6.25, 7.05)):
        ax.annotate("", xy=(x1, 4.65), xytext=(x0, 4.65),
                    arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=2.2))

    # The gate wall
    ax.add_patch(mpatches.FancyBboxPatch((6.35, 0.55), 3.1, 2.75,
                                         boxstyle="round,pad=0.06", fc=GREEN + "10",
                                         ec=GREEN, lw=2, linestyle="--"))
    ax.text(7.9, 3.06, "THE GATE WALL", ha="center", fontsize=10.5,
            color=GREEN, fontweight="bold")
    ax.text(7.9, 2.78, "vetting/gates.py — imported, never copied", ha="center",
            fontsize=7.8, color=MUTED, style="italic")
    lines = [f"profit_factor  ≥ {GATES['profit_factor']}",
             f"sharpe         ≥ {GATES['sharpe']}",
             f"max_drawdown   ≤ {GATES['max_drawdown']:.0%}",
             f"win_rate       ≥ {GATES['win_rate']:.0%}",
             f"recovery       ≥ {GATES['recovery_factor']}",
             f"oos_months     ≥ {GATES['oos_months']}"]
    for i, ln in enumerate(lines):
        ax.text(6.62, 2.42 - i * 0.30, ln, fontsize=9, color=INK, family="monospace")
    ax.annotate("", xy=(7.9, 3.62), xytext=(7.9, 3.35),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=2))
    ax.annotate("", xy=(6.4, 1.9), xytext=(6.1, 1.9),
                arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.6, ls=":"))

    # Walk-forward harness feeding both promotions
    ax.add_patch(mpatches.FancyBboxPatch((0.3, 1.35), 5.6, 1.15,
                                         boxstyle="round,pad=0.06", fc=BLUE + "10",
                                         ec=BLUE, lw=1.8))
    ax.text(3.1, 2.16, "walk-forward harness  ·  validation/walk_forward.py",
            ha="center", fontsize=10, color=BLUE, fontweight="bold")
    ax.text(3.1, 1.72, "min_train 36mo · step 6mo · OOS 6mo · anchored\n"
                       "cost model: spread 1.0 pip · slippage 0.5 pip · commission 0",
            ha="center", va="center", fontsize=8.3, color=INK, linespacing=1.5)
    for x in (1.55, 4.95):
        ax.annotate("", xy=(x, 3.62), xytext=(x, 2.56),
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1.6, ls=":"))

    # Blocked bypass paths
    blocked = [
        (1.55, 5.95, 7.85, "research → qualified (skips gates)"),
        (5.0, 0.95, 8.9, "self-declared stage in metadata"),
    ]
    ax.annotate("", xy=(7.0, 5.95), xytext=(2.1, 5.95),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.8, ls="--",
                                connectionstyle="arc3,rad=-0.25"))
    ax.text(4.55, 6.42, "skip the gates", ha="center", fontsize=9, color=RED)
    ax.text(4.55, 6.03, "✗", ha="center", fontsize=20, color=RED, fontweight="bold")

    for i, (label, y) in enumerate([("duplicate strategy_id", 1.02),
                                    ("look-ahead (shift(-1))", 0.66),
                                    ("research writes to fact_*", 0.30)]):
        ax.text(0.45, y, "✗", fontsize=15, color=RED, fontweight="bold")
        ax.text(0.85, y + 0.05, f"BLOCKED: {label}", fontsize=9, color=RED, va="center")

    ax.set_title("How a new strategy idea reaches live\n"
                 "every bypass path the adversarial review tried is blocked by code, not convention",
                 fontsize=13.5, color=INK, loc="left", pad=16)
    fig.tight_layout()
    fig.savefig(OUT / "pipeline_diagram.png", dpi=160); plt.close(fig)
    print("wrote pipeline_diagram.png")


def chart_pilot_folds():
    import glob
    qual = sorted(glob.glob(str(REPO / "results/research/rsi_mean_reversion/qualification_*.json")))
    reports = qual or sorted(glob.glob(str(REPO / "results/research/rsi_mean_reversion/*.json")))
    if not reports:
        print("no pilot report yet"); return
    data = json.load(open(reports[-1]))
    ev, cell = data["evidence"], data["evidence"]["cell"]
    folds = ev["per_fold"]
    from src.system1.vetting.gates import GATES

    # Aggregate per fold index across pair/granularity for readability.
    by_fold = {}
    for f in folds:
        by_fold.setdefault(f["fold"], []).append(f)
    idx = sorted(by_fold)
    mean_r = [sum(x["mean_r"] for x in by_fold[i]) / len(by_fold[i]) for i in idx]
    win = [sum(x["win_rate"] for x in by_fold[i]) / len(by_fold[i]) for i in idx]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 7.6), sharex=True)
    ax1.bar(idx, mean_r, color=[GREEN if v > 0 else RED for v in mean_r])
    ax1.axhline(0, color=INK, lw=1)
    ax1.set_ylabel("mean R per OOS trade", color=MUTED, fontsize=10)
    ax1.set_title("Pilot: rsi_mean_reversion — per-fold out-of-sample results",
                  fontsize=13, color=INK, loc="left", pad=10)

    ax2.bar(idx, win, color=[GREEN if v >= GATES["win_rate"] else RED for v in win])
    ax2.axhline(GATES["win_rate"], color=RED, lw=1.6, ls="--")
    ax2.text(idx[-1], GATES["win_rate"] + 0.012, f"win-rate gate {GATES['win_rate']:.0%}",
             ha="right", fontsize=9, color=RED)
    ax2.set_ylabel("win rate", color=MUTED, fontsize=10)
    ax2.set_xlabel("walk-forward fold", color=MUTED, fontsize=10)

    for ax in (ax1, ax2):
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        for s in ("left", "bottom"): ax.spines[s].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.grid(axis="y", color=MUTED, alpha=0.18, lw=0.7, zorder=0)

    verdict = (f"AGGREGATE  PF {cell['profit_factor']}  ·  Sharpe {cell['sharpe']}  ·  "
               f"MaxDD {cell['max_drawdown']:.1%}  ·  WinRate {cell['win_rate']:.1%}  ·  "
               f"Recovery {cell['recovery_factor']}  ·  OOS {cell['oos_months']}mo  "
               f"·  {cell['trade_count']:,} trades")
    fig.text(0.012, 0.022, verdict, fontsize=9, color=INK, family="monospace")
    failures = data.get("failures") or []
    outcome = data.get("outcome", "")
    tail = ("VERDICT " + outcome + " — " + " · ".join(failures)) if failures else ""
    fig.text(0.012, 0.001, tail + "  (a clean rejection with per-gate reasons is the pipeline working)",
             fontsize=8.5, color=RED if failures else GREEN, style="italic")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "pilot_folds.png", dpi=160); plt.close(fig)
    print("wrote pilot_folds.png")


if __name__ == "__main__":
    chart_pipeline(); chart_pilot_folds()
