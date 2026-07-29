"""T2 deliverable chart: credential exposure before vs after.

Counts come from the measured inventory taken during the task (fixed-string
`git grep -F` over HEAD and the working tree), not from estimates.
No password value — old or new — appears anywhere in this file or its output.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent

INK = "#1f2933"
MUTED = "#7b8794"
RED = "#c0392b"
GREEN = "#1e8449"
AMBER = "#b9770e"

# (location, occurrences, after-state)
#   "purged"  -> secret removed and credential dead
#   "dead"    -> value still present but no longer authenticates
#   "n/a"     -> nothing was there
ROWS = [
    ("configuration/postgresql_connection_details.txt\n(plaintext memo + DSN)", 2, "purged"),
    ("docs/postgresql/ setup guides (4 files)", 11, "purged"),
    ("docs/ roadmap + research notes (3 files)", 4, "purged"),
    ("FIX-XC-003 fix doc (the report itself)", 7, "purged"),
    ("MDs/ live-trading readiness review", 1, "purged"),
    ("src/sql/timescaledb/README.md", 2, "purged"),
    (".claude/settings.local.json\n(PGPASSWORD permission, untracked)", 1, "purged"),
    ("git history (8 commits)", 8, "dead"),
    ("System 2 / System 3 on other computers", 0, "n/a"),
]

AFTER_STYLE = {
    "purged": (GREEN, "purged from HEAD + credential rotated"),
    "dead": (AMBER, "still present, but the credential is dead"),
    "n/a": (MUTED, "not a consumer — confirmed with the owner"),
}


def main():
    fig, ax = plt.subplots(figsize=(12.5, 7.0))
    y = list(range(len(ROWS)))[::-1]

    for yi, (label, n, state) in zip(y, ROWS):
        colour, _ = AFTER_STYLE[state]
        # Bar length is the ACTUAL occurrence count in each state — an emptied
        # location must render as an empty bar, not a full one labelled "0".
        after_n = 0 if state in ("purged", "n/a") else n

        if n:
            ax.barh(yi + 0.19, n, height=0.34, color=RED, zorder=2)
            ax.text(n + 0.25, yi + 0.19, f"{n}", va="center",
                    fontsize=8.5, color=RED)
        if after_n:
            ax.barh(yi - 0.19, after_n, height=0.34, color=colour, zorder=2)
            ax.text(after_n + 0.25, yi - 0.19, f"{after_n}", va="center",
                    fontsize=8.5, color=colour)
        elif n:
            # Zero after: a tick at the origin so the row still reads as acted-on.
            ax.plot([0.06], [yi - 0.19], marker="o", ms=6, color=colour, zorder=3)
            ax.text(0.32, yi - 0.19, "0 — purged", va="center",
                    fontsize=8.5, color=colour)
        else:
            ax.text(0.06, yi, "no exposure", va="center", fontsize=8.5,
                    color=MUTED, style="italic")

    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in ROWS], fontsize=8.5, color=INK)
    ax.set_xlabel("occurrences of the live password", color=MUTED, fontsize=10)
    ax.set_xlim(0, 13.5)
    ax.set_title(
        "ForexBrainDB `sa` password — exposure before and after rotation\n"
        "27 occurrences across 11 tracked files, live in the repo since 2026-04-25",
        fontsize=13, color=INK, loc="left", pad=14)

    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="x", color=MUTED, alpha=0.18, lw=0.7, zorder=0)

    handles = [
        mpatches.Patch(color=RED, label="BEFORE — live secret exposed"),
        mpatches.Patch(color=GREEN, label="AFTER — purged from HEAD, credential rotated"),
        mpatches.Patch(color=AMBER, label="AFTER — value remains, but no longer authenticates"),
        mpatches.Patch(color=MUTED, alpha=0.4, label="not a consumer"),
    ]
    ax.set_ylim(-0.75, len(ROWS) - 0.25)
    ax.legend(handles=handles, frameon=False, fontsize=8.5, ncol=2,
              loc="upper center", bbox_to_anchor=(0.5, -0.13))

    fig.text(0.012, 0.012,
             "Old credential verified dead: FATAL: password authentication failed for user \"sa\".  "
             "History was NOT rewritten — that needs owner sign-off.",
             fontsize=8, color=MUTED, style="italic")

    fig.tight_layout(rect=(0, 0.10, 1, 1))
    fig.savefig(OUT / "exposure_before_after.png", dpi=160)
    plt.close(fig)
    print("wrote exposure_before_after.png")


if __name__ == "__main__":
    main()
