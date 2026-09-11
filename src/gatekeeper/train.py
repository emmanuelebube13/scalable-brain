"""MODEL-006 — train the regime-aware ML gatekeeper with OOS uplift gating.

Training set = backtested trades (fact_trade_outcomes) joined point-in-time to the CAUSAL
regime (fact_market_regime_v2.regime_causal / prob_causal_* — walk-forward filtered
forward-only labels, FIX-S1-005; the leaked reporting-only smoothed columns are never
consumed): features = [atr_value, adx_value, prob_causal_trending_up/down/ranging/high_vol]
+ causal regime / strategy_id / entry_signal_type (one-hot); label = is_winner.
Expanding-window walk-forward folds calibrate a regime-aware dynamic threshold and measure
OOS uplift (approved vs rejected r_multiple, bootstrap-significant).

Writes the champion contract. Use ``--dry-run`` to write a PROPOSED bundle
(models/proposed_champion_*) without overwriting the live champion (log-only; rule #1).

Usage: python -m src.gatekeeper.train --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text
from xgboost import XGBClassifier

from src.common.db import get_engine
from src.gatekeeper import thresholds as TH
from src.gatekeeper.promote import atomic_promote

logger = logging.getLogger("system1.gatekeeper")

from src.regime.structural import LABELLER_VERSION

REGIME_MODEL_VERSION = LABELLER_VERSION
# 2.0.0 — trade geometry in, `strategy_id` and the `trending_strength` duplicate out.
#
# A MAJOR bump: a model fit on 1.0.0 cannot be scored against this basis or vice versa, so
# a consumer comparing the two is comparing different things. What protects the LIVE
# champion (fit on 1.0.0) is `Scorer`, which reads `preprocessor.feature_names_in_` off
# the pickled artifact in the bundle — not this constant and not the manifest. It asks the
# shipped preprocessor what it needs, so it keeps asking for the 1.0.0 columns.
#
# That is also the constraint on `_derive_features`: it is shared by training and serving
# on purpose, so it must keep PRODUCING every column any live bundle asks for, even ones
# no longer trained on. See the back-compat note there.
#
# NOT YET SCOREABLE LIVE. A 2.0.0 champion needs `atr_sl_multiplier`,
# `atr_tp_multiplier` and `entry_signal_type` at inference. The live signal already
# carries everything they are derived from (`proposed_entry`, `proposed_sl`,
# `proposed_tp`, `atr`, `direction` — they are in every ledger row), but nothing maps them
# across yet, and doing so changes the live emit path. Promoting a 2.0.0 bundle before
# that lands would refuse every signal with MISSING_FEATURE. This change set is dry-run
# only and promotes nothing, so the gap is a prerequisite for promotion, not a live defect.
FEATURE_SET_VERSION = "2.0.0"
# FIX-S1-005: the gatekeeper trains on the CAUSAL regime label/probs (walk-forward,
# filtered forward-only) — never the reporting-only smoothed columns, which leak the
# future into a past bar and contaminate the OOS uplift proof.
NUMERIC = [
    "atr_value",
    "adx_value",
    # TRADE GEOMETRY — the transferable payoff features (2026-09-11).
    #
    # Market state alone does not say much about whether a trade wins: WO-04B removed
    # `strategy_id` and found no significant uplift at H4 (p=0.44) or D1 (p=1.00). But
    # market state was never the whole premise — HOW FAR THE STOP IS and HOW FAR THE
    # TARGET IS say a great deal, and unlike strategy identity they mean the same thing
    # across strategies, pairs and price levels. A 1.5xATR stop against a 3xATR target is
    # the same bet whoever places it; `strategy_id` one-hot is the opposite of that, which
    # is why it absorbed 96.78% of gain importance and generalised to nothing.
    #
    # These two columns existed from the day `fact_trade_outcomes` was created and were
    # NULL in all 93,738 rows — both writers passed a literal None. `src/outcomes/geometry.py`
    # fills them now. Until it did, this feature set had nothing transferable in it to use.
    "atr_sl_multiplier",
    "atr_tp_multiplier",
]
# The subset of NUMERIC a row must have to be usable at all. `atr_tp_multiplier` is
# absent from it on purpose — see the dropna in `build_frame`.
NUMERIC_REQUIRED = ["atr_value", "adx_value", "atr_sl_multiplier"]
# `strategy_id` REMOVED 2026-09-11 (WO-04B verdict, and FIX-S1-012's whole point).
#
# It is not a market-state feature and never generalised: one-hot strategy identity let
# the model reproduce MODEL-005's selection instead of gating it, scored a near-constant
# per strategy, and drove `check_cell_degeneracy` to 100% — the guard that has refused
# every retrain since. It is still SELECTED in `build_frame` because the degeneracy check
# groups by it; it is simply no longer something the model can learn from.
CATEGORICAL = ["regime_structural", "entry_signal_type"]
REGIME_FEATURES = [
    "regime_structural",
]
# Pre-migration (causal-regime) schema — no longer trained on by default (see FIX-S1-016;
# regime_causal is NULL on the newest rows, which made this schema unusable for live
# scoring), but still what already-shipped champions before the migration were fit on.
# build_frame(include_causal=True) rebuilds exactly this set so an old shipped model can
# still be honestly re-scored against its own schema, e.g. by the model card.
CAUSAL_REGIME_COLS = [
    "regime_causal",
    "prob_causal_trending_up",
    "prob_causal_trending_down",
    "prob_causal_ranging",
    "prob_causal_high_vol",
]
MIN_TURNOVER, MAX_TURNOVER = 0.05, 0.60
N_FOLDS = 5
N_BOOTSTRAP = 20000
SEED = 42
# FIX-S1-010: fraction of the (time-sorted) frame held out from the final fit and used to
# calibrate the thresholds that actually ship. The shipped model must never inherit
# thresholds calibrated against a *different* model — see ``run()``.
CALIBRATION_FRACTION = 0.20
# FIX-S1-010: a regime must hold at least this many calibration-tail rows before its
# approval rate is treated as a hard gate. Matches the n>=30 rule that decides whether a
# regime gets its own calibrated threshold at all.
MIN_REGIME_N = 30
# FIX-S1-012: a gatekeeper whose per-(strategy x regime) approval is bimodal 0/1 is a
# lookup table on strategy identity, not a gate. Refuse to ship if more than this share of
# populated cells sit pinned at either end of the turnover band. The live gk-656f09e2
# champion scored 34/39 (87.2%) on this measure while its aggregate rate (0.1717) sat
# mid-band — see ``check_cell_degeneracy``.
MAX_DEGENERATE_CELL_SHARE = 0.50
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS_DIR = os.path.join(_REPO_ROOT, "models")

PARAM_GRID = {
    "max_depth": [3, 4, 5],
    "n_estimators": [100, 200, 300],
    "learning_rate": [0.03, 0.05, 0.08],
    "subsample": [0.7, 0.8, 0.9],
}


class GatekeeperRefused(Exception):
    pass


def _join_causal_regime(frame: pd.DataFrame, engine) -> pd.DataFrame:
    """Point-in-time join of ``CAUSAL_REGIME_COLS`` onto ``frame`` (bar <= entry_time).

    Same shape as ``attribution.attribute``'s causal-regime tag: only rows where
    ``regime_causal`` was actually filled by a completed walk-forward fold are eligible,
    so this can never pull a label the live system couldn't also have had at that time.
    """
    sql = (
        'SELECT asset_id, granularity, "timestamp" AS bar_time, '
        + ", ".join(CAUSAL_REGIME_COLS)
        + " FROM fact_market_regime_v2 WHERE regime_causal IS NOT NULL"
    )
    with engine.connect() as conn:
        regimes = pd.read_sql(text(sql), conn)
    regimes["bar_time"] = pd.to_datetime(regimes["bar_time"], utc=True)

    parts = []
    for (aid, gran), tg in frame.groupby(["asset_id", "granularity"]):
        rg = (
            regimes[(regimes["asset_id"] == aid) & (regimes["granularity"] == gran)]
            .sort_values("bar_time")
            .copy()
        )
        for col in CAUSAL_REGIME_COLS:
            rg[col] = rg[col].shift(1)
        if rg.empty:
            continue
        merged = pd.merge_asof(
            tg.sort_values("entry_time"),
            rg[["bar_time"] + CAUSAL_REGIME_COLS],
            left_on="entry_time",
            right_on="bar_time",
            direction="backward",
        )
        parts.append(merged)
    if not parts:
        for c in CAUSAL_REGIME_COLS:
            frame[c] = None
        return frame
    return pd.concat(parts, ignore_index=True)


def build_frame(include_causal: bool = False) -> pd.DataFrame:
    """Trades joined point-in-time to structural regime + ATR/ADX features.

    ``include_causal`` additionally joins ``entry_signal_type`` and the pre-migration
    ``CAUSAL_REGIME_COLS`` (see there) — never used for training, only so an
    already-shipped champion fit on that older schema can still be honestly re-scored
    against its own feature set (model_card.py).
    """
    from src.gatekeeper.features import build_inference_features

    engine = get_engine()
    with engine.connect() as conn:
        trades = pd.read_sql(
            text(
                'SELECT outcome_id, "timestamp" AS entry_time, asset_id, granularity, '
                "strategy_id, is_winner, r_multiple, entry_signal_type, "
                # Trade geometry, written by src/outcomes/geometry.py. NULL on rows no
                # rebuild reproduces — which is how the 17,583 orphaned rows of O-4 leave
                # the training frame at the dropna below, rather than by a special case.
                "atr_sl_multiplier, atr_tp_multiplier"
                " FROM fact_trade_outcomes"
            ),
            conn,
        )
        assets = pd.read_sql("SELECT asset_id, symbol FROM dim_asset", conn)
        prices = pd.read_sql(
            text(
                'SELECT asset_id, granularity, timestamp, "Open", high, low, "Close", volume '
                "FROM fact_market_prices"
            ),
            conn,
        )

    trades["entry_time"] = pd.to_datetime(trades["entry_time"], utc=True)
    prices["timestamp"] = pd.to_datetime(prices["timestamp"], utc=True)
    prices.rename(columns={"high": "High", "low": "Low"}, inplace=True)
    asset_map = dict(zip(assets.asset_id, assets.symbol))

    parts = []
    for (aid, gran), tg in trades.groupby(["asset_id", "granularity"]):
        decision_frame = prices[
            (prices["asset_id"] == aid) & (prices["granularity"] == gran)
        ]

        if decision_frame.empty:
            continue

        decision_frame = decision_frame.sort_values("timestamp").set_index("timestamp")

        feats = build_inference_features(decision_frame, granularity=gran)
        feats = feats.reset_index().rename(columns={"timestamp": "bar_time"})
        for col in ["atr_value", "adx_value"]:
            feats[col] = feats[col].shift(1)

        merged = pd.merge_asof(
            tg.sort_values("entry_time"),
            feats.sort_values("bar_time"),
            left_on="entry_time",
            right_on="bar_time",
            direction="backward",
        )
        parts.append(merged)

    frame = pd.concat(parts, ignore_index=True)
    frame["strategy_id"] = frame["strategy_id"].astype(str)

    # `atr_tp_multiplier` is deliberately NOT in this list. A trade that declares no
    # take-profit (trailing-stop, time or opposite-signal exit) has a genuinely absent
    # target, not a missing measurement, and dropping those rows would silently remove a
    # whole class of trade from the training set — ~12% of the rebuilt table, and not a
    # random 12%. The imputer's missingness indicator carries it instead
    # (`_make_preprocessor`).
    #
    # `atr_sl_multiplier` IS required: every trade has a stop, so a NULL there means the
    # row was not produced by this rebuild at all.
    required = ["atr_sl_multiplier"]
    dropna_cols = NUMERIC_REQUIRED + CATEGORICAL + required
    if include_causal:
        frame = _join_causal_regime(frame, engine)
        dropna_cols = dropna_cols + CAUSAL_REGIME_COLS
    frame = frame.dropna(subset=[c for c in dropna_cols if c in frame.columns])
    return frame.sort_values("entry_time").reset_index(drop=True)


def _derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived interaction features (no look-ahead).

    Every input here is known at entry. Nothing reads ``r_multiple``, ``exit_reason`` or
    ``holding_bars`` — those describe the outcome, and deriving a feature from them would
    make the model a function of the label it is meant to predict.

    ``trending_strength`` was dropped from the TRAINED feature set on 2026-09-11. It was
    ``df["adx_value"]`` assigned verbatim — a byte-identical copy of a column already in
    ``NUMERIC``, with a comment ("ADX is already trending strength") saying as much. Two
    identical columns add no information; they split one feature's importance across two
    names, so every gain table understated ADX by roughly half and showed a duplicate
    that read as a distinct signal. Harmless to predictions, actively misleading to
    anyone reading why the model does what it does — which was the entire subject of
    WO-04.

    **It is still COMPUTED here, and must stay that way while a 1.0.0 bundle is live.**
    This function is shared by training and by ``Scorer.score`` precisely so the two
    cannot drift, and ``Scorer`` validates against ``preprocessor.feature_names_in_`` from
    the shipped artifact. The live champion was fit with ``trending_strength``, so
    deleting the line here would make every live signal refuse
    ``MISSING_FEATURE:trending_strength`` and go out unscored — a live regression caused
    by a training-side cleanup. ``NUMERIC_DERIVED`` is what the new model learns from;
    this function is what any live bundle can ask for. Remove the line only once no
    bundle in service was fit on it.
    """
    df = df.copy()
    if "regime_structural" in df.columns:
        df["volatility_regime"] = (df["regime_structural"] == "High-Vol").astype(float)
    if "adx_value" in df.columns:
        # Serve-side back-compat only — deliberately NOT in NUMERIC_DERIVED. See above.
        df["trending_strength"] = df["adx_value"]
    if "atr_value" in df.columns and "adx_value" in df.columns:
        df["adx_over_atr"] = np.where(
            df["atr_value"] > 1e-8, df["adx_value"] / df["atr_value"], 0.0
        )
    # THE payoff feature: reward per unit of risk, as the trade was entered. Both legs are
    # already ATR-normalised, so this is scale-free twice over — comparable across pairs,
    # across volatility regimes and across strategies, which is exactly what `strategy_id`
    # was not.
    #
    # NaN, not a filled-in number, where no take-profit was declared (trailing-stop, time
    # and opposite-signal exits declare none; ~12% of rebuilt rows). The imputer in
    # `_make_preprocessor` handles it and flags it, so "no target" becomes a feature the
    # model can use rather than a fabricated ratio it cannot tell from a real one.
    if "atr_sl_multiplier" in df.columns and "atr_tp_multiplier" in df.columns:
        sl = df["atr_sl_multiplier"]
        df["risk_reward_ratio"] = np.where(
            sl.notna() & (sl > 1e-8), df["atr_tp_multiplier"] / sl, np.nan
        )
    return df


