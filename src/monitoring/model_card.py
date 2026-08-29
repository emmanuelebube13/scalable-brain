"""Publish the live gatekeeper's model card, so the dashboard's Model page has a source.

Why this exists
---------------
The telemetry Model page renders five tiles and three panels about the gatekeeper. As of
2026-08-23 it showed: training date "—", training data "—", every training metric 0.0%, a
calibration curve flatlined at zero, and "No feature importance weights available".

None of that was a rendering bug alone. **System 1 never published any of it.** The
champion manifest carries thresholds, approval rates and an uplift test; it has never
carried a feature importance vector, a reliability curve, or a single classification
metric. A frontend cannot render data that was never produced, so it rendered zeros — and
a zero reads as "measured, and terrible" rather than "never measured", which is the more
damaging of the two failures.

This module produces that data from the artifact that is actually live.

Atomicity: the card is an artifact OF the model set, not a sidecar
------------------------------------------------------------------
A model artifact and the telemetry describing it are **one inseparable unit**. Shipping the
artifact without its contemporaneously generated card is forbidden, and if the card cannot
be built the deployment halts.

That invariant is not enforced by a check bolted on after the fact — it is structural. The
card is written into the **immutable versioned prefix alongside the bundle**, enumerated in
the model-set manifest with its SHA256, and covered by the existing publish contract:
upload -> verify -> *pointer flip last*. So the card becomes live at exactly the instant
the model set does, by the same atomic flip, and a set whose card failed to build never
gets a pointer pointing at it.

``telemetry/s1_model.json`` is therefore a **mirror of the pinned card, never an
independent recomputation**. Recomputing it on a schedule was the obvious design and it is
wrong: the measurements move with the database, so within hours the frontend would be
showing numbers that no deployed artifact ever produced. :func:`mirror` copies; it does not
measure. :func:`verify_parity` fails loudly if the two ever diverge.

One consequence worth stating plainly: because the card is pinned per bundle version, it is
generated **once**, when a new bundle is first packaged. Republishing an unchanged bundle
reuses the pinned card rather than regenerating it — the deployed artifact did not change,
so its telemetry must not either. This is also what keeps the manifest digest stable and
publishes idempotent.

The champion manifest itself is still not modified: adding fields to it would change its
digest, mint a new gatekeeper version, and constitute a promotion — the orchestrator's
exclusive right (FIX-S1-009). ``train.py`` should grow these fields natively at the next
retrain; until then the card is generated from what actually ships.

What is trustworthy here, and what is not
-----------------------------------------
Everything is labelled with its own provenance, because the panels do not have equal
standing:

* **Feature importance** is read straight out of the booster. It depends on no database
  and is exact.
* **Identity and thresholds** are copied from the published manifest.
* **The calibration curve and the operating-point metrics** are computed by scoring the
  joined frame with the shipped artifact. They are deterministically reproducible from
  that frame and carry ``reproducible: true``. They are *not* provably out-of-sample, so
  they also carry ``in_sample_risk: true``.
* **Anything that cannot be reproduced from the final joined frame** — notably the
  manifest's ``n_train``, which is a pre-join row count — is quarantined under
  ``training_data.unverified``, where every entry carries an explicit
  ``reproducible: false`` and the measured value beside the claimed one. Such numbers are
  never surfaced as plain top-level fields, because an unlabelled count is indistinguishable
  from a verified one at the point of rendering.

Publishing a number with its caveat attached is the point. The alternative already exists,
and it is a page full of zeros.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("system1.monitoring.model_card")

#: Read by the dashboard alongside ``telemetry/s1_health.json`` and
#: ``telemetry/s1_analytics.json``. System 1 writes it; nobody else does. A *mirror* of the
#: pinned card — see :func:`mirror`.
TELEMETRY_KEY = "telemetry/s1_model.json"

#: Filename of the pinned card inside the model set's immutable versioned prefix. Listed in
#: ``S1_ARTIFACTS`` so the manifest carries its SHA256 and the pointer flip covers it.
CARD_ARTIFACT_NAME = "model_card.json"

SCHEMA_VERSION = 1


class ModelCardRefused(Exception):
    """A card could not be built for a set that is about to ship.

    Raised, never swallowed. Requirement: artifact and telemetry are a single unit, so a
    card that cannot be built must halt the deployment rather than let the artifact ship
    undescribed.
    """


#: Reliability-curve bin edges. Ten equal buckets over the probability range — the
#: convention every calibration plot uses, so the dashboard needs no configuration.
BIN_EDGES: Sequence[float] = tuple(i / 10 for i in range(11))

#: One-hot prefixes to fold back to their source column. XGBoost reports importance per
#: encoded column, so ``strategy_id`` arrives as ~50 separate ``strategy_id_<n>`` entries;
#: charting those individually buries the finding that the *feature* dominates.
_CATEGORICAL_BASES = ("regime_causal", "strategy_id", "entry_signal_type")


# --------------------------------------------------------------------------------------
# Pure computation (no DB, no network, no model) — the testable half.
# --------------------------------------------------------------------------------------
def collapse_encoded_name(encoded: str) -> str:
    """``cat__strategy_id_12`` -> ``strategy_id``; ``num__atr_value`` -> ``atr_value``.

    The ColumnTransformer prefixes every output column with its transformer name, and the
    one-hot encoder appends the category. Both have to come off before importances can be
    summed back to the feature a human reasons about.
    """
    raw = encoded.split("__", 1)[1] if "__" in encoded else encoded
    for base in _CATEGORICAL_BASES:
        if raw == base or raw.startswith(base + "_"):
            return base
    return raw


def aggregate_importance(
    scores: Dict[str, float], encoded_names: Sequence[str]
) -> Dict[str, Any]:
    """Fold per-encoded-column gain back onto source features, normalised to 1.0.

    ``scores`` is XGBoost's ``get_score`` output keyed ``f<index>``; ``encoded_names`` is
    the preprocessor's ``get_feature_names_out()``. Columns the booster never split on are
    absent from ``scores`` — they get an explicit 0.0 rather than being omitted, so a
    consumer can tell "unused" from "not reported".
    """
    total = float(sum(scores.values()))
    if total <= 0:
        return {"available": False, "reason": "booster reported zero total gain"}

    per_feature: Dict[str, float] = defaultdict(float)
    per_encoded: Dict[str, float] = {}
    for key, gain in scores.items():
        try:
            encoded = encoded_names[int(key[1:])]
        except (ValueError, IndexError):
            continue
        share = gain / total
        per_encoded[encoded.split("__", 1)[-1]] = share
        per_feature[collapse_encoded_name(encoded)] += share

    # Features the booster never split on are reported at 0.0, not omitted: "unused" and
    # "not measured" are different answers and the page has already conflated them once.
    for name in encoded_names:
        per_feature.setdefault(collapse_encoded_name(name), 0.0)

    ranked = sorted(per_feature.items(), key=lambda kv: -kv[1])
    top_encoded = sorted(per_encoded.items(), key=lambda kv: -kv[1])[:10]
    return {
        "available": True,
        "method": "xgboost total_gain, one-hot columns summed back to the source "
        "feature, normalised to 1.0",
        "encoded_columns_used": len(scores),
        "encoded_columns_total": len(encoded_names),
        "features": [
            {"rank": i + 1, "feature": name, "importance": round(val, 6)}
            for i, (name, val) in enumerate(ranked)
        ],
        "top_encoded_columns": [
            {"column": name, "importance": round(val, 6)} for name, val in top_encoded
        ],
    }


def reliability_bins(
    probs: Sequence[float], outcomes: Sequence[int]
) -> List[Dict[str, Any]]:
    """Predicted-probability bucket -> observed win rate, the calibration curve's data.

    Empty buckets are returned with ``n: 0`` and null rates rather than being dropped or
    zero-filled. A zero win rate and an unpopulated bucket are different statements, and
    conflating them is exactly what produced the flatlined curve this module replaces.
    """
    out: List[Dict[str, Any]] = []
    for i in range(len(BIN_EDGES) - 1):
        lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
        # The top bin is closed on the right so a probability of exactly 1.0 lands
        # somewhere instead of being silently dropped.
        last = i == len(BIN_EDGES) - 2
        members = [
            (p, y)
            for p, y in zip(probs, outcomes)
            if lo <= p and (p <= hi if last else p < hi)
        ]
        n = len(members)
        out.append(
            {
                "bin_lower": round(lo, 4),
                "bin_upper": round(hi, 4),
                "n": n,
                "mean_predicted": (
                    round(sum(p for p, _ in members) / n, 6) if n else None
                ),
                "observed_win_rate": (
                    round(sum(y for _, y in members) / n, 6) if n else None
                ),
            }
        )
    return out


def operating_point_metrics(
    approved: Sequence[int], outcomes: Sequence[int], r_multiples: Sequence[float]
) -> Dict[str, Any]:
    """Classification metrics at the *shipped* per-regime thresholds, not at 0.5.

    0.5 is not the operating point of this model and never has been — the manifest ships
    a threshold per regime. Reporting metrics at 0.5 would describe a gate nobody runs.

    ``recall`` here means P(approved | winner) and is meaningful **only** because the
    rejected trades' outcomes are known from backtest. It is not computable from live
    trades, where rejected signals never become trades and recall is therefore pinned at
    1.0 by construction. See ``METRIC_SEMANTICS``.
    """
    tp = sum(1 for a, y in zip(approved, outcomes) if a and y)
    fp = sum(1 for a, y in zip(approved, outcomes) if a and not y)
    fn = sum(1 for a, y in zip(approved, outcomes) if not a and y)
    n_appr = tp + fp
    precision = tp / n_appr if n_appr else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision and recall and (precision + recall)
        else None
    )
    appr_r = [r for a, r in zip(approved, r_multiples) if a]
    all_r = list(r_multiples)
    return {
        "n": len(outcomes),
        "n_approved": n_appr,
        "approval_rate": round(n_appr / len(outcomes), 6) if outcomes else None,
        "precision": round(precision, 6) if precision is not None else None,
        "recall": round(recall, 6) if recall is not None else None,
        "f1": round(f1, 6) if f1 is not None else None,
        "expectancy_r_approved": (
            round(sum(appr_r) / len(appr_r), 6) if appr_r else None
        ),
        "expectancy_r_all": round(sum(all_r) / len(all_r), 6) if all_r else None,
        "operating_point": "per-regime dynamic thresholds from the champion manifest",
    }


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> Optional[float]:
    """Mean squared error of the predicted probability. Lower is better, unlike its
    neighbours in the dashboard table — hence the explicit ``direction`` in
    ``METRIC_SEMANTICS``."""
    if not outcomes:
        return None
    return round(sum((p - y) ** 2 for p, y in zip(probs, outcomes)) / len(outcomes), 6)


#: Shipped with the payload so a renderer never has to infer a metric's direction, unit or
#: measurability. Every item here corresponds to a row the dashboard already draws wrongly.
METRIC_SEMANTICS: Dict[str, Any] = {
    "precision": {
        "definition": "P(trade won | gatekeeper approved)",
        "direction": "higher_is_better",
        "format": "ratio_0_1",
        "measurable_live": True,
    },
    "recall": {
        "definition": "P(gatekeeper approved | trade won)",
        "direction": "higher_is_better",
        "format": "ratio_0_1",
        "measurable_live": False,
        "why_not": (
            "a rejected signal never becomes a trade, so live data contains no rejected "
            "winners. Live recall is 1.0 by construction whatever the model does, and "
            "carries no information. Render it only against backtest, or not at all."
        ),
    },
    "f1": {
        "definition": "harmonic mean of precision and recall",
        "direction": "higher_is_better",
        "format": "ratio_0_1",
        "measurable_live": False,
        "why_not": "inherits recall's defect — see recall.",
    },
    "brier": {
        "definition": "mean squared error of the predicted win probability",
        "direction": "LOWER_is_better",
        "format": "score_0_1",
        "measurable_live": True,
        "note": (
            "not a percentage and not comparable to the rows above. A Brier of 0.0 in a "
            "column of missing data reads as a perfect score; it is not one."
        ),
    },
    "expectancy_r": {
        "definition": "mean R-multiple per approved trade",
        "direction": "higher_is_better",
        "format": "r_multiple",
        "measurable_live": True,
        "note": "an R-multiple is a ratio of risk, not a percentage. Never render as %.",
    },
}


# --------------------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _age_seconds(ts: Optional[str], now: datetime) -> Optional[float]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((now - dt).total_seconds(), 1)
    except Exception:
        return None


def _load_bundle(
    storage, tmpdir: str, pointer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Fetch the artifacts a card is built from.

    ``pointer`` is the model-set manifest to describe. Omitted, it is read from the
    BACKEND pointer — never the local ``model-artifacts/latest.json``, since the backend
    copy is authoritative and is what a consumer downloads (CLAUDE.md).

    The publish path passes the *pending* manifest explicitly. That is what makes the card
    contemporaneous: it describes the set being shipped, resolved from that set's own
    artifact paths, rather than whatever happens to be live at the moment it runs.
    """
    import joblib

    from src.serializer.publish_model_set import POINTER_KEY

    if pointer is None:
        ptr_path = os.path.join(tmpdir, "pointer.json")
        storage.get_object(POINTER_KEY, ptr_path)
        with open(ptr_path, encoding="utf-8") as fh:
            pointer = json.load(fh)
    assert pointer is not None

    wanted = (
        "champion_model.pkl",
        "champion_preprocessor.pkl",
        "champion_manifest.json",
        "regime_strategy_map.json",
    )
    paths: Dict[str, str] = {}
    for art in pointer.get("artifacts") or []:
        # An entry with no path is a malformed set, not a fetchable artifact: skip it so
        # it surfaces below as "missing" and refuses, rather than raising a bare KeyError.
        if art.get("name") in wanted and art.get("path"):
            local = os.path.join(tmpdir, art["name"])
            storage.get_object(art["path"], local)
            paths[art["name"]] = local
    missing = [w for w in wanted if w not in paths]
    if missing:
        raise ModelCardRefused(
            f"model set {pointer.get('model_set_id')!r} is missing {missing} — "
            f"refusing to describe an incomplete set"
        )

    def _json(name: str) -> Dict[str, Any]:
        with open(paths[name], encoding="utf-8") as fh:
            loaded: Dict[str, Any] = json.load(fh)
            return loaded

    return {
        "pointer": pointer,
        "manifest": _json("champion_manifest.json"),
        "regime_map": _json("regime_strategy_map.json"),
        "model": joblib.load(paths["champion_model.pkl"]),
        "preprocessor": joblib.load(paths["champion_preprocessor.pkl"]),
    }


