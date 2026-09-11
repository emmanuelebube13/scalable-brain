# Gatekeeper feature basis and trade geometry

**2026-09-11 · branch `remediation/R2` · dry-run only, nothing promoted or published.**

Owner-directed, following WO-04B's *PARTIALLY FIXABLE (H1 only)* verdict. Three items, taken
together because the first two are one job:

1. The gatekeeper's feature basis and trade geometry — the model needs transferable payoff
   features, and the columns to hold them were NULL.
2. The `trending_strength` / `adx_value` duplicate.
3. The `signals_published_total` counter inconsistency.

---

## 1. The columns were NULL, in every row, since the table was created

```
select count(*), count(atr_sl_multiplier), count(atr_tp_multiplier) from fact_trade_outcomes;
 count |  sl   |  tp
-------+-------+------
 93738 |     0 |    0
```

Both writers passed a literal `None`, with a comment saying why:
`persist_trade_outcomes.py:319` — `None,  # atr_sl_multiplier (strategy SL not ATR-multiple here)`.
The comment is true — the strategies set absolute stop prices, not ATR multiples — but the
multiple is derivable from those prices, and nothing derived it. The columns were a place to
put the number, never a source of it.

That is why WO-04B's question had only one answer available. Its test — strip `strategy_id`,
change nothing else — left a feature basis of `atr_value`, `adx_value`, `regime_structural`
and two things derived from them. **There was nothing transferable in it to fall back on**,
so the honest finding was "no significant uplift at H4 or D1", and the honest conclusion from
*that* basis was "retire it above H1".

### What was built

`src/outcomes/geometry.py` — one module, pure arithmetic, no I/O.

**The rule for the ATR reference is "the most recent ATR available at entry under that
engine's fill model", and it resolves differently per engine** because the engines genuinely
differ:

| engine | reference | why |
|---|---|---|
| `backtest_engine_v1` | `ATR(i)` — entry bar | enters at `Close.iloc[i]`, so bar `i` is complete and its ATR is known |
| `position_engine_v2` | `ATR(i-1)` — prior bar | can fill *intrabar* on bar `i`; the engine itself resolves ATR-multiple legs against `atr_values[fill_bar - 1]` |

A single shared reference was tried first and rejected on measurement, not taste
(`Trend_EMA_ADX_H4` / EUR_USD, 201 trades):

| reference | mean | sd | reads as |
|---|---|---|---|
| `ATR(i)` entry bar | **1.5000** | **0.0000** | the declared 1.5×, exactly |
| `ATR(i-1)` prior bar | 1.4968 | 0.1079 | 1.5× plus 7% of noise |

That dispersion is entirely `ATR(i-1)/ATR(i)` — volatility acceleration folded into what is
supposed to be a geometry column. Two quantities in one feature is the conflation this repo
keeps paying for.

`position_engine.py` gained one column, `take_profit_price`: the fraction-weighted mean of the
declared take-profit legs, resolved against the fill. Only the engine can report it — a leg
may be declared as an ATR multiple or in pips, and resolving either needs the fill price and
the engine's own ATR. Weights are the **declared** fractions, not what filled, so the number
cannot depend on how the trade turned out.

### After the rebuild

`python -m src.outcomes.persist_all` — 75,209 trades, 48 of 67 strategies producing.

```
 rows  |  sl   |  tp   | pct_sl | pct_tp
-------+-------+-------+--------+--------
 93773 | 75209 | 65903 |   80.2 |   70.3
```

**100% of the rows this run produced carry `atr_sl_multiplier`.** The 19.8% that do not are
the 17,583 orphaned rows of O-4 — strategies 7/8/9, whose code no longer loads, so no rebuild
reproduces them. They keep their NULLs, which turns out to be useful (see §2).

`atr_tp_multiplier` is populated on 87.6% of produced rows. The remaining 12.4% **declare no
take-profit at all** — trailing-stop, time and opposite-signal exits. `weekly_day_reversal_ea`
is one: its only exit leg is `kind="time"`. NULL is the correct value there, and the
distinction is load-bearing (§2).

