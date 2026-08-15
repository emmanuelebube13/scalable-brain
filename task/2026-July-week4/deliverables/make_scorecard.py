"""Week 2026-W31 scorecard — the five first-principles, scored from measured outcomes."""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
INK, MUTED = "#1f2933", "#7b8794"
RED, AMBER, GREEN = "#c0392b", "#b9770e", "#1e8449"

# (principle, score 0-1, status, evidence)
ITEMS = [
    ("Feedback loop live",
     1.0, "done",
     "outcomes current through 2026-07-24 (frozen 5 weeks); 42 guard tests"),
    ("Truth promoted",
     1.0, "done",
     "bundle 2026-07-29T11-46-42Z promoted — first ever with a REAL incumbent comparison"),
    ("Secrets rotated",
     0.85, "done",
     "password rotated + verified dead; 27 occurrences purged; history not rewritten (accepted)"),
    ("Failures loud",
     0.8, "partial",
     "8-check daily heartbeat live; but nothing notifies — the flag file is the whole channel"),
    ("Money layer unit-correct",
     0.35, "pending",
     "fixes packaged + tested, NOT applied; VM capture blocked; live edge is negative"),
]
COLOUR = {"done": GREEN, "partial": AMBER, "pending": RED}


def main():
    fig, ax = plt.subplots(figsize=(13, 6.6))
    y = list(range(len(ITEMS)))[::-1]

    for yi, (label, score, status, evidence) in zip(y, ITEMS):
        c = COLOUR[status]
        ax.barh(yi, 1.0, height=0.52, color=MUTED, alpha=0.12, zorder=1)
        ax.barh(yi, score, height=0.52, color=c, alpha=0.9, zorder=2)
        ax.text(0.012, yi + 0.30, label, fontsize=11.5, color=INK, fontweight="bold",
                va="bottom")
        ax.text(0.012, yi - 0.34, evidence, fontsize=8.5, color=MUTED, va="top")
        ax.text(min(score + 0.012, 0.99), yi, status.upper(), fontsize=9,
                color=c, va="center", fontweight="bold")

    ax.set_xlim(0, 1.02); ax.set_ylim(-0.75, len(ITEMS) - 0.15)
    ax.set_yticks([]); ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["0", "", "half", "", "done"], fontsize=9)
    ax.set_xlabel("progress this week", color=MUTED, fontsize=10)
    ax.set_title("Week 2026-W31 — the five first-principles\n"
                 "T1-T6 all complete; one item blocked on the user, one on a strategy decision",
                 fontsize=14, color=INK, loc="left", pad=16)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.grid(axis="x", color=MUTED, alpha=0.15, lw=0.7, zorder=0)
    ax.legend(handles=[mpatches.Patch(color=COLOUR[k], label=k) for k in COLOUR],
              frameon=False, fontsize=9, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.10))
    fig.text(0.012, 0.015,
             "The money layer scores lowest on purpose: the fixes are proven but unapplied, and the live "
             "account has taken 10 trades and lost all 10 — correctness is not the binding constraint there.",
             fontsize=8.5, color=MUTED, style="italic")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(OUT / "week_scorecard.png", dpi=160)
    print("wrote week_scorecard.png")


if __name__ == "__main__":
    main()