NUMERIC_DERIVED = NUMERIC + [
    "volatility_regime",
    "adx_over_atr",
    "risk_reward_ratio",
]


def _make_preprocessor() -> ColumnTransformer:
    """Numeric: impute-then-scale with an explicit missingness flag. Categorical: one-hot.

    ``SimpleImputer(add_indicator=True)`` is doing real work, not papering over a gap.
    ``atr_tp_multiplier`` — and therefore ``risk_reward_ratio`` — is genuinely absent for
    trades that declare no take-profit (trailing-stop, time and opposite-signal exits;
    ~12% of rebuilt rows). That absence is information: "this strategy did not name a
    target" is a real property of the trade, known at entry.

    Imputing silently would tell the model those trades had a median-sized target, which
    is false. ``add_indicator=True`` appends a binary column instead, so the model sees
    both the filler and the fact that it IS filler and can split on it. The median is fit
    per fold on the training split only — ``ColumnTransformer.fit`` is called on ``tr``
    inside ``_walk_forward``, never on the whole frame — so no OOS row contributes to the
    value used to fill it.

    ``StandardScaler`` cannot accept NaN at all, which is why this cannot be left to
    XGBoost's own native missing-value handling: the scaler would raise first.
    """
    return ColumnTransformer(
        [
            (
                "num",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(strategy="median", add_indicator=True),
                        ),
                        ("scale", StandardScaler()),
                    ]
                ),
                NUMERIC_DERIVED,
            ),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL,
            ),
        ]
    )