Verification that the arithmetic recovers what strategies declare:

| strategy | engine | mean sl | sd sl | mean tp |
|---|---|---|---|---|
| `Trend_EMA_ADX_H4` | v1 | **1.5000** | **0.0000** | **2.500** |
| `liquidity_grab_fade` | v2 | 2.2119 | 0.8232 | 0.399 |

The v1 row is the declared geometry recovered exactly. The v2 row is its own finding:
**`liquidity_grab_fade` (strategy 30) has a mean reward:risk of 0.23:1 across 1,018 trades.**
That is O-24 — "a 0.06:1 risk/reward signal reached the wire" — shown to be systematic rather
than a one-off, arrived at independently and from the other direction.

---

## 2. The gatekeeper, rebased

`FEATURE_SET_VERSION` 1.0.0 → **2.0.0** (major: a 1.0.0 model cannot be scored on this basis).

| | out | in |
|---|---|---|
| numeric | `trending_strength` | `atr_sl_multiplier`, `atr_tp_multiplier`, `risk_reward_ratio` |
| categorical | `strategy_id` | `entry_signal_type` |

`risk_reward_ratio = atr_tp_multiplier / atr_sl_multiplier` — scale-free twice over, so it is
comparable across pairs, volatility regimes and strategies. Which is precisely what
`strategy_id` one-hot was not.

**Missingness is carried, not filled.** `SimpleImputer(strategy="median", add_indicator=True)`
ahead of the scaler: "this strategy declared no target" is a real property of a trade, known
at entry, and imputing it silently would tell the model those trades had a median-sized
target. The indicator column lets the model split on the fact that the value is filler. The
median is fit per fold on the training split only. `StandardScaler` cannot accept NaN at all,
which is why this cannot be left to XGBoost's native missing handling — the scaler raises
first.

`atr_sl_multiplier` **is** required in `build_frame`'s dropna; `atr_tp_multiplier` is **not**.
Requiring both would have removed every trailing-stop and time-exit strategy wholesale — ~12%
of the table and not a random 12%. Requiring the stop has a useful side effect: it is how the
17,583 orphaned rows of O-4 leave the training frame, by a general rule rather than a special
case.

### What the model learns from now

Gain importance, fit on the full pre-holdout frame:

| feature | share |
|---|---|
| `risk_reward_ratio` | **46.06%** |
| `missingindicator_atr_tp_multiplier` | **14.51%** |
| `atr_sl_multiplier` | **12.14%** |
| `atr_tp_multiplier` | **5.89%** |
| **trade geometry, total** | **78.60%** |
| `regime_structural` (4 levels) | 7.72% |
| `adx_over_atr`, `atr_value`, `adx_value` | 8.70% |
| `entry_signal_type` (direction) | 2.57% |
| `volatility_regime` | 2.41% |

Against the number WO-04 was opened over: **`strategy_id` 96.78%, regime 0.21%, all nine
numerics 2.65% combined.** The regime feature now carries roughly 37× the share it did.

Note the missingness indicator at 14.5%: "did this strategy name a target at all" is the
second most informative thing the model sees. That signal did not exist in any previous basis.

### Comparison of feature bases

WO-04B's numbers came from a scratch script that no longer exists, so quoting them beside new
ones would compare two procedures as much as two feature sets. All four bases below were run
through **one identical procedure** — same folds, same fixed XGB config, same threshold
calibration, same 20,000-sample bootstrap — on the same 47,482-row frame, so the differences
are attributable to the features. (A fixed config rather than the real grid: 81 combinations ×
cv=3 × 5 folds × 4 bases is hours, and a per-basis hyperparameter search would itself be a
confound. The authoritative numbers for the chosen basis come from `train.run(dry_run=True)`
with the real grid — §2.4.)

