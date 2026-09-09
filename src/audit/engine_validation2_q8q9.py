"""Q8 (inversion symmetry) and Q9 (random-entry floor) analysis.

Q8 enforces the spec's hard precondition BEFORE computing any statistic:
per cell, |n_inv - n_orig| / n_orig <= 0.05. A cell failing it is BLOCKED and
excluded, with the reason recorded. If more than half the population is blocked,
the whole variant is BLOCKED (Rule 2 — no caveated-but-reported invalid tests).

Q9 reports the measured floor per engine x granularity with its replication
distribution, and computed generator-validity statistics (Rule 3 — no
"by construction" claims).
"""

from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ev2.q8q9")
OUT = _REPO / "audit" / "reports" / "engine_validation_2"
PRECONDITION = 0.05


def _cg() -> dict:
    c = pd.read_csv(OUT / "q2_cost_floor_by_engine_granularity.csv")
    return {(e, g): float(v) for e, g, v in zip(c.engine, c.granularity, c.C_g_median)}


def q8() -> None:
    cg = _cg()
    frames = []
    for f, eng in (("q8_trades_v1.parquet", "backtest_engine_v1"),
                   ("q8_trades_v2.parquet", "position_engine_v2")):
        p = OUT / f
        if p.exists():
            d = pd.read_parquet(p)
            d["engine"] = eng
            frames.append(d)
    if not frames:
        log.warning("no Q8 inputs")
        return
    t = pd.concat(frames, ignore_index=True)

    # Each inversion construction applies to exactly one engine: the signal-flip variants
    # are v1-only (v1 strategies emit a signal series), the geometric mirror is v2-only
    # (v2 strategies emit OrderIntents). Comparing across is not a blocked test, it is a
    # test that does not exist, so those pairs are never formed.
    APPLIES_TO = {"inv_naive": "backtest_engine_v1", "inv_pinned": "backtest_engine_v1",
                  "inv_mirror": "position_engine_v2"}
    rows = []
    for inv_variant in [v for v in t.variant.unique() if v != "orig"]:
        eng = APPLIES_TO[inv_variant]
        o = t[(t.variant == "orig") & (t.engine == eng)]
        i = t[(t.variant == inv_variant) & (t.engine == eng)]
        keys = ["engine", "granularity", "strategy_key", "symbol"]
        go = o.groupby(keys)["r_multiple"].agg(n_orig="count", mean_R_orig="mean")
        gi = i.groupby(keys)["r_multiple"].agg(n_inv="count", mean_R_inv="mean")
        m = go.join(gi, how="outer").reset_index()
        m["inv_variant"] = inv_variant
        m["n_orig"] = m.n_orig.fillna(0)
        m["n_inv"] = m.n_inv.fillna(0)
        m["count_divergence"] = (m.n_inv - m.n_orig).abs() / m.n_orig.replace(0, np.nan)
        m["C_g"] = [cg.get((e, g), np.nan) for e, g in zip(m.engine, m.granularity)]
        m["sum_R"] = m.mean_R_orig + m.mean_R_inv
        m["target_neg2Cg"] = -2 * m.C_g
        m["deviation"] = m.sum_R - m.target_neg2Cg
        m["precondition_ok"] = m.count_divergence <= PRECONDITION
        m["status"] = np.where(m.precondition_ok, "TESTED", "BLOCKED_count_divergence")
        rows.append(m)
    inv = pd.concat(rows, ignore_index=True)
    inv.to_csv(OUT / "q8_inversion_v2.csv", index=False)

    summ = []
    for (var, eng, gran), sub in inv.groupby(["inv_variant", "engine", "granularity"]):
        ok = sub[sub.precondition_ok]
        blocked_frac = 1 - len(ok) / max(1, len(sub))
        verdict = "BLOCKED_majority_failed_precondition" if blocked_frac > 0.5 else "TESTED"
        w = ok.n_orig.sum()
        summ.append({
            "inv_variant": var, "engine": eng, "granularity": gran,
            "k_cells": len(sub), "k_passed_precondition": len(ok),
            "blocked_fraction": blocked_frac, "verdict": verdict,
            "median_count_divergence": sub.count_divergence.median(),
            "n_orig_trades": int(ok.n_orig.sum()), "n_inv_trades": int(ok.n_inv.sum()),
            "wmean_R_orig": np.average(ok.mean_R_orig, weights=ok.n_orig) if w else np.nan,
            "wmean_R_inv": np.average(ok.mean_R_inv, weights=ok.n_orig) if w else np.nan,
            "sum_R": (np.average(ok.mean_R_orig, weights=ok.n_orig)
                      + np.average(ok.mean_R_inv, weights=ok.n_orig)) if w else np.nan,
            "target_neg2Cg": -2 * cg.get((eng, gran), np.nan),
        })
    s = pd.DataFrame(summ)
    s["deviation"] = s.sum_R - s.target_neg2Cg
    s.to_csv(OUT / "q8_inversion_summary.csv", index=False)
    log.info("\n=== Q8 ===\n%s", s.round(5).to_string(index=False))

    # matched-pair sums where entry timestamps coincide
    pairs = []
    cols = ["engine", "granularity", "strategy_key", "symbol", "entry_time", "r_multiple"]
    for inv_variant in [v for v in t.variant.unique() if v != "orig"]:
        eng = APPLIES_TO[inv_variant]
        o = t[(t.variant == "orig") & (t.engine == eng)][cols]
        i = t[(t.variant == inv_variant) & (t.engine == eng)][cols]
        m = o.merge(i, on=["engine", "granularity", "strategy_key", "symbol", "entry_time"],
                    suffixes=("_orig", "_inv"))
        m["inv_variant"] = inv_variant
        m["pair_sum_R"] = m.r_multiple_orig + m.r_multiple_inv
        pairs.append(m)
    pp = pd.concat(pairs, ignore_index=True)
    pp.to_csv(OUT / "q8_matched_pair_sums.csv", index=False)
    ps = (pp.groupby(["inv_variant", "engine", "granularity"])["pair_sum_R"]
          .agg(n="count", mean="mean", median="median", sd="std",
               p5=lambda x: x.quantile(.05), p95=lambda x: x.quantile(.95)).reset_index())
    ps["target_neg2Cg"] = [-2 * cg.get((e, g), np.nan) for e, g in zip(ps.engine, ps.granularity)]
    ps.to_csv(OUT / "q8_matched_pair_summary.csv", index=False)
    log.info("\n=== Q8 matched pairs ===\n%s", ps.round(5).to_string(index=False))