def _fit_model(pre: ColumnTransformer, X: pd.DataFrame, y: np.ndarray) -> XGBClassifier:
    """Fit with hyperparameter search, using class-weight for imbalanced winners (~38%)."""
    Xt = pre.transform(X)
    scale_pos = max(1.0, float((y == 0).sum() / max(1, (y == 1).sum())))
    base = XGBClassifier(
        eval_metric="logloss",
        random_state=SEED,
        n_jobs=4,
        verbosity=0,
        scale_pos_weight=scale_pos,
    )
    gs = GridSearchCV(
        base,
        PARAM_GRID,
        scoring="neg_log_loss",
        cv=3,
        n_jobs=4,
        verbose=0,
    )
    gs.fit(Xt, y)
    logger.info("best params: %s", gs.best_params_)
    return gs.best_estimator_


def _scores(model, pre, X) -> np.ndarray:
    return model.predict_proba(pre.transform(X))[:, 1]


def _walk_forward(frame: pd.DataFrame) -> Dict[str, Any]:
    """Expanding-window folds -> aggregated OOS approved/rejected returns + per-regime thresholds."""
    blocks = np.array_split(frame, N_FOLDS + 1)
    approved_all: List[float] = []
    rejected_all: List[float] = []
    last_thresholds: Dict[str, float] = {}
    feature_cols = NUMERIC_DERIVED + CATEGORICAL
    for i in range(1, N_FOLDS + 1):
        train = pd.concat(blocks[:i]).reset_index(drop=True)
        oos = blocks[i]
        cut = int(len(train) * 0.8)
        tr, val = train.iloc[:cut], train.iloc[cut:]
        if len(tr) < 200 or len(val) < 50 or len(oos) < 50:
            continue
        pre = _make_preprocessor().fit(tr[feature_cols])
        model = _fit_model(pre, tr[feature_cols], tr["is_winner"].to_numpy())
        val_scores = _scores(model, pre, val[feature_cols])
        thr_map = _calibrate_regime_thresholds(val, val_scores)
        last_thresholds = thr_map
        oos_scores = _scores(model, pre, oos[feature_cols])
        approved_mask = _apply_thresholds(oos, oos_scores, thr_map)
        approved_all.extend(oos["r_multiple"].to_numpy()[approved_mask].tolist())
        rejected_all.extend(oos["r_multiple"].to_numpy()[~approved_mask].tolist())
    return {
        "approved": approved_all,
        "rejected": rejected_all,
        "thresholds": last_thresholds,
    }