| basis | AUC | uplift | p | sig | approval | degenerate |
|---|---|---|---|---|---|---|
| old (`strategy_id` + `trending_strength`) | 0.6334 | 0.0445 | 0.0009 | yes | 0.252 | 174/240 (72.5%) |
| WO-04B (`strategy_id` removed only) | 0.5269 | **−0.0181** | 0.9090 | **no** | 0.315 | 23/240 (9.6%) |
| **new (trade geometry, no `strategy_id`)** | **0.6399** | **0.0296** | **0.0208** | **yes** | 0.239 | 152/240 (63.3%) |
| geometry **+** `strategy_id` | 0.6413 | 0.0376 | 0.0050 | yes | 0.231 | 164/240 (68.3%) |

Three things to read from this:

**The premise was not false; the features were missing.** WO-04B's basis has *negative* uplift
under this procedure (−0.0181, p=0.91) — not a weak edge, no edge. The same folds with trade
geometry give 0.0296 at p=0.0208, and an AUC (0.6399) that **exceeds the old basis** (0.6334)
without using strategy identity at all. *Read §2.6 before relying on this — the mechanism
behind the AUC is mostly win-rate arithmetic, and the mean-R uplift it converts to is thinner
and fails in one of five folds.*

**The geometry carries what `strategy_id` was standing in for.** Adding `strategy_id` back on
top of the geometry moves AUC by 0.0014 (0.6399 → 0.6413). When identity was the only
per-strategy signal available it was worth 0.11 of AUC; now it is worth almost nothing,
because the thing it was a proxy for is measured directly. That is the definition of a
transferable feature, and it is the strongest evidence here.

**Per granularity, the WO-04B conclusion inverts:**

| | AUC | uplift | p | sig |
|---|---|---|---|---|
| H1 (31,457) | 0.6081 | 0.0013 | 0.4663 | no |
| **H4 (13,849)** | **0.6774** | **0.1405** | **0.00005** | **yes** |
| D1 (2,176) | 0.6081 | 0.0291 | 0.3505 | no |

WO-04B found H1 significant and H4 dead (p=0.4356) and recommended retiring the gatekeeper at
H4 and D1. On the rebuilt evidence it is **H4 that carries the edge**, strongly, and H1 that
does not. **Do not act on WO-04B's "retire above H1" recommendation** — it was correct for the
basis and data it had, and both have changed.

Two confounds are stacked in that reversal and neither is separated here: the feature basis
changed *and* the underlying table was rebuilt (orphan rows now excluded, strategy 58's pip
hotfix and the O-28 pip-scaling population both re-derived). **I have not isolated which drove
the inversion.** The pooled and per-basis comparisons above are internally valid because every
row ran on one frame; the comparison to WO-04B's published numbers is not.

### 2.4 The authoritative run

`python -m src.gatekeeper.train --dry-run --no-mlflow`, real grid, 47,482 trades:

```
OOS uplift=0.056210  p=0.000100  sig=True  approval=0.2375  n_approved=9397 n_rejected=30171
shipped-model calibration: fit=37985 cal=9497 approval=0.2244
  thresholds {'High-Vol': 0.8, 'Ranging': 0.5, 'Trending-Down': 0.5, 'Trending-Up': 0.5, 'fallback': 0.5}
per-regime approval (calibration tail):
  {'High-Vol': 0.1936, 'Ranging': 0.3522, 'Trending-Down': 0.2311, 'Trending-Up': 0.2125}
per-(strategy x regime) approval: 57 populated cells, 42 degenerate
GATEKEEPER REFUSED: 42 of 57 (73.7%) > 50% allowed
```

With the real hyperparameter grid the uplift is **0.0562 at p=0.0001** — stronger and far more
significant than the fixed-config comparison above (0.0296, p=0.0208), which is expected and
is why that sweep was only ever for comparing bases to each other.

Every other gate passes. Aggregate approval 0.2375 and shipped approval 0.2244 are both
mid-band. **All four regimes are inside the turnover band** (0.19–0.35) — no regime starved or
saturated, which is FIX-S1-010's check clearing cleanly.

