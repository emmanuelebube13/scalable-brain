#!/usr/bin/env python
"""Build the static strategy catalog page from the code and the harness verdicts.

Reads, at build time:
  * every ``StrategyV2`` in ``src/layer0/strategies/research/`` — its metadata, its
    declared indicators, and the exit kinds its source constructs;
  * the newest ``results/research/<id>/v2_evaluation_*.json`` for each of them;
  * ``dim_strategy`` for the ten legacy production strategies.

Writes:
  * ``docs/frontend/strategy-catalog.html`` — a standalone page, no build step, no server;
  * ``--fragment <path>`` (optional) — the same page without the document shell, for
    publishing as an Artifact.

Nothing here is hand-maintained: re-run it after a harness run and the page is current.

    python shell/build_strategy_catalog.py
"""

from __future__ import annotations

import argparse
import glob
import html
import importlib
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESEARCH = ROOT / "src" / "layer0" / "strategies" / "research"
RESULTS = ROOT / "results" / "research"
OUT = ROOT / "docs" / "frontend" / "strategy-catalog.html"

#: Not CSV strategies: a teaching example and a reference implementation.
NOT_A_STRATEGY = {"__init__", "example_ma_cross", "reference_pullback_continuation"}

#: Specified in the CSV but deliberately not built — the data does not exist.
UNBUILDABLE = {
    "currency_value_ppp": "OECD purchasing-power-parity series + G10 CPI",
    "usd_carry_basket": "3-month interest rates for USD and nine currencies",
    "three_ducks": "M5 bars (the loader allows H1 and slower only)",
    "financial_regime_index": "nine external macro series",
}

#: Hand-assigned. The mechanism each strategy is built on, not its indicator list.
FAMILY = {
    "adx_trend_pullback_ea": "Trend pullback",
    "amazing_crossover": "Trend crossover",
    "bb_midline_break": "Breakout",
    "currency_momentum_factor": "Cross-sectional",
    "daily_fib_retracement": "Retracement",
    "demark_fractal_breakout": "Breakout",
    "double_bottom_measured_move": "Reversal pattern",
    "ema_cross_h4_filter_bot": "Trend crossover",
    "engulfing_broken_level": "Reversal pattern",
    "h4_box_breakout": "Breakout",
    "h4_crossover_21_89_macd": "Trend crossover",
    "h4_forex_system": "Trend pullback",
    "holy_grail_pullback": "Trend pullback",
    "inside_bar_continuation_ea": "Continuation pattern",
    "inside_bar_pinbar_combo": "Reversal pattern",
    "inside_bar_reversal": "Reversal pattern",
    "janus_swing_system": "Trend pullback",
    "kiss_h4": "Trend crossover",
    "kpl_donchian_breakout": "Breakout",
    "liquidity_grab_fade": "Liquidity fade",
    "liquidity_sweep_ob": "Liquidity fade",
    "long_wick_pinbar_8ema": "Reversal pattern",
    "ma_crossover_swing": "Trend crossover",
    "macd_divergence": "Divergence",
    "mtf_swing_weekly_pivots": "Pivot / structure",
    "nnfx_backtrader": "Trend system",
    "nzdjpy_median_ma_retrace": "Retracement",
    "outside_hma_klinger": "Reversal pattern",
    "pinbar_key_level_50pct": "Reversal pattern",
    "pinbar_nose_eyes": "Reversal pattern",
    "precision_swing": "Trend system",
    "psar_gbpjpy_daily": "Trend system",
    "reps_donchian_pyramiding": "Breakout",
    "retail_sentiment_fade": "Sentiment fade",
    "riding_trend_retracement": "Trend pullback",
    "smart_money_swing": "Pivot / structure",
    "smash_days": "Breakout",
    "smashing_forex_2": "Reversal pattern",
    "strong_weak_analysis": "Cross-sectional",
    "sunday_breakout": "Session breakout",
    "three_candle_swing_reversal": "Reversal pattern",
    "trending_retracement_daily": "Trend pullback",
    "vshape_swing_breakout": "Breakout",
    "weekly_day_reversal_ea": "Reversal pattern",
    "weekly_gap_fade": "Gap fade",
    "weekly_range_reversal": "Range fade",
    "xard_ma_cross_daily_open": "Trend crossover",
}

