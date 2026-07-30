"""T7 charts — all sizes measured from disk, before vs after the sweep."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
INK, MUTED = "#1f2933", "#7b8794"
RED, AMBER, GREEN, BLUE, PURPLE = "#c0392b", "#b9770e", "#1e8449", "#2471a3", "#7d3c98"


def _before():
    d = {}
    for line in (OUT / "before_sizes.txt").read_text().splitlines():
        sz, name = line.split("\t", 1)
        d[name] = sz
    return d


def _kb(s):
    u = s[-1]
    v = float(s[:-1]) if u in "KMG" else float(s)
    return v * {"K": 1, "M": 1024, "G": 1024 * 1024}.get(u, 1 / 1024)


def chart_before_after():
    before = _before()
    after = {}
    for line in subprocess.run("du -sh --exclude=.git * 2>/dev/null | sort -rh",
                               shell=True, cwd=REPO, capture_output=True, text=True).stdout.splitlines():
        sz, name = line.split("\t", 1)
        after[name] = sz

    names = [n for n in before if _kb(before[n]) >= 8]
    names = sorted(names, key=lambda n: -_kb(before[n]))[:16]

    fig, ax = plt.subplots(figsize=(12.5, 7.4))
    y = list(range(len(names)))[::-1]
    for yi, n in zip(y, names):
        b = _kb(before[n]); a = _kb(after.get(n, "0K"))
        gone = a == 0
        ax.barh(yi + 0.19, b, height=0.34, color=RED if gone else MUTED,
                alpha=0.85 if gone else 0.45, zorder=2)
        ax.barh(yi - 0.19, a, height=0.34, color=GREEN, alpha=0.85, zorder=2)
        label = "→ archived" if gone else (f"{after.get(n,'0')}" if a != b else "unchanged")
        ax.text(max(b, a) * 1.05 + 2, yi, label, va="center", fontsize=8,
                color=RED if gone else MUTED)

    ax.set_xscale("symlog", linthresh=8)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=9, color=INK)
    ax.set_xlabel("KB (symlog)", color=MUTED, fontsize=10)
    ax.set_title("Repo top level — before vs after the v1 sweep\n"
                 "227 files / 3.1 MB archived; the bulk (logs, archieved, backups) is protected data",
                 fontsize=13, color=INK, loc="left", pad=14)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED); ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.grid(axis="x", color=MUTED, alpha=0.15, lw=0.7, zorder=0)
    ax.legend(handles=[mpatches.Patch(color=MUTED, alpha=0.45, label="before"),
                       mpatches.Patch(color=GREEN, label="after"),
                       mpatches.Patch(color=RED, label="removed from the tree (archived)")],
              frameon=False, fontsize=9, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "repo_before_after.png", dpi=160); plt.close(fig)
    print("wrote repo_before_after.png")


def chart_classification():
    rows = json.loads((OUT / "manifest.json").read_text())
    groups = {}
    for r in rows:
        key = f"ARCHIVE · {r['era']}" if r["verdict"] == "ARCHIVE" else r["verdict"]
        g = groups.setdefault(key, {"files": 0, "kb": 0, "paths": 0})
        g["files"] += r["files"]; g["kb"] += r["kb"]; g["paths"] += 1

    order = ["ARCHIVE · v1-layer", "ARCHIVE · stray-root", "ARCHIVE · orphan", "UNCERTAIN", "KEEP"]
    order = [o for o in order if o in groups]
    colour = {"ARCHIVE · v1-layer": RED, "ARCHIVE · stray-root": AMBER,
              "ARCHIVE · orphan": PURPLE, "UNCERTAIN": BLUE, "KEEP": GREEN}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.6))
    for ax, key, title in ((ax1, "files", "files"), (ax2, "kb", "size (KB)")):
        vals = [groups[o][key] for o in order]
        ax.bar(range(len(order)), vals, color=[colour[o] for o in order], alpha=0.88)
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9.5,
                    color=colour[order[i]], fontweight="bold")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([o.replace("ARCHIVE · ", "") for o in order],
                           fontsize=9, color=INK, rotation=12)
        ax.set_title(title, fontsize=11, color=INK, loc="left", pad=8)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        for s in ("left", "bottom"): ax.spines[s].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.grid(axis="y", color=MUTED, alpha=0.15, lw=0.7, zorder=0)

    fig.suptitle("What kind of debt this was\n"
                 "classified by import closure + reference closure; recency advisory only",
                 fontsize=13, color=INK, x=0.012, ha="left", y=0.99)
    fig.text(0.012, 0.02,
             "UNCERTAIN items were NOT moved — they await the owner's call. "
             "KEEP rows are the ones worth stating explicitly (nlp, layer3_ml tombstone, sql, othersystemcommunication).",
             fontsize=8.5, color=MUTED, style="italic")
    fig.tight_layout(rect=(0, 0.06, 1, 0.90))
    fig.savefig(OUT / "classification_breakdown.png", dpi=160); plt.close(fig)
    print("wrote classification_breakdown.png")


if __name__ == "__main__":
    chart_before_after(); chart_classification()