def _calibrate_regime_thresholds(
    df: pd.DataFrame, scores: np.ndarray
) -> Dict[str, float]:
    thr_map: Dict[str, float] = {}
    for regime, idx in df.groupby("regime_structural").groups.items():
        pos = df.index.get_indexer(idx)
        s = scores[pos]
        r = df["r_multiple"].to_numpy()[pos]
        if len(s) >= 30:
            thr, _ = TH.calibrate_threshold(s, r, MIN_TURNOVER, MAX_TURNOVER)
            thr_map[str(regime)] = thr
    thr_map["fallback"], _ = TH.calibrate_threshold(
        scores, df["r_multiple"].to_numpy(), MIN_TURNOVER, MAX_TURNOVER
    )
    return thr_map


def _apply_thresholds(
    df: pd.DataFrame, scores: np.ndarray, thr_map: Dict[str, float]
) -> np.ndarray:
    thr = (
        df["regime_structural"]
        .map(lambda r: thr_map.get(str(r), thr_map["fallback"]))
        .to_numpy()
    )
    return scores >= thr


def per_regime_approval(
    df: pd.DataFrame, scores: np.ndarray, thr_map: Dict[str, float]
) -> Dict[str, Dict[str, float]]:
    """Approval rate per regime under ``thr_map`` (``{regime: {n, approval}}``).

    Regimes below ``MIN_REGIME_N`` are reported but not independently guarded: they get
    the fallback threshold (``_calibrate_regime_thresholds`` only fits a per-regime
    threshold at n>=30), and an approval rate estimated from a handful of rows is noise,
    so failing a run on it would be a coin flip rather than a safety guarantee.
    """
    approved = _apply_thresholds(df, scores, thr_map)
    out: Dict[str, Dict[str, float]] = {}
    for regime, idx in df.groupby("regime_structural").groups.items():
        pos = df.index.get_indexer(idx)
        out[str(regime)] = {
            "n": int(len(pos)),
            "approval": float(approved[pos].mean()) if len(pos) else 0.0,
        }
    return out