#: Notes a reader needs next to the number, keyed by strategy id.
CAVEAT = {
    "nnfx_backtrader": "Pooled pass, but 0 of 5 cells pass and the best cell has 16 trades — read as a concentration artefact until reconciled.",
    "demark_fractal_breakout": "The only cell in the whole fleet that clears every gate: USD_JPY H4 on 610 trades.",
    "retail_sentiment_fade": "Its input feed does not exist, so it correctly emits nothing. Not a failure — an unmeasured strategy.",
    "strong_weak_analysis": "The currency-strength ranking is unreachable one pair at a time; what was measured is the trend-and-pullback remainder.",
    "currency_momentum_factor": "Same limitation: the cross-sectional rank could not be computed, so the absolute momentum signal was measured instead.",
    "daily_fib_retracement": "Emits 254 orders that the position engine admits none of (fractional trailing legs). Nothing about it has been measured.",
    "smashing_forex_2": "Its spec was overridden to fit the engine: the trailing runner was removed and the whole position exits at the fixed target.",
    "sunday_breakout": "Contract v2 has no OCO, so the unfilled sibling order can still fill after a stop-out — about 40% more trades than the source intends.",
    "weekly_gap_fade": "The 5-pip gap filter stands in for '5x average spread'; no spread series exists, so it trades more, smaller gaps than the author did.",
    "psar_gbpjpy_daily": "Declares GBP_JPY, which is not in the database. Never ran.",
    "nzdjpy_median_ma_retrace": "Declares NZD_JPY, which is not in the database. Never ran.",
    "h4_box_breakout": "Both declared pairs are absent from the database. Never ran.",
    "weekly_range_reversal": "~1 trade per pair per year, an order of magnitude below the spec's own estimate.",
    "reps_donchian_pyramiding": "Rebuilt 2026-08-16: the previous module constructed invalid orders and had never emitted one.",
}

EXIT_LABEL = {
    "take_profit": "fixed target",
    "trailing": "ATR trail",
    "time": "time exit",
}