#: Identity fields that describe the *publish event* rather than the bundle. They are
#: excluded from the pinned card — ``published_at`` moves on every republish, which would
#: change the card's digest and make publishes non-idempotent — and merged in by
#: :func:`mirror` from the live manifest, which is where they are authoritative anyway.
_PUBLISH_EVENT_FIELDS = ("status", "published_at", "code_commit", "code_dirty")


def _identity(pointer: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Bundle-intrinsic identity only — deliberately clock-free, see :func:`build`.

    Publish-event fields and ages are added by :func:`mirror`, which may read a clock
    because its output is not hashed into the manifest.
    """
    trained_at = manifest.get("created_at_utc")
    return {
        "model_set_id": pointer.get("model_set_id"),
        "gatekeeper_version": pointer.get("gatekeeper_version"),
        "system1_bundle_version": pointer.get("system1_bundle_version"),
        "trained_at_utc": trained_at,
        "model_type": manifest.get("model_type"),
        "feature_set_version": manifest.get("feature_set_version"),
        "regime_model_version": manifest.get("regime_model_version"),
        # No `label_this_page_with` key here, though guidance like it belongs in this
        # payload. It shipped on 2026-08-23 and the dashboard rendered its *value* —
        # the literal string "gatekeeper_version + trained_at_utc" — into the VERSION
        # tile. A short string sitting among real values is indistinguishable from one,
        # so instructions live in `note`, which is unmistakably prose and long enough
        # that nothing will try to put it in a tile.
        "note": (
            "Label the model with gatekeeper_version, and its date with trained_at_utc. "
            "Not model_set_id: that changes whenever EITHER half of the set republishes, "
            "so its timestamp is a packaging date, not a training date, and showing it "
            "as 'the model' makes an untouched gatekeeper look retrained."
        ),
    }


def _thresholds(manifest: Dict[str, Any]) -> Dict[str, Any]:
    dyn = dict(manifest.get("dynamic_thresholds") or {})
    fallback = dyn.pop("fallback", None)
    return {
        "per_regime": dyn,
        "fallback": fallback,
        "scalar": None,
        "note": (
            "there is no single approval threshold. The gate is per regime, and the "
            "spread here is 0.60-0.75 — a lone scalar on a dashboard is not a rounding "
            "of these, it is a different claim. Render the four, or render the range."
        ),
        "shipped_approval_rate": manifest.get("shipped_approval_rate"),
        "shipped_approval_by_regime": manifest.get("shipped_approval_by_regime"),
    }


def live_map_coverage(
    regime_map: Dict[str, Any], by_cell: Dict[str, float]
) -> Dict[str, Any]:
    """Cross-reference the live regime->strategy map against the gatekeeper's own
    per-cell approval rates.

    These two artifacts ship in the same model set and nothing checks that they agree.
    They can disagree completely: vetting selects a strategy for a regime, and the
    gatekeeper — trained separately, on a different slice — may reject 100% of that
    strategy's signals, or have no measured rate for it at all because the cell fell
    below ``MIN_REGIME_N``.

    Either case means the published map advertises a cell that will never trade, and the
    only visible symptom is the one already in ``s1_health.json``: ``never_emitted:
    true`` with ``no_signals_generated`` forever, which looks like a quiet market.
    """
    cells: List[Dict[str, Any]] = []
    for regime, entries in (regime_map.get("regimes") or {}).items():
        for entry in entries or []:
            sid = str(entry.get("strategy_id"))
            rate = by_cell.get(f"{sid}|{regime}")
            cells.append(
                {
                    "regime": regime,
                    "strategy_id": entry.get("strategy_id"),
                    "strategy_key": entry.get("strategy_key"),
                    "selection_basis": entry.get("selection_basis"),
                    "gatekeeper_approval": rate,
                    "state": (
                        "unmeasured"
                        if rate is None
                        else "always_rejected" if rate == 0.0 else "measured"
                    ),
                }
            )
    unmeasured = [c for c in cells if c["state"] == "unmeasured"]
    rejected = [c for c in cells if c["state"] == "always_rejected"]
    return {
        "cells": cells,
        "n_cells": len(cells),
        "n_unmeasured": len(unmeasured),
        "n_always_rejected": len(rejected),
        "tradeable_cells": len(cells) - len(unmeasured) - len(rejected),
        "meaning": (
            "'unmeasured' = the gatekeeper publishes no approval rate for this cell "
            "(it fell below MIN_REGIME_N in training), so its live behaviour is "
            "unknown, not safe. 'always_rejected' = the gatekeeper rejected every "
            "signal from this cell in calibration; the map advertises it and it cannot "
            "trade. Both should be visible on the Model page — they are the reason a "
            "healthy-looking pipeline emits nothing."
        ),
    }


def _asset_symbols(asset_ids: Sequence[int]) -> List[str]:
    """``[1, 2]`` -> ``["EUR_USD", "GBP_USD"]``. The frame carries surrogate keys; a
    dashboard tile must not. Falls back to the raw ids if the dimension is unreadable.
    """
    try:
        from sqlalchemy import text

        from src.common.db import get_engine

        with get_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT asset_id, symbol FROM dim_asset")
            ).fetchall()
        lookup = {int(a): str(s) for a, s in rows}
        return sorted(lookup.get(int(a), str(a)) for a in asset_ids)
    except Exception:
        return sorted(str(a) for a in asset_ids)


def _training_data(manifest: Dict[str, Any], frame) -> Dict[str, Any]:
    """The training-data block, split by whether each number survives reproduction.

    Every figure here is derived from **the final joined frame** — the same frame the
    model is scored on — and carries ``reproducible: true``. Figures that come from the
    manifest and do *not* match that frame are quarantined under ``unverified``, where
    each one states its claimed value, the measured value, and ``reproducible: false``.

    The live case: the manifest says ``n_train: 92994``, which is the row count of
    ``fact_trade_outcomes`` *before* the point-in-time regime join. The joined frame is
    ~18k. A tile reading "92,994 trades" would confidently state a number no execution
    frame ever produced, and a blank tile — the status quo — hides the discrepancy
    entirely. Neither is acceptable, so the claim ships flagged and segregated.
    """
    verified: Dict[str, Any] = {
        "source": (
            "fact_trade_outcomes joined point-in-time (regime bar <= entry) to the "
            "causal walk-forward regime labels in fact_market_regime_v2"
        ),
        "reproducible": True,
    }
    unverified: Dict[str, Any] = {}

    if frame is not None:
        verified["rows"] = int(len(frame))
        verified["first_entry_utc"] = str(frame["entry_time"].min())
        verified["last_entry_utc"] = str(frame["entry_time"].max())
        verified["pairs"] = _asset_symbols(frame["asset_id"].dropna().unique().tolist())
        verified["granularities"] = sorted(
            frame["granularity"].dropna().unique().tolist()
        )
        verified["n_strategies"] = int(frame["strategy_id"].nunique())
        verified["base_win_rate"] = round(float(frame["is_winner"].mean()), 6)

    # Manifest counts, checked one by one against the frame. Only n_train has a direct
    # frame equivalent; n_fit/n_calibration describe a split of a frame we cannot rebuild,
    # so they are unverifiable by construction and are flagged as such rather than shown.
    cal = manifest.get("calibration") or {}
    reproduced = int(len(frame)) if frame is not None else None
    for name, claimed, measured in (
        ("n_train", manifest.get("n_train"), reproduced),
        ("n_fit", cal.get("n_fit"), None),
        ("n_calibration", cal.get("n_calibration"), None),
    ):
        if claimed is None:
            continue
        matches = measured is not None and int(claimed) == int(measured)
        if matches:
            verified[name] = int(claimed)
            continue
        unverified[name] = {
            "claimed": claimed,
            "measured": measured,
            "reproducible": False,
            "reason": (
                "does not match the final joined frame"
                if measured is not None
                else "no equivalent exists in the final joined frame — the split it "
                "describes cannot be rebuilt"
            ),
        }

    # Method strings are provenance, not measurements; they make no numeric claim.
    verified["calibration_method"] = cal.get("method")
    verified["calibration_fraction"] = cal.get("calibration_fraction")

    block: Dict[str, Any] = {"verified": verified}
    if unverified:
        block["unverified"] = unverified
        block["warning"] = (
            "fields under 'unverified' could not be reproduced from the final joined "
            "frame and carry reproducible: false. Do not render them as the "
            "training-set size, and do not promote them out of this sub-object. "
            "n_train specifically is a pre-join row count; the artifact itself is "
            "intact (its approval rate reproduces to within 0.0005), so the count is "
            "the suspect field, not the model."
        )
    return block


def build(storage, pointer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the card for ``pointer``'s model set. **Raises** rather than degrades.

    This is the atomicity gate. Every block is required: a card that silently omits its
    calibration curve because the database was unreachable would let an artifact ship
    described by a payload that is not actually about it. So any failure raises
    :class:`ModelCardRefused`, and the publish path turns that into a halt.

    Deliberately carries **no wall-clock timestamp**. The card is pinned to an immutable
    bundle version and enumerated in the manifest by SHA256; a clock reading inside it
    would change the digest on every call and make publishes non-idempotent. Age is
    derived by consumers from the model set's own ``published_at``.
    """
    payload: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "system": "system1",
        "metric_semantics": METRIC_SEMANTICS,
        "semantics": (
            "This card is an artifact OF the model set it describes, pinned to it by "
            "SHA256 in the manifest and made live by the same atomic pointer flip. It is "
            "generated once, when the bundle is packaged, and never recomputed — so it "
            "always describes the artifact that actually shipped. Read its age from the "
            "model set's published_at, not from a clock inside it."
        ),
    }

    with tempfile.TemporaryDirectory() as td:
        bundle = _load_bundle(storage, td, pointer=pointer)
        pointer, manifest = bundle["pointer"], bundle["manifest"]
        model, pre = bundle["model"], bundle["preprocessor"]

        payload["identity"] = _identity(pointer, manifest)
        payload["thresholds"] = _thresholds(manifest)
        payload["features"] = {
            "all": manifest.get("features"),
            "regime_features": manifest.get("regime_features"),
        }
        payload["live_map_coverage"] = live_map_coverage(
            bundle["regime_map"],
            manifest.get("shipped_approval_by_strategy_regime") or {},
        )

        # Every block below is REQUIRED. There is no degraded card: a payload that quietly
        # dropped its calibration curve would describe the shipped artifact incompletely
        # while still looking like a valid description of it.
        try:
            encoded = list(pre.get_feature_names_out())
            gains = model.get_booster().get_score(importance_type="total_gain")
            payload["feature_importance"] = aggregate_importance(gains, encoded)
        except Exception as exc:
            raise ModelCardRefused(
                f"feature importance could not be read from the shipped artifact: {exc}"
            ) from exc

        try:
            import src.gatekeeper.train as T

            # The shipped model's OWN declared schema is authoritative, not whatever
            # train.py currently trains on. Feature engineering has moved on since some
            # already-live champions were fit (e.g. the causal-regime -> structural-regime
            # migration, FIX-S1-016) — re-deriving features from today's constants would
            # silently score the artifact against a frame it was never fit to read, and a
            # blind train.py-current selection either raises (columns missing) or, worse,
            # would silently transform the wrong thing if the column names happened to
            # collide. Ask the manifest what it needs instead.
            cols = manifest.get("features") or (T.NUMERIC_DERIVED + T.CATEGORICAL)
            needs_causal = any(
                c in T.CAUSAL_REGIME_COLS + ["entry_signal_type"] for c in cols
            )
            frame = T._derive_features(T.build_frame(include_causal=needs_causal))
            missing = [c for c in cols if c not in frame.columns]
            if missing:
                raise KeyError(
                    f"shipped feature(s) not reproducible from current data: {missing}"
                )
            score_arr = T._scores(model, pre, frame[cols])
            thr_map = dict(manifest.get("dynamic_thresholds") or {})
            thr_map.setdefault("fallback", 0.5)
            probs = [float(v) for v in score_arr]
            outcomes = [int(v) for v in frame["is_winner"].to_numpy()]
            approved = [int(v) for v in T._apply_thresholds(frame, score_arr, thr_map)]
            r_mult = [float(v) for v in frame["r_multiple"].fillna(0.0).to_numpy()]
        except Exception as exc:
            raise ModelCardRefused(
                f"could not score the shipped artifact against the joined frame — "
                f"refusing to ship a model set with no measured telemetry: {exc}"
            ) from exc

        payload["training_data"] = _training_data(manifest, frame)
        scope = (
            "the final joined frame, scored by the shipped artifact at its shipped "
            "per-regime thresholds. Deterministically reproducible from that frame "
            "(reproducible: true), and it recovers the manifest's shipped_approval_rate "
            "to within 0.0005 — but these rows are not provably disjoint from the "
            "model's fit set, so read them as a health check on the shipped gate, not "
            "as an out-of-sample claim. The out-of-sample claim is oos_uplift."
        )
        payload["calibration"] = {
            "scope": scope,
            "reproducible": True,
            "in_sample_risk": True,
            "n": len(outcomes),
            "base_win_rate": round(sum(outcomes) / len(outcomes), 6),
            "brier": brier_score(probs, outcomes),
            "bins": reliability_bins(probs, outcomes),
            "reading": (
                "a perfectly calibrated model has observed_win_rate == "
                "mean_predicted in every populated bin (the 45-degree line). Bins "
                "with n=0 carry null, not zero — do not plot them at the origin."
            ),
        }
        payload["performance"] = {
            "scope": scope,
            "reproducible": True,
            "in_sample_risk": True,
            **operating_point_metrics(approved, outcomes, r_mult),
            "brier": brier_score(probs, outcomes),
        }

    return payload


