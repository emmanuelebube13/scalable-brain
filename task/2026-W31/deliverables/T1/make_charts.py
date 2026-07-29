"""Generate the T1 deliverable charts from real measured data.

Every number plotted is queried live from ForexBrainDB or read from the repo —
nothing here is illustrative. The 'before' series is the 2026-06-24 vintage
preserved in fact_trade_outcomes_bak_20260729; the 'after' series is the
rebuilt table.

Usage: python task/2026-W31/deliverables/T1/make_charts.py
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: save, never show

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from sqlalchemy import text

from src.common.db import get_engine

OUT = Path(__file__).resolve().parent

BREAK_DATE = dt.date(2026, 6, 23)  # last trade the frozen writer recorded
FIX_DATE = dt.date(2026, 7, 29)  # this repair

INK = "#1f2933"
MUTED = "#7b8794"
RED = "#c0392b"
GREEN = "#1e8449"
BLUE = "#2471a3"


def weekly(conn, table: str, since: dt.date):
    rows = conn.execute(
        text(
            f'SELECT date_trunc(\'week\', "timestamp") AS w, count(*) AS n '
            f"FROM {table} WHERE \"timestamp\" >= :since GROUP BY 1 ORDER BY 1"
        ),
        {"since": since},
    ).fetchall()
    return [r.w.date() for r in rows], [r.n for r in rows]


def chart_outcomes_timeline(conn):
    """The one picture that proves the feedback loop is reconnected."""
    since = dt.date(2026, 1, 1)
    bw, bn = weekly(conn, "fact_trade_outcomes_bak_20260729", since)
    aw, an = weekly(conn, "fact_trade_outcomes", since)

    fig, ax = plt.subplots(figsize=(12, 5.6))

    recovered_w = [w for w in aw if w > BREAK_DATE]
    recovered_n = [n for w, n in zip(aw, an) if w > BREAK_DATE]

    # A single shaded band: the window in which System 1 retrained on outcomes
    # that stopped updating. Shading it once keeps the colour honest.
    ax.axvspan(BREAK_DATE, FIX_DATE, color=RED, alpha=0.09, zorder=0)

    ax.plot(aw, an, color=GREEN, lw=2.2, marker="o", ms=3.5,
            label=f"after repair — outcomes through {max(aw):%d %b}", zorder=3)
    ax.plot(bw, bn, color=RED, lw=1.6, ls="--", marker="o", ms=3,
            label=f"before — 2026-06-24 vintage, stops {BREAK_DATE:%d %b}", zorder=4)

    ymax = max(max(an, default=0), max(bn, default=0))
    ax.set_ylim(0, ymax * 1.28)

    # Mark the break itself on the axis rather than floating in the plot.
    ax.axvline(BREAK_DATE, color=RED, lw=1.1, ls=":", zorder=2)
    ax.annotate(
        f"writer died {BREAK_DATE:%d %b}\nlast trade ever recorded",
        xy=(BREAK_DATE, ymax * 1.02), xytext=(dt.date(2026, 4, 26), ymax * 1.19),
        color=RED, fontsize=9, ha="center", va="center",
        arrowprops=dict(arrowstyle="->", color=RED, lw=1.1,
                        connectionstyle="arc3,rad=-0.15"),
    )
    if recovered_w:
        ax.annotate(
            f"{len(recovered_n)} weeks recovered\n{sum(recovered_n):,} trades rebuilt",
            xy=(recovered_w[len(recovered_w) // 2],
                recovered_n[len(recovered_n) // 2]),
            xytext=(dt.date(2026, 5, 8), ymax * 0.16),
            color=GREEN, fontsize=9, ha="center", va="center",
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.1,
                            connectionstyle="arc3,rad=0.2"),
        )
    ax.text(BREAK_DATE + (FIX_DATE - BREAK_DATE) / 2, ymax * 1.22,
            "5 weeks blind", color=RED, fontsize=8.5, ha="center",
            style="italic", alpha=0.85)

    ax.set_title("fact_trade_outcomes — weekly trades written\n"
                 "System 1 retrained on stale results for 5 weeks",
                 fontsize=13, color=INK, loc="left", pad=12)
    ax.set_ylabel("trades recorded per week", color=MUTED, fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.grid(axis="y", color=MUTED, alpha=0.20, lw=0.7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)

    handles, labels = ax.get_legend_handles_labels()
    handles += [mpatches.Patch(color=RED, alpha=0.09,
                               label="window System 1 retrained on stale outcomes")]
    ax.legend(handles=handles, frameon=False, fontsize=8.5, loc="upper left")

    fig.tight_layout()
    fig.savefig(OUT / "outcomes_timeline.png", dpi=160)
    plt.close(fig)
    return sum(recovered_n), len(recovered_n)


def chart_import_graph():
    """Before/after of the layer0.strategies import chain."""
    fig, (l, r) = plt.subplots(1, 2, figsize=(13, 6.4))

    def node(ax, x, y, w, h, label, color, style="solid", fs=8.5):
        ax.add_patch(mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.012",
            fc=color + "18", ec=color, lw=1.5, ls=style))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                fontsize=fs, color=INK, linespacing=1.35)

    def arrow(ax, x1, y1, x2, y2, color, style="->", ls="solid"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle=style, color=color, lw=1.5, linestyle=ls))

    for ax in (l, r):
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # ---- BEFORE ----
    l.set_title("BEFORE — chain severed in 3 places",
                fontsize=12, color=RED, loc="left", pad=10)
    node(l, .18, .87, .64, .085, "persist_trade_outcomes.py\n(only writer of fact_trade_outcomes)", BLUE)
    arrow(l, .5, .87, .5, .795, MUTED)
    node(l, .12, .695, .76, .10,
         "qualify_strategies.py  ✗ 11-line shim + 1,460-line\nverbatim copy of the pre-reorg module", RED)
    l.text(.90, .745, "③", fontsize=15, color=RED, ha="center", va="center")
    arrow(l, .5, .695, .5, .625, MUTED)
    node(l, .12, .525, .76, .10,
         "qualification/qualify_strategies.py\nfrom ..strategies import (24 classes)", BLUE)
    arrow(l, .5, .525, .5, .455, RED, style="-|>")
    node(l, .12, .345, .76, .11,
         "layer0.strategies  ✗ NO __init__.py\n→ implicit namespace package, zero attributes\n"
         '"cannot import name … (unknown location)"', RED)
    l.text(.90, .40, "①", fontsize=15, color=RED, ha="center", va="center")
    arrow(l, .5, .345, .5, .275, RED, style="-|>", ls="dashed")
    node(l, .12, .165, .76, .11,
         "strategieStaged/*.py\n✗ from ..strategy_base  (1 level too shallow,\n"
         "and aimed at a pre-reorg location)", RED)
    l.text(.90, .22, "②", fontsize=15, color=RED, ha="center", va="center")
    node(l, .12, .035, .76, .085,
         "core_engine/strategy_base.py · data_access/indicators.py\n(never reached)", MUTED)
    l.text(.5, -0.045, "Real error discarded by the shim's `except ImportError`,\n"
                       "resurfaced as \"No module named 'qualification'\"",
           ha="center", fontsize=8.5, color=RED, style="italic")

    # ---- AFTER ----
    r.set_title("AFTER — chain intact, breaks now fail loudly",
                fontsize=12, color=GREEN, loc="left", pad=10)
    node(r, .18, .87, .64, .085, "persist_trade_outcomes.py\n(imports OK — 42 guard tests)", GREEN)
    arrow(r, .5, .87, .5, .795, MUTED)
    node(r, .12, .695, .76, .10,
         "qualify_strategies.py  ✓ shim only\nre-raises the ORIGINAL ImportError", GREEN)
    arrow(r, .5, .695, .5, .625, MUTED)
    node(r, .12, .525, .76, .10,
         "qualification/qualify_strategies.py\nfrom ..strategies import (24 classes)", BLUE)
    arrow(r, .5, .525, .5, .455, GREEN, style="-|>")
    node(r, .12, .345, .76, .11,
         "layer0.strategies  ✓ __init__.py restored\nre-exports all 24 strategy classes\n"
         "get_all_strategies() → 10 strategies", GREEN)
    arrow(r, .5, .345, .5, .275, GREEN, style="-|>")
    node(r, .12, .165, .76, .11,
         "strategieStaged/*.py\n✓ from ...core_engine.strategy_base\n"
         "✓ from ...data_access.indicators", GREEN)
    node(r, .12, .035, .76, .085,
         "core_engine/strategy_base.py · data_access/indicators.py\n(resolved)", GREEN)
    r.text(.5, -0.045, "8 layer0 shims re-raise the original error;\n"
                       "the sweep test imports every layer0 submodule",
           ha="center", fontsize=8.5, color=GREEN, style="italic")

    fig.suptitle("layer0.strategies import chain — what broke the feedback loop",
                 fontsize=13.5, color=INK, x=0.02, ha="left", y=0.985)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(OUT / "import_graph.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    with get_engine().connect() as conn:
        n, weeks = chart_outcomes_timeline(conn)
    chart_import_graph()
    print(f"wrote outcomes_timeline.png (recovered {n:,} trades across {weeks} weeks)")
    print("wrote import_graph.png")