### 2.5 The retrain is still blocked — and the reason has changed

`check_cell_degeneracy` refuses at **73.7%** (42 of 57 populated cells) against
`MAX_DEGENERATE_CELL_SHARE = 0.50`. No guard was touched, per the standing constraint. No
bundle was written — the refusal fires before `atomic_promote`, so `models/proposed_champion_*`
does not exist, which is the intended fail-closed behaviour.

But the guard's premise no longer holds, and this is the finding that needs an owner decision.
Its docstring reads:

> A gate whose approval is bimodal 0/1 across cells is not gating: it reproduces the strategy
> selection MODEL-005 already performed.

That inference was sound when `strategy_id` was the only per-strategy-constant feature
available — bimodal approval *had* to mean memorised identity. It no longer follows, because
**strategy geometry is near-constant by construction**:

```
strategies with R:R coefficient-of-variation < 0.10 :  13 of 23  (n>=100)
six of them have sd exactly 0.000
between-strategy sd of mean R:R                     :  0.898
median within-strategy sd of R:R                    :  0.061
```

A **15:1 between-to-within ratio**. Six strategies (v1 ids 1–6) have a fixed 1.5×ATR stop and
a fixed target multiple, so their R:R is one number with zero variance. A model keying on R:R
*must* score near-constant within those strategies — not because it learned which strategy it
is, but because it learned a real, transferable property that happens not to vary inside a
strategy.

**The refusal's own worst-offender list is the confirmation.** The three strategies it names
are exactly the three with the least geometric variation in the registry:

| cell | approval | n | strategy | R:R sd |
|---|---|---|---|---|
| `4\|Trending-Up` | 0.000 | 1113 | `Trend_Donchian_H1` (v1) | **0.000** |
| `4\|Trending-Down` | 0.000 | 1054 | `Trend_Donchian_H1` (v1) | **0.000** |
| `1\|Trending-Up` | 0.000 | 677 | `Trend_EMA_ADX_H1` (v1) | **0.000** |
| `1\|Trending-Down` | 0.003 | 633 | `Trend_EMA_ADX_H1` (v1) | **0.000** |
| `11\|Trending-Down` | 0.003 | 299 | `adx_trend_pullback_ea` (v2) | 0.073 |
| `11\|Trending-Up` | 0.003 | 288 | `adx_trend_pullback_ea` (v2) | 0.073 |

Not one of them is a strategy the model could identify; all of them are strategies whose
payoff geometry is a constant the model *can* read. The guard is measuring the right thing and
drawing the wrong conclusion from it.

So `check_cell_degeneracy` cannot currently distinguish:

- **the defect it was built for** — the model reproducing MODEL-005's selection from identity; and
- **the intended behaviour** — the model discriminating on a genuine payoff feature that is
  constant within a strategy by that strategy's own design.

The importance table is what separates them, and it says this model is doing the second: no
identity feature exists in the basis, and 78.6% of gain sits on geometry.

**This is an owner decision, not a code change, and it is not mine to make.** Three options,
stated without a recommendation being acted on:

1. Accept the guard as-is. The retrain stays blocked and the gatekeeper stays in shadow mode
   indefinitely. Safe, and costs nothing today since nothing is gated on the score.
2. Re-scope the guard to what it was actually defending — e.g. measure degeneracy *residual to
   the declared geometry*, so a cell only counts as degenerate when its approval is not
   explained by its R:R and stop width. That is a real piece of work and needs
   `measurement-reviewer`.
3. Raise the threshold. **Cheapest and worst** — it discards the guard's evidence rather than
   correcting its inference, and FIX-S1-012 exists because a permissive turnover band let
   exactly this class of defect ship.

`MAX_DEGENERATE_CELL_SHARE`, `min_turnover_floor` and the turnover band are untouched.

