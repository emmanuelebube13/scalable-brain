"""T5 deliverable charts. Every number is computed from the fix package's own
arithmetic (`fx_units.py`) — the same code the 23 tests pin — not illustrative.
"""
from __future__ import annotations
import sys
from decimal import Decimal
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[1] / "T5-fix-package"))
from fx_units import (Instrument, LEGACY_position_size_units,
                      position_size_units, realised_risk_account_ccy)

INK, MUTED = "#1f2933", "#7b8794"
RED, GREEN, AMBER, BLUE = "#c0392b", "#1e8449", "#b9770e", "#2471a3"

RISK = Decimal("200")
CASES = [
    ("EUR_USD\n(quote = account)", Instrument("EUR_USD", 4, Decimal("1.0")), Decimal("0.0050")),
    ("USD_JPY\n(quote JPY @150)", Instrument("USD_JPY", 2, Decimal(1)/Decimal(150)), Decimal("0.30")),
    ("USD_CAD\n(quote CAD @1.36)", Instrument("USD_CAD", 4, Decimal(1)/Decimal("1.36")), Decimal("0.0040")),
    ("EUR_GBP cross\n(quote GBP, GBPUSD 1.27)", Instrument("EUR_GBP", 4, Decimal("1.27")), Decimal("0.0040")),
]

def chart_sizing_error():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.6))
    labels = [c[0] for c in CASES]
    legacy_u, fixed_u, legacy_r = [], [], []
    for _, inst, sl in CASES:
        lu = LEGACY_position_size_units(risk_capital_account_ccy=RISK, sl_distance_quote_ccy=sl)
        fu = position_size_units(risk_capital_account_ccy=RISK, sl_distance_quote_ccy=sl, instrument=inst)
        legacy_u.append(lu); fixed_u.append(fu)
        legacy_r.append(float(realised_risk_account_ccy(units=lu, sl_distance_quote_ccy=sl, instrument=inst)))

    x = range(len(CASES)); w = 0.36
    ax1.bar([i - w/2 for i in x], legacy_u, w, color=RED, label="unpatched")
    ax1.bar([i + w/2 for i in x], fixed_u, w, color=GREEN, label="corrected")
    for i, (lu, fu) in enumerate(zip(legacy_u, fixed_u)):
        ax1.text(i - w/2, lu, f"{lu:,}", ha="center", va="bottom", fontsize=8, color=RED)
        ax1.text(i + w/2, fu, f"{fu:,}", ha="center", va="bottom", fontsize=8, color=GREEN)
    ax1.set_yscale("log"); ax1.set_ylabel("position size (units, log scale)", color=MUTED, fontsize=10)
    ax1.set_title("Position size the code computes", fontsize=12, color=INK, loc="left", pad=8)
    ax1.legend(frameon=False, fontsize=9)

    colours = [GREEN if abs(r - 200) <= 1 else (RED if r > 200 else AMBER) for r in legacy_r]
    ax2.bar(x, legacy_r, 0.55, color=colours)
    ax2.axhline(200, color=INK, lw=1.6, ls="--")
    ax2.text(len(CASES) - 0.4, 208, "intended cap: 200", ha="right", fontsize=9, color=INK)
    for i, r in enumerate(legacy_r):
        ax2.text(i, r + 6, f"{r:,.2f}", ha="center", va="bottom", fontsize=9, color=colours[i])
        if abs(r - 200) > 1:
            ax2.text(i, r + 26, f"{(r/200-1)*100:+.0f}%", ha="center", fontsize=9,
                     color=colours[i], fontweight="bold")
    ax2.set_ylabel("actual loss if the stop is hit (account ccy)", color=MUTED, fontsize=10)
    ax2.set_title("What the unpatched code ACTUALLY risks", fontsize=12, color=INK, loc="left", pad=8)
    ax2.set_ylim(0, 300)

    for ax in (ax1, ax2):
        ax.set_xticks(list(x)); ax.set_xticklabels(labels, fontsize=8.5, color=INK)
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        for s in ("left", "bottom"): ax.spines[s].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=8.5)
        ax.grid(axis="y", color=MUTED, alpha=0.18, lw=0.7, zorder=0)

    fig.suptitle("FIX-S3-004 — the risk cap is computed in the wrong currency\n"
                 "Account 10,000 @ 2% = 200 intended risk per trade",
                 fontsize=13.5, color=INK, x=0.01, ha="left", y=0.99)
    fig.text(0.012, 0.015,
             "Only the USD-quoted pair is coincidentally correct. USD_JPY under-risks by 99.3%; "
             "the cross pair BREACHES the hard cap by 27%.",
             fontsize=8.5, color=MUTED, style="italic")
    fig.tight_layout(rect=(0, 0.05, 1, 0.90))
    fig.savefig(OUT / "sizing_error_magnitude.png", dpi=160); plt.close(fig)
    print("wrote sizing_error_magnitude.png")