def check_regime_turnover(
    approvals: Dict[str, Dict[str, float]],
    min_turnover: float = MIN_TURNOVER,
    max_turnover: float = MAX_TURNOVER,
    min_n: int = MIN_REGIME_N,
) -> List[str]:
    """Return per-regime turnover-band violations (empty == all populated regimes OK).

    FIX-S1-010: the band was previously enforced on the AGGREGATE approval rate only, so
    a single regime could starve to near-zero approval — or saturate — while the overall
    figure sat comfortably mid-band. That is a hole in the default-safe axiom: a regime
    with no approvals is a regime the system silently stops trading, with nothing in the
    manifest or the logs saying so.

    Not observed to fire on the 2026-07-24 recalibration (the thinnest regime,
    Trending-Up, held 6.6% on the calibration tail). This closes a latent gap rather than
    a live failure — a distinction worth keeping in mind when reading the fix register.
    """
    problems: List[str] = []
    for regime, stats in sorted(approvals.items()):
        if stats["n"] < min_n:
            continue
        rate = stats["approval"]
        if rate < min_turnover or rate > max_turnover:
            problems.append(
                f"{regime}: approval={rate:.4f} (n={int(stats['n'])}) outside "
                f"[{min_turnover},{max_turnover}]"
            )
    return problems


def per_cell_approval(
    df: pd.DataFrame, scores: np.ndarray, thr_map: Dict[str, float]
) -> Dict[str, Dict[str, float]]:
    """Approval rate per (strategy_id x regime_causal) cell.

    FIX-S1-012: the aggregate band and the per-regime band are both blind to a policy
    that is degenerate along the STRATEGY axis. Keyed ``"<strategy_id>|<regime>"``.
    """
    approved = _apply_thresholds(df, scores, thr_map)
    out: Dict[str, Dict[str, float]] = {}
    for (sid, regime), idx in df.groupby(
        ["strategy_id", "regime_structural"]
    ).groups.items():
        pos = df.index.get_indexer(idx)
        out[f"{sid}|{regime}"] = {
            "n": int(len(pos)),
            "approval": float(approved[pos].mean()) if len(pos) else 0.0,
        }
    return out