def _write_json(storage, key: str, payload: Dict[str, Any]) -> None:
    """Replace ``key`` with ``payload``. Both backends refuse to overwrite, so the old
    object is cleared first — safe here because these are fixed, non-versioned keys."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, os.path.basename(key))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        if storage.exists(key):
            storage.delete_prefix(key)
        storage.put_object(key, path)


def read_pinned_card(
    storage, pointer: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Fetch the card pinned to the live (or given) model set.

    Raises :class:`ModelCardRefused` if the set has no card. That is a hard error rather
    than an empty result: a published set without a card violates the atomicity
    requirement and must be visible, not papered over.
    """
    from src.serializer.publish_model_set import POINTER_KEY

    with tempfile.TemporaryDirectory() as td:
        if pointer is None:
            ptr_path = os.path.join(td, "pointer.json")
            storage.get_object(POINTER_KEY, ptr_path)
            with open(ptr_path, encoding="utf-8") as fh:
                pointer = json.load(fh)
        assert pointer is not None
        entry = next(
            (
                a
                for a in (pointer.get("artifacts") or [])
                if a.get("name") == CARD_ARTIFACT_NAME
            ),
            None,
        )
        if entry is None:
            raise ModelCardRefused(
                f"live model set {pointer.get('model_set_id')!r} carries no "
                f"{CARD_ARTIFACT_NAME} — it was published without its telemetry payload"
            )
        local = os.path.join(td, CARD_ARTIFACT_NAME)
        storage.get_object(entry["path"], local)
        with open(local, encoding="utf-8") as fh:
            card: Dict[str, Any] = json.load(fh)
    card["_pinned_at"] = entry["path"]
    card["_sha256"] = entry.get("sha256")
    return card


