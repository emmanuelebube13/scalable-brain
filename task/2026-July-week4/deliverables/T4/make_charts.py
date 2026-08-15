"""T4 deliverable charts.

`freshness_dashboard.png` renders the live heartbeat snapshot
(`results/state/heartbeat_latest.json`) — it is a real run, not a mock-up, and
re-running this script after any heartbeat run redraws current truth.

`outage_history.png` plots the two known silent outages from measured evidence:
the price-ingest gap and the trade-outcomes freeze recovered during T1.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
SNAPSHOT = REPO / "results" / "state" / "heartbeat_latest.json"

INK = "#1f2933"
MUTED = "#7b8794"
RED = "#c0392b"
AMBER = "#b9770e"
GREEN = "#1e8449"
BLUE = "#2471a3"

STATUS_COLOUR = {"OK": GREEN, "WARN": AMBER, "CRITICAL": RED, "BLOCKED": MUTED}


def chart_freshness_dashboard():
    snap = json.loads(SNAPSHOT.read_text())
    checks = snap["checks"]

    # Plot age as a fraction of its own threshold so checks on wildly different
    # timescales (2h cron vs 336h retrain) share one axis honestly.
    rows = [(c["name"], c["status"], c["age_hours"], c["threshold_hours"],
             c["budget_used"], c["detail"]) for c in checks]

    fig, ax = plt.subplots(figsize=(12.5, 6.2))
    y = list(range(len(rows)))[::-1]

    for yi, (name, status, age, thr, ratio, _detail) in zip(y, rows):
        colour = STATUS_COLOUR[status]
        if ratio is None:
            # Pass/fail check (e.g. SHA256 integrity) — no continuous tolerance.
            ax.plot([0.012], [yi], marker="o", ms=8, color=colour, zorder=3)
            ax.text(0.035, yi, "pass/fail check — no time budget", va="center",
                    fontsize=8.5, color=colour, style="italic")
            continue
        ax.barh(yi, max(min(ratio, 1.6), 0.004), height=0.5, color=colour,
                alpha=0.85, zorder=2)
        # Deliberately no "Xh of Yh" here: for market-calendar checks the budget
        # is shortfall against the last close, not wall-clock age, and showing
        # both invites the reader to divide two unrelated numbers.
        label = f"{ratio*100:.0f}% of its {thr:g}h tolerance used"
        ax.text(max(min(ratio, 1.6), 0.004) + 0.025, yi, label, va="center",
                fontsize=8.5, color=colour)

    ax.axvline(1.0, color=RED, lw=1.4, ls="--", zorder=3)
    ax.text(1.01, len(rows) - 0.35, "stale threshold", color=RED, fontsize=9,
            rotation=90, va="top")

    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=9.5, color=INK)
    ax.set_xlabel("tolerance consumed — each check against its own budget (1.0 = stale)",
                  color=MUTED, fontsize=10)
    ax.set_xlim(0, 1.75)
    ts = dt.datetime.fromisoformat(snap["evaluated_at_utc"])
    ax.set_title(
        f"System-1 freshness heartbeat — live run {ts:%Y-%m-%d %H:%M}Z\n"
        f"overall: {snap['overall_status']} (exit {snap['exit_code']})",
        fontsize=13, color=INK, loc="left", pad=12)

    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="x", color=MUTED, alpha=0.18, lw=0.7, zorder=0)

    ax.legend(handles=[mpatches.Patch(color=STATUS_COLOUR[s], label=s)
                       for s in ("OK", "WARN", "CRITICAL", "BLOCKED")],
              frameon=False, fontsize=8.5, ncol=4,
              loc="upper center", bbox_to_anchor=(0.5, -0.12))

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(OUT / "freshness_dashboard.png", dpi=160)
    plt.close(fig)
    print("wrote freshness_dashboard.png")


def chart_outage_history():
    fig, ax = plt.subplots(figsize=(12.5, 4.8))

    start, end = dt.date(2026, 1, 1), dt.date(2026, 8, 5)
    today = dt.date(2026, 7, 29)

    outages = [
        ("OANDA price ingest dead", dt.date(2026, 7, 4), dt.date(2026, 7, 20), 1.0,
         "16 days · found by chance"),
        ("fact_trade_outcomes frozen", dt.date(2026, 6, 23), dt.date(2026, 7, 29), 0.0,
         "5 weeks · found by chance"),
    ]

    for label, s, e, yi, note in outages:
        ax.barh(yi, (e - s).days, left=s, height=0.36, color=RED, alpha=0.85, zorder=3)
        ax.text(s, yi + 0.27, label, fontsize=9.5, color=INK, va="bottom")
        ax.text(e + dt.timedelta(days=2), yi, note, fontsize=8.5,
                color=RED, va="center")

    # Heartbeat coverage from today onward.
    ax.axvspan(today, end, color=GREEN, alpha=0.10, zorder=0)
    ax.axvline(today, color=GREEN, lw=1.6, zorder=4)
    ax.text(today - dt.timedelta(days=2), 1.72,
            "heartbeat live — daily 06:00 UTC",
            fontsize=9.5, color=GREEN, va="top", ha="right")

    ax.annotate("detection time before: weeks", xy=(dt.date(2026, 4, 1), 0.5),
                fontsize=10, color=RED, ha="center", va="center")
    ax.annotate("after: ≤24h", xy=(dt.date(2026, 4, 1), 0.22),
                fontsize=10, color=GREEN, ha="center", va="center")

    ax.set_xlim(start, end)
    ax.set_ylim(-0.6, 1.9)
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.set_title("Silent failures in 2026 — and when they would now be caught",
                 fontsize=13, color=INK, loc="left", pad=12)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="x", color=MUTED, alpha=0.18, lw=0.7, zorder=0)

    fig.text(0.012, 0.02,
             "Both outages ran while the pipeline reported success. Neither was detected by a check — "
             "one was found during an audit, the other during this week's repair.",
             fontsize=8, color=MUTED, style="italic")

    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(OUT / "outage_history.png", dpi=160)
    plt.close(fig)
    print("wrote outage_history.png")


if __name__ == "__main__":
    chart_freshness_dashboard()
    chart_outage_history()