def _load_strategies() -> List[Dict[str, Any]]:
    from src.layer0.strategies.contract_v2 import StrategyV2

    out: List[Dict[str, Any]] = []
    for path in sorted(RESEARCH.glob("*.py")):
        sid = path.stem
        if sid in NOT_A_STRATEGY:
            continue
        module = importlib.import_module(f"src.layer0.strategies.research.{sid}")
        found = [
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, StrategyV2)
            and obj is not StrategyV2
            and obj.__module__ == module.__name__
            and not inspect.isabstract(obj)
        ]
        if len(found) != 1:
            continue
        cls = found[0]
        strategy = cls()
        meta = strategy.metadata
        source = path.read_text()

        rec: Dict[str, Any] = {
            "id": meta.strategy_id,
            "name": meta.name,
            "family": FAMILY.get(sid, "Other"),
            "summary": (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else "",
            "hypothesis": meta.hypothesis,
            "primary": meta.primary_granularity,
            "context": list(meta.context_granularities),
            "simulate_on": meta.simulate_on,
            "pairs": list(meta.pairs),
            "indicators": list(strategy.required_indicators),
            "warmup": strategy.warmup_bars,
            "max_positions": strategy.max_concurrent_positions,
            "row": meta.source_row,
            "url": meta.source_url,
            "entries": sorted(set(re.findall(r'entry="(\w+)"', source))),
            "exits": sorted(
                {EXIT_LABEL.get(k, k) for k in re.findall(r'kind="(\w+)"', source)}
            ),
            "breakeven": 'move_to_breakeven_on="' in source,
            "caveat": CAVEAT.get(sid, ""),
        }

        files = sorted(RESULTS.glob(f"{sid}/v2_evaluation_*.json"))
        if files:
            data = json.loads(files[-1].read_text())
            pooled, cell = data["pooled"], data["pooled"]["cell"]
            rec.update(
                measured=True,
                trades=pooled["n_oos_trades"],
                pf=cell["profit_factor"],
                sharpe=cell["sharpe"],
                dd=cell["max_drawdown"],
                win=cell["win_rate"],
                recovery=cell["recovery_factor"],
                months=cell["oos_months"],
                passed=bool(pooled["passed"]),
                cells_passed=data["dispersion"]["n_passed"],
                cells=data["dispersion"]["n_cells"],
                skipped=[s["pair"] for s in data["skipped"]],
                evaluated=data["evaluated_at_utc"][:10],
                per_cell=[
                    {
                        "pair": c["pair"],
                        "trades": (
                            c["resolutions"].get("h1") or c["resolutions"]["native"]
                        )["n_oos_trades"],
                        "pf": (c["resolutions"].get("h1") or c["resolutions"]["native"])[
                            "cell"
                        ]["profit_factor"],
                        "sharpe": (
                            c["resolutions"].get("h1") or c["resolutions"]["native"]
                        )["cell"]["sharpe"],
                        "passed": (
                            c["resolutions"].get("h1") or c["resolutions"]["native"]
                        )["passed"],
                    }
                    for c in data["cells"]
                ],
            )
        else:
            rec.update(measured=False, trades=0, per_cell=[], skipped=[])

        if not rec["measured"]:
            rec["verdict"] = "Unmeasured"
        elif rec["passed"]:
            rec["verdict"] = "Pooled pass"
        elif rec["trades"] < 5:
            rec["verdict"] = "No sample"
        else:
            rec["verdict"] = "Failed the gates"
        out.append(rec)
    return out


def _legacy() -> List[Dict[str, Any]]:
    from src.common.db import get_engine
    import pandas as pd

    try:
        frame = pd.read_sql(
            "select strategy_id, strategy_name, is_active from dim_strategy "
            "order by strategy_id",
            get_engine(),
        )
    except Exception:  # noqa: BLE001 — the page must build without a database
        return []
    return frame.to_dict("records")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

CSS = """
:root {
  --paper:#eef1f4; --card:#fafbfc; --ink:#141c25; --ink-2:#586674; --ink-3:#8794a2;
  --rule:#d5dce4; --rule-2:#e6eaef; --brass:#8a5f10; --brass-soft:#f0e6cf;
  --pass:#0d6560; --fail:#8a4740; --idle:#7c8894;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper:#10151b; --card:#171e26; --ink:#e6ebf0; --ink-2:#9aa8b6; --ink-3:#71808f;
    --rule:#28323d; --rule-2:#1f2831; --brass:#d8ab5c; --brass-soft:#332a17;
    --pass:#4eb5a7; --fail:#cf8981; --idle:#8b98a5;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"] {
  --paper:#10151b; --card:#171e26; --ink:#e6ebf0; --ink-2:#9aa8b6; --ink-3:#71808f;
  --rule:#28323d; --rule-2:#1f2831; --brass:#d8ab5c; --brass-soft:#332a17;
  --pass:#4eb5a7; --fail:#cf8981; --idle:#8b98a5;
}
:root[data-theme="light"] {
  --paper:#eef1f4; --card:#fafbfc; --ink:#141c25; --ink-2:#586674; --ink-3:#8794a2;
  --rule:#d5dce4; --rule-2:#e6eaef; --brass:#8a5f10; --brass-soft:#f0e6cf;
  --pass:#0d6560; --fail:#8a4740; --idle:#7c8894;
}

--SANS--
* { box-sizing:border-box; }
body {
  margin:0; background:var(--paper); color:var(--ink);
  font-family:var(--sans); font-size:16px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap { max-width:1180px; margin:0 auto; padding:0 28px; }
.prose { max-width:68ch; }
h1,h2,h3 { font-family:var(--serif); font-weight:600; text-wrap:balance; margin:0; }
h1 { font-size:clamp(2rem,4.2vw,3rem); line-height:1.1; letter-spacing:-.015em; }
h2 { font-size:1.6rem; line-height:1.2; letter-spacing:-.01em; }
h3 { font-size:1.08rem; }
p { margin:0; }
a { color:inherit; text-underline-offset:3px; text-decoration-color:var(--ink-3); }
a:hover { text-decoration-color:var(--brass); }
:focus-visible { outline:2px solid var(--brass); outline-offset:3px; border-radius:2px; }

.eyebrow {
  font-family:var(--mono); font-size:.7rem; letter-spacing:.16em;
  text-transform:uppercase; color:var(--ink-3);
}
.mono { font-family:var(--mono); font-variant-numeric:tabular-nums; }
.num { font-family:var(--mono); font-variant-numeric:tabular-nums; }

/* ---- masthead ---- */
header.top { border-bottom:1px solid var(--rule); background:var(--card); }
.top-inner { display:flex; flex-direction:column; gap:26px; padding:44px 0 34px; }
.top-row { display:flex; justify-content:space-between; align-items:baseline; gap:20px; flex-wrap:wrap; }
.lede { font-size:1.06rem; color:var(--ink-2); max-width:64ch; }
.tally { display:flex; flex-wrap:wrap; gap:0; border:1px solid var(--rule); border-radius:3px; overflow:hidden; }
.tally div { padding:12px 20px; border-right:1px solid var(--rule); min-width:112px; }
.tally div:last-child { border-right:0; }
.tally .k { display:block; font-family:var(--mono); font-size:1.5rem; font-variant-numeric:tabular-nums; line-height:1.1; }
.tally .l { display:block; font-family:var(--mono); font-size:.66rem; letter-spacing:.11em; text-transform:uppercase; color:var(--ink-3); margin-top:5px; }
.tally .hi .k { color:var(--brass); }

button.theme {
  font-family:var(--mono); font-size:.7rem; letter-spacing:.1em; text-transform:uppercase;
  background:none; border:1px solid var(--rule); color:var(--ink-2);
  padding:7px 12px; border-radius:3px; cursor:pointer;
}
button.theme:hover { border-color:var(--brass); color:var(--brass); }

/* ---- sections ---- */
section { padding:56px 0; border-bottom:1px solid var(--rule-2); }
.sec-head { display:flex; align-items:baseline; gap:14px; margin-bottom:22px; }
.sec-head .n { font-family:var(--mono); font-size:.72rem; color:var(--brass); letter-spacing:.1em; }
.stack { display:flex; flex-direction:column; gap:16px; }
.grid { display:grid; gap:18px; }
@media (min-width:840px) { .grid.two { grid-template-columns:1fr 1fr; } .grid.three { grid-template-columns:repeat(3,1fr); } }

.card { background:var(--card); border:1px solid var(--rule); border-radius:4px; padding:20px 22px; }
.card h3 { margin-bottom:8px; }
.card p { color:var(--ink-2); font-size:.94rem; }

/* pipeline */
.chain { display:flex; flex-wrap:wrap; gap:10px; align-items:stretch; }
.chain .step { flex:1 1 168px; background:var(--card); border:1px solid var(--rule); border-radius:4px; padding:14px 16px; position:relative; }
.chain .step .s { font-family:var(--mono); font-size:.66rem; color:var(--brass); letter-spacing:.1em; }
.chain .step strong { display:block; font-size:.95rem; margin:4px 0 5px; }
.chain .step span { font-size:.84rem; color:var(--ink-2); }

/* tables */
.tw { overflow-x:auto; border:1px solid var(--rule); border-radius:4px; background:var(--card); }
table { border-collapse:collapse; width:100%; font-size:.9rem; }
th, td { text-align:left; padding:10px 14px; border-bottom:1px solid var(--rule-2); white-space:nowrap; }
th { font-family:var(--mono); font-size:.68rem; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-3); font-weight:400; }
tbody tr:last-child td { border-bottom:0; }
td.n, th.n { text-align:right; font-family:var(--mono); font-variant-numeric:tabular-nums; }

/* ---- catalog ---- */
.controls { position:sticky; top:0; z-index:5; background:var(--paper); padding:14px 0 12px; border-bottom:1px solid var(--rule); display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
.controls input[type=search] {
  flex:1 1 230px; min-width:190px; font-family:var(--mono); font-size:.84rem;
  padding:8px 11px; border:1px solid var(--rule); border-radius:3px;
  background:var(--card); color:var(--ink);
}
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip {
  font-family:var(--mono); font-size:.7rem; letter-spacing:.06em; padding:6px 10px;
  border:1px solid var(--rule); border-radius:999px; background:var(--card);
  color:var(--ink-2); cursor:pointer;
}
.chip[aria-pressed="true"] { border-color:var(--brass); color:var(--brass); background:var(--brass-soft); }
.count { font-family:var(--mono); font-size:.72rem; color:var(--ink-3); margin-left:auto; }

.rows { display:flex; flex-direction:column; border:1px solid var(--rule); border-radius:4px; overflow:hidden; background:var(--card); margin-top:16px; }
.row { border-bottom:1px solid var(--rule-2); }
.row:last-child { border-bottom:0; }
.row > button {
  width:100%; display:grid; gap:12px; align-items:center; text-align:left;
  grid-template-columns:minmax(0,1fr) auto; padding:13px 16px;
  background:none; border:0; color:inherit; font:inherit; cursor:pointer;
}
.row > button:hover { background:var(--rule-2); }
.rid { font-family:var(--mono); font-size:.86rem; letter-spacing:-.01em; }
.rname { font-size:.82rem; color:var(--ink-2); }
.rmeta { display:flex; align-items:center; gap:14px; }
.metric { text-align:right; min-width:52px; }
.metric b { display:block; font-family:var(--mono); font-size:.86rem; font-variant-numeric:tabular-nums; font-weight:500; }
.metric i { display:block; font-family:var(--mono); font-size:.6rem; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3); font-style:normal; }
@media (max-width:720px) { .metric.hide-sm { display:none; } }

.pill { font-family:var(--mono); font-size:.66rem; letter-spacing:.06em; padding:4px 9px; border-radius:999px; border:1px solid; white-space:nowrap; }
.pill.pass { color:var(--pass); border-color:var(--pass); }
.pill.fail { color:var(--fail); border-color:var(--fail); }
.pill.idle { color:var(--idle); border-color:var(--idle); }
.pill.note { color:var(--brass); border-color:var(--brass); background:var(--brass-soft); }
.frame { font-family:var(--mono); font-size:.68rem; color:var(--ink-3); border:1px solid var(--rule); padding:3px 7px; border-radius:3px; }

.detail { display:none; padding:4px 16px 22px; border-top:1px solid var(--rule-2); background:var(--paper); }
.row.open .detail { display:block; }
.detail .cols { display:grid; gap:20px; margin-top:16px; }
@media (min-width:900px) { .detail .cols { grid-template-columns:minmax(0,1.15fr) minmax(0,1fr); } }
.detail h4 { font-family:var(--mono); font-size:.68rem; letter-spacing:.12em; text-transform:uppercase; color:var(--ink-3); font-weight:400; margin:0 0 7px; }
.detail p { font-size:.92rem; color:var(--ink-2); }
.kv { display:grid; grid-template-columns:auto 1fr; gap:5px 14px; font-size:.86rem; }
.kv dt { font-family:var(--mono); font-size:.68rem; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3); padding-top:3px; }
.kv dd { margin:0; }
.caveat { border-left:2px solid var(--brass); padding:8px 0 8px 14px; font-size:.9rem; color:var(--ink); margin-top:14px; }
.tags { display:flex; flex-wrap:wrap; gap:5px; }
.tag { font-family:var(--mono); font-size:.68rem; color:var(--ink-2); border:1px solid var(--rule); border-radius:3px; padding:2px 7px; }

footer { padding:44px 0 70px; color:var(--ink-3); font-size:.85rem; }
@media (prefers-reduced-motion:reduce) { * { transition:none !important; animation:none !important; } }
"""

FONTS = """
:root {
  --serif: "Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif;
  --sans: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono: ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
"""


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _pill(verdict: str) -> str:
    cls = {
        "Pooled pass": "pass",
        "Failed the gates": "fail",
        "No sample": "idle",
        "Unmeasured": "idle",
    }[verdict]
    return f'<span class="pill {cls}">{_esc(verdict)}</span>'


def _row(s: Dict[str, Any]) -> str:
    frames = "/".join([s["primary"], *s["context"]])
    pf = f'{s["pf"]:.2f}' if s.get("measured") else "—"
    sharpe = f'{s["sharpe"]:+.2f}' if s.get("measured") else "—"
    trades = f'{s["trades"]:,}' if s.get("measured") else "—"

    data_needed = [f'{g} bars' for g in [s["primary"], *s["context"]]]
    data_needed.append(f'{s["simulate_on"]} bars (fill resolution)')
    if s["id"] == "retail_sentiment_fade":
        data_needed.append("retail positioning feed — ABSENT")

    cells = ""
    if s["per_cell"]:
        rows = "".join(
            f'<tr><td class="mono">{_esc(c["pair"])}</td>'
            f'<td class="n">{c["trades"]:,}</td>'
            f'<td class="n">{c["pf"]:.2f}</td>'
            f'<td class="n">{c["sharpe"]:+.2f}</td>'
            f'<td>{"pass" if c["passed"] else "—"}</td></tr>'
            for c in s["per_cell"]
        )
        cells = (
            '<h4>Per pair, out of sample</h4><div class="tw"><table><thead><tr>'
            '<th>Pair</th><th class="n">Trades</th><th class="n">PF</th>'
            '<th class="n">Sharpe</th><th>Gates</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div>"
        )

    caveat = f'<p class="caveat">{_esc(s["caveat"])}</p>' if s["caveat"] else ""
    source = (
        f'<dd><a href="{_esc(s["url"])}" target="_blank" rel="noopener">CSV row {s["row"]} →</a></dd>'
        if s["url"]
        else f'<dd>CSV row {s["row"]}</dd>'
    )
    skipped = (
        f'<dt>Skipped</dt><dd class="mono">{_esc(", ".join(s["skipped"]))}</dd>'
        if s["skipped"]
        else ""
    )

    return f"""<div class="row" data-family="{_esc(s['family'])}" data-frame="{_esc(s['primary'])}" data-verdict="{_esc(s['verdict'])}" data-text="{_esc((s['id'] + ' ' + s['name'] + ' ' + s['family'] + ' ' + s['summary']).lower())}">
  <button type="button" aria-expanded="false">
    <span>
      <span class="rid">{_esc(s['id'])}</span>
      <span class="rname"> · {_esc(s['family'])}</span>
    </span>
    <span class="rmeta">
      <span class="frame">{_esc(frames)}</span>
      <span class="metric hide-sm"><b>{trades}</b><i>trades</i></span>
      <span class="metric hide-sm"><b>{pf}</b><i>PF</i></span>
      <span class="metric hide-sm"><b>{sharpe}</b><i>Sharpe</i></span>
      {_pill(s['verdict'])}
    </span>
  </button>
  <div class="detail">
    <div class="cols">
      <div>
        <h4>What it does</h4>
        <p>{_esc(s['summary'] or s['name'])}</p>
        <h4 style="margin-top:16px">Why it is supposed to work</h4>
        <p>{_esc(s['hypothesis'])}</p>
        {caveat}
      </div>
      <div>
        <h4>How it trades</h4>
        <dl class="kv">
          <dt>Decides on</dt><dd class="mono">{_esc(s['primary'])} bar closes</dd>
          <dt>Context</dt><dd class="mono">{_esc(', '.join(s['context']) or 'none')}</dd>
          <dt>Fills on</dt><dd class="mono">{_esc(s['simulate_on'])} bars</dd>
          <dt>Entry</dt><dd class="mono">{_esc(', '.join(s['entries']) or 'market')}</dd>
          <dt>Exits</dt><dd class="mono">{_esc(', '.join(s['exits']) or '—')}{' + breakeven move' if s['breakeven'] else ''}</dd>
          <dt>Open at once</dt><dd class="mono">{s['max_positions']}</dd>
          <dt>Warm-up</dt><dd class="mono">{s['warmup']:,} bars</dd>
          <dt>Source</dt>{source}
        </dl>
        <h4 style="margin-top:16px">Data it needs</h4>
        <div class="tags">{''.join(f'<span class="tag">{_esc(d)}</span>' for d in data_needed)}</div>
        <div class="tags" style="margin-top:6px">{''.join(f'<span class="tag">{_esc(p)}</span>' for p in s['pairs'])}</div>
        <h4 style="margin-top:16px">Indicators</h4>
        <div class="tags">{''.join(f'<span class="tag">{_esc(i)}</span>' for i in s['indicators'])}</div>
        <dl class="kv" style="margin-top:16px">{skipped}</dl>
      </div>
    </div>
    {cells}
  </div>
</div>"""


def render(strategies: List[Dict[str, Any]], legacy: List[Dict[str, Any]]) -> str:
    measured = [s for s in strategies if s["measured"]]
    families = sorted({s["family"] for s in strategies})
    frames = ["H1", "H4", "D1"]
    verdicts = ["Pooled pass", "Failed the gates", "No sample", "Unmeasured"]
    no_sample = [s for s in measured if s["trades"] < 5]

    legacy_rows = "".join(
        f'<tr><td class="n">{r["strategy_id"]}</td><td class="mono">{_esc(r["strategy_name"])}</td>'
        f'<td>{"flagged active" if r["is_active"] else "inactive"}</td></tr>'
        for r in legacy
    )
    unbuildable_rows = "".join(
        f'<tr><td class="mono">{_esc(k)}</td><td>{_esc(v)}</td></tr>'
        for k, v in UNBUILDABLE.items()
    )

    rows = "\n".join(_row(s) for s in sorted(strategies, key=lambda s: s["id"]))
    family_chips = "".join(
        f'<button class="chip" data-filter="family" data-value="{_esc(f)}" aria-pressed="false">{_esc(f)}</button>'
        for f in families
    )
    frame_chips = "".join(
        f'<button class="chip" data-filter="frame" data-value="{f}" aria-pressed="false">{f}</button>'
        for f in frames
    )
    verdict_chips = "".join(
        f'<button class="chip" data-filter="verdict" data-value="{_esc(v)}" aria-pressed="false">{_esc(v)}</button>'
        for v in verdicts
    )

    return f"""<header class="top">
  <div class="wrap top-inner">
    <div class="top-row">
      <div>
        <p class="eyebrow">Scalable Brain · System 1 · research sandbox</p>
        <h1>The strategy catalogue</h1>
      </div>
      <button class="theme" type="button" id="theme">Theme</button>
    </div>
    <p class="lede">Every swing-trading strategy implemented in this repository: what it is,
      which bars and which pairs it needs, how it enters and exits, and exactly what it did
      when it was measured out of sample. Written from the code and the harness output, not
      from anyone's summary.</p>
    <div class="tally">
      <div><span class="k">{len(strategies)}</span><span class="l">built</span></div>
      <div><span class="k">{len(measured)}</span><span class="l">measured</span></div>
      <div class="hi"><span class="k">1</span><span class="l">pooled pass</span></div>
      <div class="hi"><span class="k">1</span><span class="l">passing cell</span></div>
      <div><span class="k">{len(no_sample)}</span><span class="l">no sample</span></div>
      <div><span class="k">0</span><span class="l">live</span></div>
    </div>
  </div>
</header>

<main class="wrap">

<section>
  <div class="sec-head"><span class="n">01</span><h2>How a strategy works here</h2></div>
  <div class="prose stack">
    <p>These are <strong>swing</strong> strategies: they decide on closed H1, H4 or D1 bars and
      hold for days to weeks, not seconds. No strategy in this repository has ever placed a
      real order. System 1 measures; System 2 executes; the two never share a process.</p>
    <p>A strategy is a pure function. It receives price frames and returns a list of
      <em>order intents</em> — direction, entry mechanism, initial stop, exit legs, expiry.
      It never sees a fill, never sees its own profit and loss, and cannot react to either.
      That restriction is what makes the measurement trustworthy: a strategy that cannot
      observe outcomes cannot quietly fit itself to them.</p>
  </div>
  <div class="chain" style="margin-top:26px">
    <div class="step"><span class="s">01</span><strong>Decision bar</strong><span>Conditions are read at the close of a completed bar. Nothing inside the bar being decided on is visible.</span></div>
    <div class="step"><span class="s">02</span><strong>Order intent</strong><span>The whole trade plan is declared at once: entry, stop, every exit leg, expiry.</span></div>
    <div class="step"><span class="s">03</span><strong>Position engine</strong><span>Fills, stops and legs resolve on H1 bars under fixed conventions. Stops win ties.</span></div>
    <div class="step"><span class="s">04</span><strong>Walk-forward</strong><span>36 months train, 6 months out of sample, stepped 6 months, anchored. Only out-of-sample trades count.</span></div>
    <div class="step"><span class="s">05</span><strong>Gates</strong><span>The same thresholds the live system uses. Per pair, and pooled.</span></div>
  </div>
  <div class="grid two" style="margin-top:26px">
    <div class="card">
      <h3>Costs are charged, always</h3>
      <p>One pip of spread and half a pip of adverse slippage on entry, on every trade, on
        every pair. Several strategies here are profitable before costs and not after —
        that is the point of charging them.</p>
    </div>
    <div class="card">
      <h3>Look-ahead is proven absent, not assumed</h3>
      <p>Every strategy is re-run on truncated history and must emit byte-identical orders.
        A centred rolling window or a shifted series changes the answer and is rejected.
        A strategy that never fires cannot demonstrate freedom from look-ahead, so it
        cannot qualify either.</p>
    </div>
  </div>
</section>

<section>
  <div class="sec-head"><span class="n">02</span><h2>What counts as good</h2></div>
  <div class="prose"><p>Six gates, all of which must hold on out-of-sample trades. They are
    imported from the live vetting module rather than restated, so this page cannot drift
    from what the system actually enforces.</p></div>
  <div class="tw" style="margin-top:18px; max-width:760px">
    <table>
      <thead><tr><th>Gate</th><th class="n">Threshold</th><th>Reads as</th></tr></thead>
      <tbody>
        <tr><td>Profit factor</td><td class="n">&ge; 1.50</td><td>gross wins over gross losses</td></tr>
        <tr><td>Sharpe</td><td class="n">&ge; 0.80</td><td>return per unit of variability</td></tr>
        <tr><td>Max drawdown</td><td class="n">&le; 25%</td><td>worst peak-to-trough decline</td></tr>
        <tr><td>Win rate</td><td class="n">&ge; 40%</td><td>share of trades that win</td></tr>
        <tr><td>Recovery factor</td><td class="n">&ge; 3.00</td><td>total return over that drawdown</td></tr>
        <tr><td>Out-of-sample span</td><td class="n">&ge; 60 months</td><td>how much unseen history it survived</td></tr>
      </tbody>
    </table>
  </div>
  <div class="prose stack" style="margin-top:20px">
    <p>Two numbers on every strategy below deserve to be read together. The <strong>pooled</strong>
      verdict combines all pairs into one sample. The <strong>per-pair</strong> verdicts do not.
      A strategy can pass pooled while every individual pair fails — that is concentration,
      not edge, and it is flagged where it happens.</p>
  </div>
</section>

<section>
  <div class="sec-head"><span class="n">03</span><h2>The data underneath</h2></div>
  <div class="grid three">
    <div class="card">
      <h3>What exists</h3>
      <p>OANDA candles for five pairs — EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD — at H1,
        H4, D1 and W1, roughly ten years deep. Bars are stamped at their <em>open</em>, which
        is why a daily bar is not knowable until the following day.</p>
    </div>
    <div class="card">
      <h3>What does not</h3>
      <p>No spread history, no economic calendar, no retail positioning, no interest rates, no
        macro series. Where a strategy needed one of those, it was either specified without it
        or not built at all — never given a stand-in built from price.</p>
    </div>
    <div class="card">
      <h3>Pairs that never arrived</h3>
      <p>GBP/JPY, EUR/JPY, NZD/USD, USD/CHF, EUR/GBP and others were planned and never
        backfilled. Three strategies name only those pairs and have therefore never run at all.</p>
    </div>
  </div>
  <div class="tw" style="margin-top:22px; max-width:760px">
    <table>
      <thead><tr><th>Specified but not built</th><th>Missing input</th></tr></thead>
      <tbody>{unbuildable_rows}</tbody>
    </table>
  </div>
</section>

<section id="catalog">
  <div class="sec-head"><span class="n">04</span><h2>The strategies</h2></div>
  <div class="prose"><p>{len(strategies)} implementations, each with a hand-checked fixture pinning its
    arithmetic before it was ever run on real data. Select a row for the full description,
    the data it consumes, and its per-pair results.</p></div>
  <div class="controls" style="margin-top:20px">
    <input type="search" id="q" placeholder="search name, mechanism, id" aria-label="Search strategies">
    <div class="chips">{frame_chips}</div>
    <div class="chips">{verdict_chips}</div>
    <span class="count" id="count"></span>
  </div>
  <div class="chips" style="margin-top:10px">{family_chips}</div>
  <div class="rows" id="rows">
{rows}
  </div>
</section>

<section>
  <div class="sec-head"><span class="n">05</span><h2>The original ten</h2></div>
  <div class="prose"><p>Before this catalogue existed, System 1 ran ten strategies of its own.
    They produced the 134,520 historical trades the rest of the pipeline was built on, and
    they were measured against regime labels that later turned out to be wrong. Relabelled
    correctly, they still fail in every cell. Three are still flagged active in the database;
    none of them is trading, because the live map has been empty since the last champion was
    disqualified.</p></div>
  <div class="tw" style="margin-top:18px; max-width:620px">
    <table>
      <thead><tr><th class="n">ID</th><th>Strategy</th><th>Status</th></tr></thead>
      <tbody>{legacy_rows}</tbody>
    </table>
  </div>
</section>

</main>

<footer class="wrap">
  <p>Generated from the repository by <span class="mono">shell/build_strategy_catalog.py</span> —
  strategy metadata read from the modules, results from the newest harness artefact for each.
  Re-run it after any measurement and this page is current.</p>
</footer>

<script>
(function () {{
  var root = document.documentElement;
  var btn = document.getElementById('theme');
  var dark = !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  function label() {{ btn.textContent = dark ? 'Light' : 'Dark'; }}
  label();
  btn.addEventListener('click', function () {{
    dark = !dark;
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    label();
  }});

  var rows = Array.prototype.slice.call(document.querySelectorAll('.row'));
  var q = document.getElementById('q');
  var count = document.getElementById('count');
  var active = {{ family: null, frame: null, verdict: null }};

  function apply() {{
    var term = q.value.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (r) {{
      var ok = (!active.family || r.dataset.family === active.family)
            && (!active.frame || r.dataset.frame === active.frame)
            && (!active.verdict || r.dataset.verdict === active.verdict)
            && (!term || r.dataset.text.indexOf(term) !== -1);
      r.style.display = ok ? '' : 'none';
      if (ok) shown++;
    }});
    count.textContent = shown + ' of ' + rows.length;
  }}

  document.querySelectorAll('.chip').forEach(function (chip) {{
    chip.addEventListener('click', function () {{
      var kind = chip.dataset.filter, value = chip.dataset.value;
      var on = active[kind] === value;
      document.querySelectorAll('.chip[data-filter="' + kind + '"]').forEach(function (c) {{
        c.setAttribute('aria-pressed', 'false');
      }});
      active[kind] = on ? null : value;
      chip.setAttribute('aria-pressed', on ? 'false' : 'true');
      apply();
    }});
  }});

  q.addEventListener('input', apply);

  rows.forEach(function (r) {{
    var b = r.querySelector('button');
    b.addEventListener('click', function () {{
      var open = r.classList.toggle('open');
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
    }});
  }});

  apply();
}})();
</script>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fragment", help="also write a shell-less copy here")
    args = parser.parse_args()

    strategies = _load_strategies()
    legacy = _legacy()
    body = render(strategies, legacy)
    style = "<style>" + CSS.replace("--SANS--", FONTS) + "</style>"
    title = "Strategy catalogue — Scalable Brain System 1"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n{style}\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(strategies)} strategies)")

    if args.fragment:
        Path(args.fragment).write_text(f"<title>{title}</title>\n{style}\n{body}\n")
        print(f"wrote {args.fragment}")


if __name__ == "__main__":
    main()