def check_cell_degeneracy(
    approvals: Dict[str, Dict[str, float]],
    min_n: int = MIN_REGIME_N,
    max_degenerate_share: float = MAX_DEGENERATE_CELL_SHARE,
) -> List[str]:
    """Refuse a gatekeeper that is a lookup table rather than a gate.

    FIX-S1-012 — the defect this exists to stop, measured on the live 2026-07-05 champion
    (``gk-656f09e2``) on 2026-08-02:

    * ``strategy_id`` one-hot carried **96.78%** of the model's gain importance;
      ``regime_causal`` carried **0.21%** and all nine numeric features 2.65% combined.
      The "regime-aware gatekeeper" had learned strategy identity and essentially nothing
      else, emitting a near-constant score per strategy.
    * Per (strategy x regime) at H1: **23 of 40 cells approved <=5%** (median 0.0000) and
      **12 of 40 approved >=95%**. Almost nothing in between.
    * The aggregate approval rate was 0.1717 — comfortably inside ``turnover_band``
      [0.05, 0.60] — so both the aggregate gate and the per-regime gate passed cleanly.

    Downstream, System 2 traded the one strategy that vetting had qualified (id 10), which
    sat in the 100% group in every regime, and measured a live approval rate of **0.9995**
    against a published ``oos_approval_rate`` of 0.3379. The published number was a
    population average across ten strategies and had no meaning for a consumer trading one.

    A gate whose approval is bimodal 0/1 across cells is not gating: it reproduces the
    strategy selection MODEL-005 already performed. Fail closed instead of shipping it.
    """
    populated = {k: v for k, v in approvals.items() if v["n"] >= min_n}
    if not populated:
        return []
    degenerate = {
        k: v
        for k, v in populated.items()
        if v["approval"] <= min_turnover_floor()
        or v["approval"] >= 1.0 - min_turnover_floor()
    }
    share = len(degenerate) / len(populated)
    if share <= max_degenerate_share:
        return []
    worst = sorted(degenerate.items(), key=lambda kv: -kv[1]["n"])[:6]
    detail = ", ".join(
        f"{k} approval={v['approval']:.3f} (n={v['n']})" for k, v in worst
    )
    # Report the MEASUREMENT, and name both explanations for it.
    #
    # This message used to assert "The model is discriminating on strategy identity, not
    # market state." That was a safe inference while `strategy_id` was the only
    # per-strategy-constant feature in the basis, and it is false as of FEATURE_SET_VERSION
    # 2.0.0 — `strategy_id` is not a feature at all, and the run of 2026-09-11 emitted that
    # sentence about a model that could not possibly have seen it. Trade geometry is also
    # near-constant within a strategy (13 of 23 strategies have an R:R coefficient of
    # variation below 0.10; six have sd exactly 0.000), so bimodal approval is now equally
    # consistent with the model working as intended.
    #
    # CLAUDE.md's rule about hardcoded values in rejection reasons applies to asserted
    # causes as well as to thresholds: a rejection that names a cause it cannot verify
    # sends the next reader somewhere the evidence does not support.
    return [
        f"{len(degenerate)} of {len(populated)} populated (strategy x regime) cells are "
        f"degenerate (approval <={min_turnover_floor():.2f} or >={1-min_turnover_floor():.2f}) "
        f"— {share:.1%} > {max_degenerate_share:.0%} allowed. This check does not identify "
        "WHY: approval near-constant within a strategy means the model is keying on "
        "something that does not vary inside one, which is either strategy identity "
        "(the FIX-S1-012 defect) or a genuine feature that is fixed by that strategy's "
        "design. Read the gain importances to tell them apart. "
        f"Worst: {detail}"
    ]


def min_turnover_floor() -> float:
    """Edge width that counts a cell as degenerate (shared by both ends of the band)."""
    return MIN_TURNOVER