ITEMS = [
    ("S3-001\ngates blind",        3.0, 2.2, "blocks S3-002"),
    ("S3-002\nexposure = count",   3.4, 1.6, "packaged"),
    ("S3-003\nKelly inert",        2.6, 2.6, "next"),
    ("S3-004\nwrong currency",     3.8, 1.3, "packaged"),
    ("S3-005\nauditor leakage",    1.7, 1.5, "next"),
    ("S3-006\nsizing lockout",     3.6, 3.2, "decision"),
]
STATUS_COLOUR = {"packaged": GREEN, "blocks S3-002": AMBER, "next": BLUE, "decision": RED}

def chart_risk_matrix():
    fig, ax = plt.subplots(figsize=(10.5, 7.4))
    ax.axhspan(2, 4.3, 0, 0.5, color=AMBER, alpha=0.05)
    ax.axhspan(0, 2, 0.5, 1, color=GREEN, alpha=0.05)
    ax.axvline(2.5, color=MUTED, lw=1, ls=":"); ax.axhline(2.0, color=MUTED, lw=1, ls=":")
    for label, sev, eff, status in ITEMS:
        c = STATUS_COLOUR[status]
        ax.scatter([eff], [sev], s=1500, color=c, alpha=0.22, zorder=2)
        ax.scatter([eff], [sev], s=90, color=c, zorder=3)
        ax.annotate(label, (eff, sev), textcoords="offset points", xytext=(0, 24),
                    ha="center", fontsize=9, color=INK, linespacing=1.3)
    ax.set_xlim(0.6, 4.0); ax.set_ylim(1.2, 4.3)
    ax.set_xlabel("effort to fix  →", color=MUTED, fontsize=10)
    ax.set_ylabel("severity  →", color=MUTED, fontsize=10)
    ax.set_xticks([1, 2, 3, 4]); ax.set_xticklabels(["trivial", "small", "medium", "large"], fontsize=9)
    ax.set_yticks([2, 3, 4]); ax.set_yticklabels(["P2", "P1", "P0"], fontsize=9)
    ax.text(0.75, 4.15, "high severity, low effort — do first", fontsize=9, color=AMBER, style="italic")
    ax.set_title("System-3 money-layer risk landscape\nall six open items, 2026-07-29",
                 fontsize=13, color=INK, loc="left", pad=14)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.grid(color=MUTED, alpha=0.15, lw=0.7, zorder=0)
    ax.legend(handles=[mpatches.Patch(color=v, label=k) for k, v in STATUS_COLOUR.items()],
              frameon=False, fontsize=9, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.09))
    fig.text(0.012, 0.015,
             "S3-006 is plotted as a DECISION, not a fix: the locked gate is currently the only thing "
             "preventing further loss (profit factor 0.0 over 10 realised trades).",
             fontsize=8.5, color=MUTED, style="italic")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(OUT / "s3_risk_matrix.png", dpi=160); plt.close(fig)
    print("wrote s3_risk_matrix.png")

if __name__ == "__main__":
    chart_sizing_error(); chart_risk_matrix()