### 2.6 Adversarial pass — what the gate is actually doing, and why it qualifies §2.2

The obvious challenge to a result where one feature carries 46% of importance is that the
feature is arithmetic rather than insight. I tested it, and **the challenge is substantially
correct.**

R:R and win rate are mechanically related, because a wider target is harder to reach:

| `risk_reward_ratio` quintile | n | win rate | mean R |
|---|---|---|---|
| ≤ 1.245 | 8,331 | **0.6394** | **−0.1302** |
| 1.245 – 1.667 | 8,332 | 0.3398 | −0.0683 |
| 1.667 – 2.000 | 8,331 | 0.3311 | −0.0424 |
| = 2.000 | 10,668 | 0.3091 | −0.0910 |
| > 2.000 | 5,990 | **0.2733** | −0.1191 |
| *no target declared* | 5,830 | 0.3861 | −0.0302 |

Win rate falls from 64% to 27% across the range. **The training target is `is_winner`
(`r_multiple > 0`) — a win-rate target.** So a model handed R:R can score well on its own
objective by learning the geometry of stop placement, with no reference to market state at all.

And that is largely what it does. Approved vs rejected, per OOS fold:

| fold | approved R:R | rejected R:R | approved win | rejected win | **approved mean R** | **rejected mean R** |
|---|---|---|---|---|---|---|
| 1 | 1.153 | 1.948 | 0.513 | 0.339 | −0.0605 | −0.0783 |
| 2 | 1.188 | 2.024 | 0.492 | 0.310 | −0.0917 | −0.1501 |
| 3 | 0.425 | 1.924 | 0.714 | 0.349 | **−0.0671** | **−0.0584** |
| 4 | 0.597 | 1.966 | 0.667 | 0.320 | +0.0030 | −0.1064 |
| 5 | 0.511 | 1.979 | 0.700 | 0.323 | −0.0250 | −0.0849 |

The gate systematically approves low-R:R trades and rejects high-R:R ones. Its primary lever
is win rate via geometry.

**Two things stop this from voiding the result, and one thing does not:**

*It is not leakage.* Every input is known when the trade is entered. This is a real property
of the market, correctly learned.

*Low R:R alone does not produce the uplift.* The lowest R:R quintile has the **worst** mean R
of any quintile (−0.1302). A model that merely picked low-R:R trades would select the worst
bucket by the metric the gate is judged on. It nonetheless beats the rejected set in 4 of 5
folds, which means it is discriminating *within* the low-R:R population using regime, ADX and
ATR. The uplift is thin but it is not the tautology.

*But the mean-R effect is much weaker than the win-rate effect, and it is not uniform.*
**Fold 3 approved a WORSE mean R than it rejected** (−0.0671 vs −0.0584). One of five folds
going the wrong way is invisible in the pooled figure (0.0562, p=0.0001), and the pooled figure
is what the promotion gate reads.

**The finding this argues for — stated as evidence, not acted on.** WO-04B's constraint was
"do not replace one target redefinition with another… that is a Stage B finding to be argued
with evidence". This is that argument:

> `is_winner` is a **win-rate** target; `oos_uplift_ok` is a **mean-R** gate. They are not the
> same objective, and trade geometry is precisely the feature that separates them — it moves
> win rate and expected R in *opposite* directions. Optimising a win-rate target on a feature
> basis whose strongest signal is R:R geometry is training the model against a proxy that
> disagrees with the thing it is scored on.

Nothing was changed. The target is untouched and `models/proposed_champion_*` was never
written. Any redefinition needs `measurement-reviewer` and `devils-advocate` and is a separate
change set — but it should be considered before the degeneracy question in §2.5, because it
may change what the right answer to that question is.

### 2.7 One thing I did change: the refusal's wording

The refusal printed this, on 2026-09-11, about a model that has no `strategy_id` feature:

> The model is discriminating on strategy identity, not market state.

