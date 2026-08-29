---
name: run-vetting
description: The procedure for running strategy vetting and selection — rebuilding outcomes, attribution, the gates, ranking, and the designate owner-override path. Use when qualifying strategies, regenerating the regime-strategy map, or investigating why a strategy did or did not qualify.
---

# Running vetting and selection

```bash
cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
```

## The chain

Vetting reads attribution, which reads trade outcomes. A stale link upstream produces a
confident wrong answer downstream — trade outcomes have gone stale silently for months
before, because their only writer stopped running and nothing alerted.

```bash
python -m src.outcomes.persist_all       # → fact_trade_outcomes (one writer, check it ran)
python -m src.attribution.attribute      # MODEL-004 → fact_strategy_regime_attribution
python -m src.vetting.vet                # dry: → results/reports/proposed_*
python -m src.vetting.rank_all           # the selection report; changes nothing
python -m src.vetting.vet --live         # writes regime_strategy_map.json + strategy_weights.json
```

**Run the dry form first and read it.** `vet` without `--live` writes `proposed_*` reports
and touches nothing live.

## The gates

`src/vetting/gates.py`, applied to **OOS trades only**:

| Gate | Bar |
|---|---|
| Profit factor | ≥ 1.5 |
| Sharpe | ≥ 0.8 |
| Max drawdown | ≤ 25% |
| Win rate | ≥ 40% |
| Recovery factor | ≥ 3.0 |
| OOS months | ≥ 12 |

Two things to hold onto:

- **The OOS gate was lowered from 60 to 12 months by owner decision on 2026-08-21.** That was
  deliberate. Tests still asserting 60 are stale — fix the tests to the current thresholds
  rather than reverting the behaviour.
- **There is no minimum-trade-count gate.** `trade_count` is only a ranking tie-break. A cell
  can pass everything on a small sample, so check `n` yourself and say what it is.

## Integrity is not a gate

`INTEGRITY_DISQUALIFIED` is checked **before** the performance gates, in a separate
`integrity_fail` category. The distinction is deliberate:

> A gate failure means "could pass later by improving." An integrity failure cannot.

`Range_Stochastic_Divergence` (strategy 10) reads the future via `rolling(center=True)` and
emits **zero** signals causally. Its attribution rows still show PF 1.92 because they derive
from the look-ahead backtest — so regenerating the map without the integrity bar would
**re-qualify it**. Never remove that bar to "see what happens".

## The designate override

```bash
python -m src.vetting.designate --strategy KEY --reason "…" --by owner [--dry-run]
```

This puts a **gate-failing** strategy into the map with a written reason. It refuses
`INTEGRITY_DISQUALIFIED` ids. `selection_basis: "designated"` is carried all the way into the
signal message and must be disclosed in any communication describing the live model set.

Known latent defect: `vet.py` can publish qualified strategies with **empty exits** — check
that exits are populated before believing a new qualifier.

## Reading the result

`results/state/regime_strategy_map.json` — read the file, do not cite a remembered cell
count. Designated cells carry `designated_reason`, `ci_mean_r`, `pairs_passed_fraction` and
`tail_dependence`.

Before believing any new qualifier, run the adversarial pass:

- `measurement-reviewer` — sample size, per-pair decomposition, metric definitions.
- `devils-advocate` — is this a pair effect, a duplicate cell, or a search artifact?
- `leakage-hunter` — if the strategy is new or was recently modified.

## Standing findings that constrain interpretation

- **Regimes do not discriminate.** `discrimination` reports `n_discriminating: 0 of 10`; max
  win-rate spread among clean strategies is 0.0567 against a 0.10 bar. Re-tested against
  honest labels (kappa 0.83+); it stands. Do not present a regime cell as evidence that
  regimes work.
- **The Trending-Up H4 cell is 100% USD_JPY** — concentration, not breadth.
- **The D1 HMM falls back to K-Means** by design. Do not claim HMM at D1.
- The live routing label is **CSRM structural** (`src/regime/structural.py`), not
  `regime_causal`, which is NULL on the newest rows.

## Known-broken

`python -m src.analytics.publish_regime` fails — it imports `src.regime_aware.families`,
removed with the failed R3 experiment (FIX-S1-016). The label math now lives in
`src/regime/structural.py`.

## Tests

```bash
python -m pytest src/vetting -v
```

Known-red as of 2026-08-23: `vetting/tests/test_gates.py` and friends still assert the old
60-month OOS gate. Pre-existing, not yours — but fixing them to the current thresholds is a
welcome change.