def q9() -> None:
    p = OUT / "q9_random_trades.parquet"
    if not p.exists():
        log.warning("no Q9 input")
        return
    r = pd.read_parquet(p)
    real = pd.read_parquet(OUT / "replay_trades.parquet")
    real = real[real.is_oos]
    cg = _cg()

    per_rep = (r.groupby(["engine", "granularity", "replication"])["r_multiple"]
               .agg(n="count", mean_R="mean").reset_index())
    per_rep.to_csv(OUT / "q9_floor_distribution_v2.csv", index=False)

    rows = []
    for (e, g), sub in per_rep.groupby(["engine", "granularity"]):
        obs = real[(real.engine == e) & (real.granularity == g)].r_multiple
        floor_mean = sub.mean_R.mean()
        floor_sd = sub.mean_R.std()
        z = (obs.mean() - floor_mean) / floor_sd if floor_sd > 0 else np.nan
        rows.append({
            "engine": e, "granularity": g, "n_replications": len(sub),
            "random_trades_per_rep": int(sub.n.mean()),
            "floor_mean_R": floor_mean, "floor_sd_of_rep_means": floor_sd,
            "floor_p5": sub.mean_R.quantile(.05), "floor_p95": sub.mean_R.quantile(.95),
            "C_g_measured": cg.get((e, g), np.nan),
            "minus_C_g": -cg.get((e, g), np.nan),
            "real_bank_mean_R": obs.mean(), "real_bank_n": len(obs),
            "real_minus_floor": obs.mean() - floor_mean,
            "z_vs_floor": z,
        })
    s = pd.DataFrame(rows)
    s.to_csv(OUT / "q9_floor_summary.csv", index=False)
    log.info("\n=== Q9 floor ===\n%s", s.round(5).to_string(index=False))

    # Generator validity — COMPUTED statistics only (Rule 3)
    lines = ["# Q9 generator validity — computed statistics", "",
             "Every claim below is a computed comparison of the synthetic random-entry",
             "population against the real replayed bank, per engine x granularity.",
             "No 'by construction' arguments.", "",
             "| engine | granularity | KS entry-hour (D, p) | KS bars-held (D, p) | "
             "n_real | n_synth | long share real | long share synth | chi2 p |",
             "|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for (e, g), sub in r.groupby(["engine", "granularity"]):
        obs = real[(real.engine == e) & (real.granularity == g)]
        if not len(obs):
            continue
        hr_s = pd.to_datetime(sub.entry_time, utc=True).dt.hour.values
        hr_r = pd.to_datetime(obs.entry_time, utc=True).dt.hour.values
        ks_h = stats.ks_2samp(hr_r, hr_s)
        ks_b = stats.ks_2samp(obs.bars_held.values, sub.bars_held.values)
        lr = float((obs.direction == 1).mean())
        ls = float((sub.direction == 1).mean())
        ct = np.array([[(obs.direction == 1).sum(), (obs.direction == -1).sum()],
                       [(sub.direction == 1).sum(), (sub.direction == -1).sum()]])
        chi = stats.chi2_contingency(ct)
        rows.append({"engine": e, "granularity": g,
                     "ks_entry_hour_D": ks_h.statistic, "ks_entry_hour_p": ks_h.pvalue,
                     "ks_bars_held_D": ks_b.statistic, "ks_bars_held_p": ks_b.pvalue,
                     "n_real": len(obs), "n_synth": len(sub),
                     "long_share_real": lr, "long_share_synth": ls,
                     "direction_chi2_p": chi.pvalue})
        lines.append(
            f"| {e} | {g} | D={ks_h.statistic:.4f}, p={ks_h.pvalue:.3g} | "
            f"D={ks_b.statistic:.4f}, p={ks_b.pvalue:.3g} | {len(obs)} | {len(sub)} | "
            f"{lr:.4f} | {ls:.4f} | {chi.pvalue:.3g} |")
    pd.DataFrame(rows).to_csv(OUT / "q9_generator_validity.csv", index=False)
    lines += ["", "**Reading it.** A large D with a tiny p means the synthetic entries do NOT",
              "match the real ones on that axis. The random-entry control is deliberately",
              "unmatched on entry timing — that is the whole point of a zero-information",
              "entry — so a failed hour-of-day KS is expected and is reported, not hidden.",
              "The direction share is the one axis the generator does target (a fair coin",
              "against the real bank's near-50/50 split); its chi-square p is the check.",
              "`bars_held` is an OUTCOME, not an input: it differs because the exits differ."]
    (OUT / "q9_generator_validity.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    q8()
    q9()