def run(register_mlflow: bool = True, dry_run: bool = False) -> Dict[str, Any]:
    """Train the gatekeeper and write the champion bundle.

    ``dry_run=True`` (the FIX-S1-005 default invocation) writes a PROPOSED bundle
    (``models/proposed_champion_model.pkl`` / ``proposed_champion_preprocessor.pkl`` /
    ``proposed_champion_manifest.json``) and NEVER overwrites the live champion bundle
    — honouring global rule #1 (log-only, no auto-promotion). The trainer previously
    always overwrote ``champion_model.pkl`` etc. (silent auto-promote); that is now
    gated behind the explicit (non-dry-run) path.
    """
    frame = build_frame()

    # Exclude holdout trades to avoid data contamination
    from src.validation.walk_forward import HOLDOUT_CUT_DATE

    cut_dt = pd.to_datetime(HOLDOUT_CUT_DATE, utc=True)
    frame = frame[frame["entry_time"] < cut_dt].copy()

    frame = _derive_features(frame)

    logger.info(
        "Training frame: %d trades, outperformer rate %.3f",
        len(frame),
        frame["is_winner"].mean(),
    )

    wf = _walk_forward(frame)
    uplift, p_value, significant = TH.oos_uplift_test(
        wf["approved"],
        wf["rejected"],
        n_bootstrap=N_BOOTSTRAP,
        seed=SEED,
    )
    n_app, n_rej = len(wf["approved"]), len(wf["rejected"])
    oos_approval = n_app / (n_app + n_rej) if (n_app + n_rej) else 0.0
    logger.info(
        "OOS uplift=%.6f p=%.6f sig=%s approval=%.4f n_approved=%d n_rejected=%d",
        uplift,
        p_value,
        significant,
        oos_approval,
        n_app,
        n_rej,
    )

    if TH.is_degenerate(oos_approval, MIN_TURNOVER, MAX_TURNOVER):
        raise GatekeeperRefused(
            f"degenerate walk-forward approval rate {oos_approval:.3f} outside "
            f"[{MIN_TURNOVER},{MAX_TURNOVER}]"
        )

    # FIX-S1-010 (threshold/model calibration mismatch) --------------------------------
    # The trainer previously shipped ``wf["thresholds"]`` — the map calibrated on the LAST
    # walk-forward fold's validation split — attached to a model refit on the ENTIRE frame.
    # Two different models: the fold model's score distribution is not the shipped model's,
    # so the thresholds landed at an arbitrary point on the shipped model's distribution.
    # Measured impact of that bug on the 2026-07-05 champion: manifest advertised a 33.79%
    # approval rate; the shipped artifact actually approved 17.23%, and the per-regime
    # ordering was scrambled (the tightest gates sat on the highest-mean-R regimes).
    #
    # Fix: hold out the most recent CALIBRATION_FRACTION of the (time-sorted) frame, fit the
    # shipped model on the head, and calibrate the shipped thresholds on the held-out tail
    # using THAT model's own scores. Costs some training data; buys thresholds that are
    # calibrated, out-of-sample, against the artifact that actually ships.
    feature_cols = NUMERIC_DERIVED + CATEGORICAL
    cut = int(len(frame) * (1.0 - CALIBRATION_FRACTION))
    fit_df, cal_df = frame.iloc[:cut], frame.iloc[cut:]
    if len(fit_df) < 200 or len(cal_df) < 50:
        raise GatekeeperRefused(
            f"insufficient data to fit+calibrate (fit={len(fit_df)}, cal={len(cal_df)})"
        )
    pre = _make_preprocessor().fit(fit_df[feature_cols])
    model = _fit_model(pre, fit_df[feature_cols], fit_df["is_winner"].to_numpy())

    cal_scores = _scores(model, pre, cal_df[feature_cols])
    dynamic_thresholds = _calibrate_regime_thresholds(cal_df, cal_scores)

    # Enforce the turnover band on the SHIPPED artifact, not just on the walk-forward
    # method. Previously ``is_degenerate`` only ever saw the fold-aggregated rate, so the
    # [MIN_TURNOVER, MAX_TURNOVER] business rule never bound on what was published.
    shipped_approval = float(
        _apply_thresholds(cal_df, cal_scores, dynamic_thresholds).mean()
    )
    logger.info(
        "shipped-model calibration: fit=%d cal=%d approval=%.4f thresholds=%s",
        len(fit_df),
        len(cal_df),
        shipped_approval,
        {k: round(v, 4) for k, v in dynamic_thresholds.items()},
    )
    if TH.is_degenerate(shipped_approval, MIN_TURNOVER, MAX_TURNOVER):
        raise GatekeeperRefused(
            f"degenerate SHIPPED approval rate {shipped_approval:.3f} outside "
            f"[{MIN_TURNOVER},{MAX_TURNOVER}] — thresholds do not fit the shipped model"
        )

    # FIX-S1-010: the aggregate band above can sit mid-range while one regime starves.
    # Fail closed on any populated regime outside the band rather than ship a policy that
    # silently stops trading a market condition.
    regime_approvals = per_regime_approval(cal_df, cal_scores, dynamic_thresholds)
    logger.info(
        "per-regime approval (calibration tail): %s",
        {k: round(v["approval"], 4) for k, v in sorted(regime_approvals.items())},
    )
    regime_problems = check_regime_turnover(regime_approvals)
    if regime_problems:
        raise GatekeeperRefused(
            "per-regime turnover band violated — refusing to ship a starved/saturated "
            "policy:\n  " + "\n  ".join(regime_problems)
        )

    # FIX-S1-012: the two gates above are both blind along the strategy axis. Refuse a
    # model that merely re-states MODEL-005's strategy selection.
    cell_approvals = per_cell_approval(cal_df, cal_scores, dynamic_thresholds)
    cell_problems = check_cell_degeneracy(cell_approvals)
    logger.info(
        "per-(strategy x regime) approval: %d populated cells, %d degenerate",
        sum(1 for v in cell_approvals.values() if v["n"] >= MIN_REGIME_N),
        sum(
            1
            for v in cell_approvals.values()
            if v["n"] >= MIN_REGIME_N
            and (v["approval"] <= MIN_TURNOVER or v["approval"] >= 1.0 - MIN_TURNOVER)
        ),
    )
    if cell_problems:
        raise GatekeeperRefused(
            "per-(strategy x regime) degeneracy check failed:\n  "
            + "\n  ".join(cell_problems)
        )

    # FIX-S1-009 Fix 5: route the bundle write through the single governed
    # promote path. atomic_promote is the SOLE writer of champion_*/proposed_
    # champion_* in System-1 — it stages each artifact and os.replace()-s it into
    # place, then appends the ``sha256`` map to the manifest (last key, so the
    # on-disk schema and key order are unchanged from the prior inline write).
    manifest = {
        "model_type": "xgboost",
        "schema_version": "1.0.0",
        "features": feature_cols,
        "regime_features": REGIME_FEATURES,
        "dynamic_thresholds": dynamic_thresholds,
        "turnover_band": [MIN_TURNOVER, MAX_TURNOVER],
        # FIX-S1-010: the approval rate of the ARTIFACT IN THIS BUNDLE, measured on the
        # held-out calibration tail with this model's own scores. Consumers sizing or
        # capacity-planning off an approval rate must read THIS key. ``oos_uplift
        # .oos_approval_rate`` below is a property of the walk-forward fold models (it is
        # the evidence for the uplift claim) and is NOT the shipped model's behaviour.
        "shipped_approval_rate": round(shipped_approval, 4),
        "shipped_approval_by_regime": {
            k: round(v["approval"], 4) for k, v in sorted(regime_approvals.items())
        },
        # FIX-S1-012: the per-cell rates a downstream consumer actually needs. A consumer
        # trading ONE strategy cannot use an aggregate rate: on the live gk-656f09e2
        # champion the aggregate was 0.1717 while strategy 10 approved at ~1.00, which is
        # what System 2 measured (0.9995) and could not reconcile against 0.3379.
        "shipped_approval_by_strategy_regime": {
            k: round(v["approval"], 4)
            for k, v in sorted(cell_approvals.items())
            if v["n"] >= MIN_REGIME_N
        },
        "calibration": {
            "method": "held-out tail of the time-sorted frame, shipped-model scores",
            "calibration_fraction": CALIBRATION_FRACTION,
            "n_fit": int(len(fit_df)),
            "n_calibration": int(len(cal_df)),
            "per_regime_band_enforced": True,
            "min_regime_n": MIN_REGIME_N,
        },
        "oos_uplift": {
            "uplift": round(uplift, 6),
            "p_value": round(p_value, 6),
            "significant": significant,
            "oos_approval_rate": round(oos_approval, 4),
            "approval_rate_scope": "walk_forward_fold_models_not_shipped_artifact",
            "n_approved": n_app,
            "n_rejected": n_rej,
            "n_folds": N_FOLDS,
        },
        "regime_model_version": REGIME_MODEL_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "n_train": int(len(frame)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
    }
    paths = atomic_promote(
        model=model,
        manifest=manifest,
        models_dir=MODELS_DIR,
        preprocessor=pre,
        dry_run=dry_run,
    )
    model_path = paths["model_path"]
    manifest_path = paths["manifest_path"]

    result = {
        "n_train": len(frame),
        "oos_uplift": uplift,
        "p_value": p_value,
        "significant": significant,
        "oos_approval_rate": oos_approval,
        "shipped_approval_rate": shipped_approval,
        "dynamic_thresholds": dynamic_thresholds,
        "manifest": manifest_path,
        "model_path": model_path,
        "dry_run": dry_run,
    }
    if register_mlflow:
        result["mlflow_run_id"] = _register_mlflow(manifest)
    logger.info(
        "MODEL-006 %s bundle written: %s",
        "PROPOSED (dry-run, live champion untouched)" if dry_run else "champion",
        model_path,
    )
    return result


def _register_mlflow(manifest) -> str:
    try:
        import mlflow
        from src.features.feature_pipeline import _resolve_mlflow_uri

        mlflow.set_tracking_uri(_resolve_mlflow_uri())
        mlflow.set_experiment("system1-gatekeeper")
        with mlflow.start_run(run_name="gatekeeper") as run:
            mlflow.log_param("regime_features", ",".join(REGIME_FEATURES))
            mlflow.log_param("features", ",".join(manifest["features"]))
            mlflow.log_param("turnover_band", str(manifest["turnover_band"]))
            mlflow.log_metric("oos_uplift", manifest["oos_uplift"]["uplift"])
            mlflow.log_metric("oos_p_value", manifest["oos_uplift"]["p_value"])
            mlflow.log_metric(
                "oos_approval_rate", manifest["oos_uplift"]["oos_approval_rate"]
            )
            mlflow.log_artifact(os.path.join(MODELS_DIR, "champion_manifest.json"))
            return run.info.run_id
    except Exception as e:  # noqa: BLE001
        logger.error("MLflow registration failed: %s", e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="MODEL-006 gatekeeper trainer")
    parser.add_argument("--no-mlflow", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write models/proposed_champion_* and never overwrite the live champion "
        "(log-only; global rule #1). Default invocation for FIX-S1-005.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    try:
        print(run(register_mlflow=not args.no_mlflow, dry_run=args.dry_run))
    except GatekeeperRefused as e:
        logger.error("GATEKEEPER REFUSED: %s", e)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