That sentence was a safe inference when `strategy_id` was the only per-strategy-constant thing
in the basis. It is now simply false, and it is the exact defect CLAUDE.md records under "when
a threshold appears in a message string, read it from the constant" — *a hardcoded "< 60mo" in
a rejection reason sent a downstream agent on a real investigation into a gate that was
working.* An asserted cause is worse than a stale threshold, because it tells the reader where
to look.

The message now reports the measurement, names both explanations, and points at the gain
importances as the way to tell them apart. **The check's threshold, inputs and verdict are
unchanged** — a run that refused before refuses now, identically.

---

## 3. The `trending_strength` duplicate

`_derive_features` contained:

```python
df["trending_strength"] = df["adx_value"]  # ADX is already trending strength
```

A byte-identical copy of a column already in `NUMERIC`, with a comment saying so. It cannot
add information; it splits one feature's importance across two names, so **every gain table
ever produced for this model understated ADX by roughly half** and showed a duplicate that
read as a distinct signal. Harmless to predictions, actively misleading to anyone reading why
the model does what it does — which was the entire subject of WO-04.

Removed from `NUMERIC_DERIVED`. **Still computed in `_derive_features`, deliberately.**

That distinction is the whole of the fix, and getting it wrong would have been a live
regression. `_derive_features` is shared by training and by `Scorer.score` on purpose, so the
two cannot drift. `Scorer` validates a signal against `preprocessor.feature_names_in_` read
off the **shipped artifact** — not the manifest and not `FEATURE_SET_VERSION`. The live
champion `gk-d614163c` was fit with `trending_strength`, so deleting the line would have made
every live signal refuse `MISSING_FEATURE:trending_strength` and go out unscored — which reads
downstream as a gatekeeper outage, not as a training-side cleanup.

Verified against the live bundle after the change:

```
expects: ['atr_value', 'adx_value', 'volatility_regime', 'trending_strength',
          'adx_over_atr', 'regime_structural', 'strategy_id']
score  : {'status': 'scored', 'score': 0.4285, 'threshold': 0.75, 'would_pass': False}
```

0.4285 sits inside the 0.42–0.46 band the live ledger records, and `test_feature_basis.py`
now reads the shipped preprocessor's own feature list and fails if `_derive_features` stops
producing any of it.

---

## 4. The `signals_published_total` counter

### What was wrong

`results/state/signal_emitter_state.json`, read at the start of this session:

```json
"last_signal_emitted_at": "2026-09-04T21:15:44.359181Z",
"signals_published_total": 0,
```

Those two statements cannot both be true. Between `05:15:57Z` and `14:07:04Z` on 2026-09-11
every cumulative total went to zero — published 63 → 0, scored 21 → 0, shadow_would_refuse
20 → 0, dlq_count_total 0 → null — while `last_signal_emitted_at` kept its value.

### No code path produces that state

- Every total is written as `prev.get(key, 0) + delta`; the dlq totals have an explicit
  `setdefault` carry-forward.
- The one path that discards `prev` — the unreadable-file self-heal — **also** blanks
  `last_signal_emitted_at` and logs an ERROR. No such line exists in any log.
- Replaying the pre-reset file through `record_emitter_state("risk_off")` leaves all five
  fields unchanged. Measured, not reasoned:

  ```
  signals_published_total            63 -> 63
  signals_scored_total               21 -> 21
  shadow_would_refuse_total          20 -> 20
  dlq_count_total                     0 -> 0
  last_signal_emitted_at    2026-09-04T21:15:44.359181Z -> unchanged
  ```
- Tests are isolated (`test_run_once_never_writes_the_live_emitter_state` exists for this),
  and no shell script writes the file.

**The totals were overwritten out of band** — a hand edit of a machine-written artifact. The
reason it went unnoticed is structural: an incrementally-maintained integer has no second copy
to disagree with.

### What was built

`src/signals/reconcile.py` gives it one. The ledger under `results/signals/` is one durable
NDJSON row per candidate, so the counters become **derivable** rather than only accumulated —
a lost total is repaired by running something, not by typing a number back in, which is the
same class of edit that caused the loss.

