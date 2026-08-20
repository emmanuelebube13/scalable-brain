Step 0 — record the baseline

So you can prove the run did something:

cd /home/emmanuel/Documents/Scalable_Brain/scalable-brain
source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate
psql -h localhost -p 5432 -U sa -d ForexBrainDB -c \
"SELECT granularity, count(*) n, max(\"timestamp\") latest FROM fact_market_regime_v2 GROUP BY 1 ORDER BY 1;"

Current: D1 29,408 · H4 165,118 · H1 650,815, all latest ~2026-07-24.

Step 1 — back up what gets overwritten

cp models/hmm_model.joblib models/hmm_model.joblib.bak-$(date +%Y%m%d)

Optional but cheap — snapshot the table too, since a refit rewrites historical labels, not just appends new ones:

psql -h localhost -p 5432 -U sa -d ForexBrainDB -c \
"CREATE TABLE fact_market_regime_v2_bak_20260811 AS SELECT * FROM fact_market_regime_v2;"

Step 2 — D1 first

Smallest set, fails fast if anything's wrong:

python -m src.regime.hmm_regime --granularity D1 --no-mlflow

--no-mlflow keeps it from writing experiment tracking you don't need for a catch-up run.

Step 3 — read the output before continuing

Watch for two things:

- Regime accuracy vs the 0.70 gate. ACCURACY_GATE = 0.70. Below it, the engine drops to a 4-cluster K-Means fallback.
- "K-Means fallback" on D1 is expected. D1 has historically fallen back. That's the gate working as designed — don't treat it as an error, and don't claim HMM for D1 afterwards.

Step 4 — the full run

python -m src.regime.hmm_regime --no-mlflow

H1 is 650k rows and takes several minutes. Let it finish.

Step 5 — verify

psql -h localhost -p 5432 -U sa -d ForexBrainDB -c \
"SELECT granularity, count(*) n, max(\"timestamp\") latest FROM fact_market_regime_v2 GROUP BY 1 ORDER BY 1;"

Expected — regimes should now track prices almost exactly:

┌─────┬─────────────┬────────────────┬──────────────────┐
│     │ rows before │ rows after (≈) │      latest      │
├─────┼─────────────┼────────────────┼──────────────────┤
│ D1  │ 29,408      │ ~29,598        │ 2026-08-09       │
├─────┼─────────────┼────────────────┼──────────────────┤
│ H4  │ 165,118     │ ~165,553       │ 2026-08-11 09:00 │
├─────┼─────────────┼────────────────┼──────────────────┤
│ H1  │ 650,815     │ ~652,150       │ 2026-08-11 13:00 │
└─────┴─────────────┴────────────────┴──────────────────┘

A small shortfall is normal — regime features need a warmup window, so the first bars of each series produce no label.

Step 6 — confirm the alarm clears

bash shell/cron_heartbeat_daily.sh
cat results/state/HEARTBEAT_ALERT 2>/dev/null || echo "ALL CLEAR"

CRITICAL regimes should disappear. Still expected to remain:
- CRITICAL outcomes — different writer, that's item 3
- CRITICAL cron_liveness — the deliberate hold, that's item 4

---
Run steps 0–3 and paste the D1 output. I mainly want to see the accuracy number and whether it fell back — that tells us something useful before committing to the H1 run.



RESULTS
2026-08-11 12:23:45,419 | INFO     | system1.regime.hmm | [H1] done: model=HMM acc=0.964 flick raw=0.0258→sm=0.0237
2026-08-11 12:23:45,456 | INFO     | system1.regime.hmm | Serialized HMM package → /home/emmanuel/Documents/Scalable_Brain/scalable-brain/models/hmm_model.joblib
2026-08-11 12:23:45,456 | INFO     | system1.regime.hmm | MODEL-003 complete: {'D1': 'HMM', 'H4': 'HMM', 'H1': 'HMM'}
{'model_version': 'hmm-v1.0.0', 'model_path': '/home/emmanuel/Documents/Scalable_Brain/scalable-brain/models/hmm_model.joblib'}
{'granularity': 'D1', 'rows': 29463, 'written': 29463, 'model': 'HMM', 'fallback_reason': None, 'converged': True, 'holdout_accuracy': 0.9389, 'flicker_raw': 0.00752, 'flicker_smoothed': 0.00722, 'label_distribution': {'Trending-Down': 22116, 'Trending-Up': 2836, 'Ranging': 2632, 'High-Vol': 1879}, 'mapping': {2: 'High-Vol', 3: 'Trending-Up', 0: 'Trending-Down', 1: 'Ranging'}}
{'granularity': 'H4', 'rows': 165468, 'written': 165468, 'model': 'HMM', 'fallback_reason': None, 'converged': True, 'holdout_accuracy': 0.7143, 'flicker_raw': 0.00909, 'flicker_smoothed': 0.00763, 'label_distribution': {'Trending-Down': 123464, 'Ranging': 15302, 'Trending-Up': 14256, 'High-Vol': 12446}, 'mapping': {3: 'High-Vol', 1: 'Trending-Up', 2: 'Trending-Down', 0: 'Ranging'}}
{'granularity': 'H1', 'rows': 652220, 'written': 652220, 'model': 'HMM', 'fallback_reason': None, 'converged': True, 'holdout_accuracy': 0.9644, 'flicker_raw': 0.02576, 'flicker_smoothed': 0.02366, 'label_distribution': {'Ranging': 283294, 'Trending-Down': 221849, 'Trending-Up': 97977, 'High-Vol': 49100}, 'mapping': {2: 'High-Vol', 1: 'Trending-Up', 3: 'Trending-Down', 0: 'Ranging'}}
(.venv) emmanuel@emmanuel-OptiPlex-3050:~/Documents/Scalable_Brain/scalable-brain$ 
psql -h localhost -p 5432 -U sa -d ForexBrainDB -c \
"SELECT granularity, count(*) n, max(\"timestamp\") latest FROM fact_market_regime_v2 GROUP BY 1 ORDER BY 1;"
Password for user sa: 
 granularity |   n    |         latest         
-------------+--------+------------------------
 D1          |  29463 | 2026-08-09 18:00:00-03
 H1          | 652220 | 2026-08-11 10:00:00-03
 H4          | 165468 | 2026-08-11 06:00:00-03