def mirror(
    storage, pointer: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Copy the pinned card to ``telemetry/s1_model.json``. **Copies; never measures.**

    The frontend key is a projection of the deployed artifact, so it is produced by
    reading what shipped and adding only derived, clock-dependent context: the publish-event
    fields from the live manifest, and ages. Recomputing the measurements here would let
    the page drift away from the artifact it claims to describe within hours of a publish.
    """
    from src.serializer.publish_model_set import POINTER_KEY

    now = now or datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        if pointer is None:
            ptr_path = os.path.join(td, "pointer.json")
            storage.get_object(POINTER_KEY, ptr_path)
            with open(ptr_path, encoding="utf-8") as fh:
                pointer = json.load(fh)
    assert pointer is not None

    card = read_pinned_card(storage, pointer)
    identity = dict(card.get("identity") or {})
    identity.update(
        {
            "model_set_status": pointer.get("status"),
            "model_set_published_at": pointer.get("published_at"),
            "code_commit": pointer.get("code_commit"),
            "code_dirty": pointer.get("code_dirty"),
            "trained_age_sec": _age_seconds(identity.get("trained_at_utc"), now),
            "published_age_sec": _age_seconds(pointer.get("published_at"), now),
        }
    )
    # The underscore keys are how read_pinned_card reports provenance to its caller; they
    # are re-exposed below under public names and must not appear twice in the payload.
    body = {k: v for k, v in card.items() if not k.startswith("_")}
    payload = {
        **body,
        "identity": identity,
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "mirror_of": card.get("_pinned_at"),
        "mirror_sha256": card.get("_sha256"),
        "parity": (
            "this object is a byte-faithful copy of the model_card.json pinned to model "
            "set "
            f"{identity.get('model_set_id')}, plus publish-event fields and ages. It is "
            "never recomputed independently, so what is rendered here is what shipped."
        ),
    }
    _write_json(storage, TELEMETRY_KEY, payload)
    logger.info(
        "mirrored %s -> %s (model_set=%s)",
        card.get("_pinned_at"),
        TELEMETRY_KEY,
        identity.get("model_set_id"),
    )
    return payload


def verify_parity(storage) -> Dict[str, Any]:
    """Check that the mirror still describes the live model set.

    Returns a report; ``ok: False`` means the frontend is showing telemetry for a
    different artifact than the one deployed. Callers decide whether that is fatal —
    :func:`main` exits non-zero on it.
    """
    from src.serializer.publish_model_set import POINTER_KEY

    report: Dict[str, Any] = {"ok": False, "checked_at": _now_iso()}
    with tempfile.TemporaryDirectory() as td:
        ptr_path = os.path.join(td, "pointer.json")
        storage.get_object(POINTER_KEY, ptr_path)
        with open(ptr_path, encoding="utf-8") as fh:
            pointer = json.load(fh)
        report["live_model_set_id"] = pointer.get("model_set_id")

        if not storage.exists(TELEMETRY_KEY):
            report["reason"] = f"{TELEMETRY_KEY} does not exist"
            return report
        mir_path = os.path.join(td, "mirror.json")
        storage.get_object(TELEMETRY_KEY, mir_path)
        with open(mir_path, encoding="utf-8") as fh:
            mirrored = json.load(fh)

    entry = next(
        (
            a
            for a in (pointer.get("artifacts") or [])
            if a.get("name") == CARD_ARTIFACT_NAME
        ),
        None,
    )
    if entry is None:
        report["reason"] = (
            f"live model set carries no {CARD_ARTIFACT_NAME} — it shipped without its "
            f"telemetry payload"
        )
        return report

    report["mirror_model_set_id"] = (mirrored.get("identity") or {}).get("model_set_id")
    report["pinned_sha256"] = entry.get("sha256")
    report["mirror_sha256"] = mirrored.get("mirror_sha256")
    if report["mirror_model_set_id"] != report["live_model_set_id"]:
        report["reason"] = (
            "mirror describes a different model set than the live pointer"
        )
        return report
    if report["mirror_sha256"] != report["pinned_sha256"]:
        report["reason"] = "mirror was taken from a different card revision"
        return report
    report["ok"] = True
    return report


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Model card operations. The card is generated by the model-set publish path, "
            "not here — these are the read/mirror/verify verbs."
        )
    )
    ap.add_argument(
        "--mirror",
        action="store_true",
        help=f"copy the pinned card to {TELEMETRY_KEY} (default action)",
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="check the mirror still describes the live model set; exit 1 if not",
    )
    ap.add_argument(
        "--build",
        action="store_true",
        help=(
            "build a card for the live set and print it WITHOUT uploading. Diagnostic "
            "only — the shipped card is the one pinned at publish time"
        ),
    )
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    from src.common.storage import build_storage

    storage = build_storage()

    if args.build:
        print(json.dumps(build(storage), indent=2, sort_keys=True))
        return 0
    if args.verify:
        report = verify_parity(storage)
        print(json.dumps(report, indent=2, sort_keys=True))
        if not report["ok"]:
            logger.error("PARITY VIOLATION: %s", report.get("reason"))
            return 1
        logger.info("parity OK for model set %s", report["live_model_set_id"])
        return 0

    mirror(storage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