The ledger has an epoch and pretending otherwise would silently shrink the count: it began
2026-08-30 (commit `51ec34a`), when the counter already stood at 49. A pure ledger rebuild
would produce 14 and look authoritative. `LEDGER_EPOCH_BASELINE` carries the pre-ledger counts
explicitly, so the arithmetic is visible.

The reconstruction reproduced every destroyed value exactly, before any repair was applied:

```
counter                        actual    floor  baseline   ledger
signals_published_total             0       63        49       14
signals_scored_total                0       21         0       21
shadow_would_pass_total             0        1         0        1
shadow_would_refuse_total           0       20         0       20
```

63, 21, 1, 20 — the four numbers that were destroyed, derived independently from the ledger
plus a baseline read out of the commit that created it. Repaired via
`python -m src.signals.reconcile --repair`, not by editing the file.

Repair is **monotonic** — it raises a short counter and never lowers one. A counter above its
floor may be history the ledger cannot see: pruned days (O-19) and a publish whose ledger
append failed (O-21) both land there legitimately. Only the cumulative totals are touched;
`last_run_*`, `last_signal_emitted_at` and `consecutive_faults` are written back unchanged.

### And a consumer, so it cannot happen silently again

`heartbeat.check_emitter_counters`. A detector with no consumer is not a control — the R4.2
lesson, where the regime stall was reported correctly every morning for twelve days into a
file nothing read.

| condition | status | why |
|---|---|---|
| non-null `last_signal_emitted_at` beside a zero publish count | **CRITICAL** | cannot be true under any history — the file contradicts itself |
| a counter below its ledger floor | **WARN** | evidence of lost history, and repairable |
| a counter above its floor | not a finding | pruned days and failed appends land here legitimately |

```
[PASS] emitter_counters  63 published lifetime, reconciled against 21 ledger rows
```

**This closes the detection half of O-21**, which asked for exactly this reconciliation and
noted "neither is currently alarmed". The two divergences O-21 names (rows outliving counters
on a mid-run crash; a failed append still incrementing the tally) are now visible as
shortfall/surplus rather than invisible. It does not change the emission behaviour that causes
them — that remains open.

---

## Gates

**Applied by hand against the agent files in `.agents/agents/`, not as subagents.** Stated
explicitly because a gate silently skipped is worse than one openly done by hand.

| gate | verdict |
|---|---|
| `leakage-hunter` | **PASS.** Every geometry input is known at entry. v1's `ATR(i)` is causal because it fills at that bar's close; v2 uses `ATR(i-1)` because it can fill intrabar. `initial_stop_price`, never `final_stop_price` — v2 trails its stop, so the final one is a function of the outcome. `take_profit_price` weights by **declared** fractions, not realised fills. The imputer's median is fit on `tr` inside `_walk_forward` and on `fit_df` inside `run()` — never on the whole frame. Nothing reads `r_multiple`, `exit_reason`, `exit_price` or `holding_bars`. |
| `measurement-reviewer` | **PASS with a material qualification** — §2.6. The pooled uplift is real and significant, but its mechanism is mostly win-rate arithmetic and one of five folds inverts. The per-basis comparison is internally valid (one frame, one procedure); the comparison to WO-04B's published numbers is **not**, and is labelled as such. |
| `devils-advocate` | **The counter-case is in §2.6 and it landed.** The strongest feature is partly tautological and the training target disagrees with the promotion gate's metric. Recorded as evidence for a target discussion, not acted on. |
| `db-guardian` | **PASS.** No schema change — both columns already existed. Writes go through the existing parameterised `execute_values` upsert via `src/common/db.py`. The NaN→None conversion in `_assign_oos_columns` is there because psycopg2 sends NaN to `double precision` as the float NaN, not NULL, which would make "no target declared" indistinguishable from a corrupt value and report the column as fully populated. |
| `forex-strategist` | **PASS, with one finding surfaced rather than fixed:** `liquidity_grab_fade` at a mean 0.23:1 reward:risk over 1,018 trades. That is O-24 confirmed as systematic. Not touched — fixing or disqualifying strategy 30 takes live output to 0 qualified cells and is owner-gated. |
| `release-guard` | **N/A — nothing published.** Dry-run only; the refusal fires before `atomic_promote`, so no bundle exists. Both GCS pointers and the live map are untouched. |
| `structure-warden` | New files placed per `STRUCTURE.md`: `src/outcomes/geometry.py` beside its writer, `src/signals/reconcile.py` beside `ledger.py`, tests in each module's `tests/`, this report in `audit/reports/`. **Nothing new at the repo root.** Pre-existing root violations (`gk_train_log.txt`, `my_eval_output.txt`, `run_traceback.log`, `model001_ingest.log`, `model003_regime.log`, `backlog_run.log`) were left alone — they are committed and referenced, and moving them is its own change. |

## What I did NOT check

- **The degeneracy inversion is confounded.** Feature basis and underlying data changed in the
  same step. I did not run the new basis against the pre-rebuild table, so I cannot say how
  much of H4's reversal is the geometry and how much is the orphan exclusion and pip fixes.
- **No holdout was touched.** `HOLDOUT_CUT_DATE` excludes post-cut rows from training, as
  WO-04B Stage C established. No Stage-2 evaluation was run.
- **Nothing was promoted or published.** `--dry-run` only; the live map, the live model set and
  both GCS pointers are untouched. `MODEL_SET_AUTOPUBLISH` and `GATEKEEPER_AUTOPROMOTE` unset.
- **The O-4 orphan rows were not reconciled.** `--reconcile` is destructive and owner-gated. They
  remain in the table; they simply no longer reach the gatekeeper's frame.
- **A 2.0.0 champion is not scoreable live yet** (see below). I did not build that mapping —
  it changes the live emit path, which this change set deliberately does not touch.
- **I did not run the review agents as subagents.** The checks below were applied by hand
  against the agent files; stated explicitly because a gate silently skipped is worse than one
  openly done by hand.

## Prerequisite before any 2.0.0 bundle is promoted

`Scorer` validates against the shipped preprocessor's feature names, so a 2.0.0 champion would
demand `atr_sl_multiplier`, `atr_tp_multiplier` and `entry_signal_type` at inference and refuse
every live signal with `MISSING_FEATURE` until they are supplied.

The live signal already carries everything needed — `build.py:525-528` puts `atr`,
`proposed_entry`, `proposed_sl` and `proposed_tp` on every candidate, and the ledger records
them. What is missing is the mapping.

**One definitional trap in that mapping.** `build.py:500-509` computes `rr_ratio` as
*signed* reward/risk and returns `None` when the range is zero or inverted. Training computes
`risk_reward_ratio` from unsigned ATR magnitudes, which yields a positive number for an
inverted target. The two therefore disagree **exactly on the pathological trades** — the O-24
shape. The live mapping must adopt the training definition, or the model will see a feature it
was never fit on precisely where it matters most.

## Tests

```
python -m pytest src -q     ->  1071 passed, 1 skipped, 56s
```

New: `src/outcomes/tests/test_geometry.py` (18), `src/signals/tests/test_reconcile.py` (14),
`src/gatekeeper/tests/test_feature_basis.py` (13).

Three of those are guards on things that would otherwise fail silently:

- `test_the_reference_matches_the_position_engines_own_atr` — this module and the engine must
  compute one number. The R2 lesson, where three callers with three windows disagreed about
  the same bar.
- `test_derive_features_covers_every_feature_the_live_champion_asks_for` — reads the shipped
  preprocessor rather than a list in the test file, because the list is what drifts.
- `test_atr_tp_multiplier_is_not_required_but_atr_sl_multiplier_is` — putting the target back
  in the required set would silently delete a class of strategy from training.
