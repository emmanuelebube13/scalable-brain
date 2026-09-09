# Scalable-Brain — Fix Register

Every defect found in the audit, with the reasoning for why it is a defect, a verification
step, and an action gated behind that verification.

**Working rule for the agent:** verify first, act only if verification confirms. If
verification comes back clean, mark the item `NOT A PROBLEM` and move on — that is a valid
and useful outcome. Do not fix something because this document predicts it.

Each entry has the same five parts:

- **WHY** — the reasoning. Why this is a defect rather than a design choice.
- **VERIFY** — the check, with what a confirming result looks like and what a clearing result
  looks like.
- **ACT** — the change. Only on confirmation.
- **CONFIRM** — how you prove the fix worked.
- **ROLLBACK** — how to undo it.

Severity: **P0** halt-worthy · **P1** blocks trustworthy results · **P2** correctness risk ·
**P3** hygiene.

Order of work is in §8. Do not follow the numbering order.

---

# 1. Gatekeeper

The Gatekeeper computes a score and never compares it to anything. This section makes it a
gate. Read §1.5 before wiring anything — sequencing matters here.

## G1 — The calibrated threshold is never read `[P0]`

**WHY.** `Scorer.__init__` sets `self.manifest_path` and `_load()` never opens it. The
champion's per-regime cutoffs (0.60–0.80) live in that file. `score()` returns
`predict_proba[0,1]` and nothing downstream compares it to anything: `run.py:415` stamps
`threshold_applied = 0.5`, which is below every calibrated value, and publishes.

An ML gate that never rejects is not a conservative gate — it is not a gate. The system
currently has one filter on live trades (the regime map), and that map is selected on a label
it isn't executed against. Wiring the threshold restores a layer that everyone downstream
believes already exists. That belief is itself a hazard: System 3 sizes positions assuming a
model vetted the signal.

**VERIFY.**
1. `grep -rn "manifest_path" src/gatekeeper/` — confirm it is assigned and never opened.
2. `grep -rn "threshold" src/gatekeeper/ src/signals/ src/queue_producer/` — confirm no
   comparison of `model_score` against any threshold anywhere on the live path.
3. Read `models/champion_manifest.json` and report the per-regime thresholds it contains.
4. From `results/state/signal_emitter_state.json`, report `shadow_would_pass_total`,
   `shadow_would_refuse_total`, and the implied refusal rate.

*Confirms if:* no threshold comparison exists and the manifest holds real cutoffs.
*Clears if:* a comparison exists somewhere and `threshold_applied = 0.5` is dead code.

**ACT.** Do not wire this yet — see §1.5. In this pass, only:
- Load the manifest in `_load()` and expose `self.thresholds`.
- Return the applicable threshold alongside the score: `{"status": "scored", "score": p,
  "threshold": t, "would_pass": p >= t}`.
- Have `run.py` stamp the **real** threshold in `threshold_applied` and keep publishing
  regardless, with the shadow verdict recorded per signal.

This makes the gap measurable per-signal instead of only in aggregate, and changes nothing
that reaches the wire.

**CONFIRM.** One hour of ledger rows carry a non-0.5 `threshold_applied`, a `would_pass` flag,
and an unchanged published count.

**ROLLBACK.** Revert; the scoring path is unchanged in behaviour.

## G2 — `known_strategies` fails open and silently `[P0]`

**WHY.** `Scorer._load()` populates `known_strategies` only if a preprocessor transformer is
literally named `"cat"`. If that name ever changes, the set is empty, every membership test
fails, and every signal refuses with `UNKNOWN_STRATEGY_ID` — which `run.py:468-470` emits as
**unscored and publishes anyway**.

So total Gatekeeper failure is indistinguishable at the wire from normal operation. The only
evidence it isn't currently happening is a one-off measurement from 2026-08-30 recorded in a
comment. Nothing re-checks it. This is the same failure shape as FIX-S1-016 — healthy process,
absent outcome — one layer up.

**VERIFY.**
1. Load the champion preprocessor and print `[name for name, _, _ in
   preprocessor.transformers_]`. Confirm whether `"cat"` is present.
2. Print `len(Scorer(MODELS_DIR).known_strategies)`.
3. From the last 7 days of ledger rows, report the count by `gate1_outcome` and by
   `refusal_reason`.

*Confirms if:* `known_strategies` is empty, or `UNKNOWN_STRATEGY_ID` appears at a material rate.
*Clears if:* the set is populated and refusals are rare.

**ACT.** Regardless of the verify result (this is a robustness fix, not a bug fix):
- Raise at load time if `known_strategies` is empty while a model is present. An empty set is
  never correct when a trained preprocessor exists.
- Resolve the strategy column by inspecting `feature_names_in_` across all transformers rather
  than matching a transformer name.
- Emit a startup log line with the count.
- Update the stale comment listing `regime_causal` in the example columns — that is the
  previous champion.

**CONFIRM.** Rename a transformer in a copy of the preprocessor and confirm the loader raises
rather than silently returning an empty set.

**ROLLBACK.** Revert.

## G3 — Every refusal path publishes `[P1]`

**WHY.** `NO_CHAMPION_MODEL`, `UNKNOWN_STRATEGY_ID`, `MISSING_FEATURE:*` and `INFERENCE_ERROR`
all emit unscored and publish. Only `NAN_FEATURE` drops.

The reasoning documented in `run.py` is sound for `MISSING_FEATURE` — the Gatekeeper declining
to have an opinion is not a verdict on the signal, and System 3's contract represents
"unscored" as a first-class state. But `NO_CHAMPION_MODEL` is different: it means no vetted
model exists at all. Publishing under that condition is not "no opinion," it is "no oversight,"
and it should be a deliberate, configured choice rather than a default.

**VERIFY.** From 30 days of ledger rows: the count and rate of each refusal reason, and how
many of those were published. Report what fraction of published signals were unscored.

*Confirms if:* a material share of published signals are unscored.
*Clears if:* unscored publishes are rare.

**ACT.** Add a config flag `PUBLISH_UNSCORED` with per-reason granularity. Default:
`NO_CHAMPION_MODEL` → drop. `UNKNOWN_STRATEGY_ID`, `MISSING_FEATURE`, `INFERENCE_ERROR` →
publish unscored (current behaviour, now explicit). Alert on any sustained rise.

**CONFIRM.** Ledger shows the new drop reason firing when the champion is absent.

**ROLLBACK.** Set the flag to publish-all.

## G4 — Shadow counters are computed and never used `[P2]`

**WHY.** `shadow_would_pass` / `would_refuse` measure exactly what the gate would decide.
Nothing reads them. This is the same pattern as the shrunk columns, the `settled` flag and
`evidence_age_days` — the measurement exists, nothing acts.

**VERIFY.** Report the totals from the emitter state file, the implied refusal rate, and the
same broken down by regime from `last_run_by_regime`.

**ACT.** Publish the shadow refusal rate to monitoring. Alert if it moves more than 20 points
week-over-week — that indicates either model drift or a feature-pipeline change.

**CONFIRM.** The metric appears in the dashboard with a plausible value.

## G5 — Is the score calibrated? `[P2]`

**WHY.** `predict_proba` from a gradient-boosted model is not a calibrated probability unless
it was explicitly calibrated. If the 0.60–0.80 thresholds were chosen on validation-set
probabilities from a differently-distributed population, they will not mean the same thing
live. Wiring an uncalibrated threshold is worse than wiring none, because it produces
confident-looking filtering with no defined false-positive rate.

**VERIFY.** Read `models/champion_manifest.json` and the training code: was a calibration step
(`CalibratedClassifierCV` or equivalent) applied? Produce a reliability curve of predicted
probability against realised win rate on the validation set. Then compare the live score
distribution over the last 30 days against the validation distribution (PSI or KS).

*Confirms a problem if:* no calibration was applied, or live and validation score
distributions differ materially.

**ACT.** If uncalibrated: calibrate on a held-out set and re-derive thresholds before §1.5.
If distributions have drifted: retrain before wiring.

**CONFIRM.** Reliability curve is near-diagonal; PSI below 0.2 per feature.

## §1.5 — Sequencing for turning the gate on

**Do not enable the threshold until L1 (label unification) is complete.**

The Gatekeeper's features include `regime_structural`. The map's entries were selected using
HMM `regime_causal`. Enabling the threshold now means the score gates against a regime that
did not select the entry it is gating — filtering on a variable unrelated to the selection
criterion. `run.py:412` warns against exactly this and is correct.

Order: **G1 (measure) → G2, G5 (make it trustworthy) → L1 (unify the label) → then wire the
threshold as its own change set, in shadow for one week first.**

---

# 2. Designation and the live map

The intent — surfacing well-sampled strategies the gate structurally rejects — is legitimate.
See C1 for why the gate rejects them. Every fix below preserves that ability and removes a
side effect you did not ask for.

## D1 — Designation promotes a draft map to published `[P0]`

**WHY.** `designate.py` sets `regime_map["status"] = "published"` unconditionally. `vet.py`
writes `"proposed"` in log-only mode, which is the **default** (`VETTING_LOG_ONLY` defaults to
true). So designating against a map that was never approved for live promotes it. Per
`vet.py:458-466`, System 2 treats any status outside `{published, active}` as a withdrawal —
`status` is a live control field, and this script overwrites it without checking.

**VERIFY.** Read the current `regime_strategy_map.json` `status`. Cross-reference the vetting
report for `qualification_run_id` `7fde532c` and check whether that run was `mode: "live"` or
`mode: "log_only"`.

*Confirms if:* the map says `published` and the run was log-only.

**ACT.** Remove the `status` write from `designate.py`. If the map lacks `status`, fail with a
message telling the operator to run `vet.py --live` first. Designation is not an approval
mechanism.

**CONFIRM.** Designating against a proposed map exits non-zero without writing.

**ROLLBACK.** Restore the line.

## D2 — Designation replaces every weight with equal weights `[P0]`

**WHY.** `designate.py` loops over **every** regime with entries and writes
`share = 1/len(entries)` for each. That discards `gates.normalized_weights` entirely —
the softmax over composite scores, the temperature, the minimum-weight floor, the whole of
FIX-S1-001 — including for cells that qualified on merit and were never designated.

**Confirmed from the artifact.** `strategy_weights.json` shows 0.25/0.25/0.25/0.25 and
0.142857 × 7. Live capital is currently allocated equally across everything in the map,
regardless of any score, set by whenever `designate.py` last ran (2026-08-24T10:51:39).

**VERIFY.** Already confirmed. For the record, also compute what
`gates.normalized_weights` would have produced for the same ranked cells, and report the
difference.

**ACT.**
- Restrict weight rewriting to the regimes actually being designated.
- Use `gates.normalized_weights` rather than an inline equal-weight rule. A second, softer
  weighting rule growing beside the first is how the two drift.
- If a designated cell has no meaningful composite score (`rank: 999`, `composite_score: 0.0`),
  give it an explicit, declared weight rather than letting it inherit an accidental one.

**CONFIRM.** Re-run designation; weights in undesignated regimes are unchanged, and the
designated regime's weights match `normalized_weights` output.

**ROLLBACK.** Restore from `audit/reports/baseline/`.

## D3 — Weights are keyed by `strategy_id`, not variant `[P1]`

**WHY.** `{str(e["strategy_id"]): share for e in entries}` is the exact collision that
`gates._variant_key` exists to prevent, with a docstring explaining that a strategy qualifying
at two granularities in one regime collapses to one key (FIX-S1-004). `designate.py` bypasses
it.

It fails loudly — the sum-to-1 check catches it and exits — so this is a latent crash, not
silent corruption. But the crash arrives at the least convenient moment.

**VERIFY.** Check whether any current map regime contains two entries with the same
`strategy_id` at different granularities. Then check the High-Vol arithmetic:
`round(1/7, 6) × 7 = 0.999999`, and the guard is `abs(total - 1.0) > 1e-6`. That is
`1.0e-6`, which is **not** greater than `1e-6`. It passes on the exact boundary.

*Confirms if:* the boundary case is real (it is) or a duplicate exists.

**ACT.** Use `gates._variant_key`. Widen the tolerance to `1e-4`, or normalise the final
weight rather than rounding each share independently.

**CONFIRM.** Unit test: two granularity variants of one strategy in one regime produce two
keys summing to 1.0.

## D4 — Designated metrics are pooled across all regimes `[P1]`

**WHY.** `m = attr._oos_cell_metrics(strat_trades, folds)` is computed on **all** of the
strategy's OOS trades with no regime filter, then written identically into every target
regime. The entry claims the same performance in Trending-Up, Trending-Down and High-Vol.

An entry present in every regime with identical metrics is not a regime-conditioned permission.
It is an unconditional one wearing the map's clothing — which defeats the purpose of having a
regime map at all.

**VERIFY.** Confirm `nnfx_backtrader@D1`, `reference_pullback_continuation@H4` and
`double_bottom_measured_move@D1` (strategy ids 17, 36, 43 per the weights file) appear in
Trending-Up, Trending-Down and High-Vol with byte-identical `metrics` blocks.

**ACT.** Two options — pick one and record it:
- **(a)** Require `--regime` on designation. Compute metrics for that regime's cell only.
  Designation becomes what the map's shape implies.
- **(b)** Add `entry_type: "unconditional"` to the contract and represent these honestly as
  regime-agnostic permissions, so System 3 can size them differently.

(a) is preferable — it keeps one concept in the artifact.

**CONFIRM.** A designated entry appears in one regime with that regime's metrics.

## D5 — Which regimes a designation lands in is accidental `[P1]`

**WHY.** `targets = list(regime_map["regimes"].keys()) or list(all_regimes)`. So the target set
is whatever vetting happened to qualify that run. If vetting qualified only Trending-Up, the
designation goes there alone. If it qualified nothing, it goes to all four.

**Confirmed from the artifact:** `Ranging` is absent from `strategy_weights.json` entirely —
not empty, missing — because Ranging was starved and therefore not in `regimes.keys()`. The
target set was determined by an unrelated outcome.

**VERIFY.** Confirm `Ranging` is absent from the weights file (it is) and check whether System
3 does `weights[regime]` or `weights.get(regime, {})`. The former raises; the latter silently
allocates nothing.

**ACT.** Resolved by D4(a) — an explicit `--regime`. Separately, ensure the weights document
always contains all four regime keys, with `{}` for empty ones, so a consumer can distinguish
"no allocation" from "key missing."

**CONFIRM.** All four regimes present in the weights file after a rebuild.

## D6 — Designation bypasses validation and the audit trail `[P1]`

**WHY.** `vet.py` validates both artifacts against jsonschema before writing and emits
`vetting_report_*.json`. `designate.py` writes the map with a raw `json.dump` — no contract
validation, no report update, no registry update.

After any designation, the vetting report describes a map that no longer exists on disk:
entries it doesn't count, weights it didn't compute, possibly a status it didn't authorise.
The audit trail and the artifact have diverged, and nothing detects it.

**VERIFY.** Compare `vetting_report_*.json` for run `7fde532c` — its `n_qualifying` — against
the actual entry count in `regime_strategy_map.json`.

*Confirms if:* the counts differ.

**ACT.**
- Call `vet._validate` on both artifacts before writing.
- Append a `designation_log` array to the map: who, when, which strategy, which regime, gate
  failures at designation time.
- Emit a `designation_report_*.json` alongside, so every mutation of the live map has a record.

**CONFIRM.** A designation produces a report; contract validation runs and can fail.

## D7 — `tail_dependence` does not measure tail dependence `[P1]`

**WHY.** `tail_dependence = float(np.sum(r_sorted[:-3]))` is the sum of every R value except
the three largest. It is a scale-dependent sum that grows with trade count; it is not a
dependence measure of any kind.

`vet.py`'s DESIGNATED entries record 3.7738, 1.0239 and 0.7705, described as *"a single loss
~3.8x the mean absolute R."* This formula cannot produce those values for a 100-trade
strategy. So either the stored numbers came from a computation that no longer exists, or the
formula was rewritten and the stored values are stale.

**This field ships to System 3 and is used for position sizing.** A sizing input whose meaning
is undefined is worse than an absent one, because the consumer trusts it.

**VERIFY.** Run the current formula against `weekly_gap_fade`'s 100 OOS R-multiples and compare
against the stored 3.7738.

*Confirms if:* they differ materially (they will).

**ACT.** Decide what the field should mean and implement it — e.g. `max(|R|) / mean(|R|)`,
which matches the description in the designation reason. Recompute for all existing entries.
If the intended meaning cannot be recovered, remove the field from the contract rather than
shipping an undefined number.

**CONFIRM.** Recomputed values match the description in the designation reasons.

## D8 — `pairs_passed_fraction` does not count pairs `[P1]`

**WHY.** It counts attribution *cells* (strategy × regime) that pass gates. The name says
currency pairs, and the designation reasons read *"4 of 5 pairs profitable"* and *"3/5"*.
System 3 consumes it for sizing. The name and the value disagree.

**VERIFY.** For `xard_ma_cross_daily_open`, compute both: cells passing gates, and distinct
currency pairs with positive mean R. Compare each against the stored `4/5`.

**ACT.** Rename to `cells_passed_fraction`, **or** implement the per-pair measure the name
implies. If the latter, recompute every stored value. Do not leave both interpretations live.

**CONFIRM.** Field name and computation agree; System 3's contract updated in the same change.

## D9 — Granularity is picked from the first row `[P2]`

**WHY.** `gran = strat_trades["granularity"].iloc[0]`. If a strategy traded more than one
granularity, this silently picks whichever sorted first, and the entry's `variant` string
claims a granularity the metrics may not correspond to.

**VERIFY.** `strat_trades.groupby("granularity").size()` for each of the three designated
strategies. *Confirms if:* any has more than one.

**ACT.** Raise if more than one granularity is present, requiring an explicit `--granularity`.

## D10 — A passing strategy can be designated `[P3]`

**WHY.** `if not failures: pass` with the comment *"Actually, it's fine if it passes, we can
still designate it, or not?"* — an unresolved question in production code. A qualifying
strategy designated this way is tagged `selection_basis: "designated"` with
`gate_failures: []`, misrepresenting merit as an override.

**VERIFY.** Check whether any current designated entry has an empty `gate_failures`.

**ACT.** If the strategy passes, print that it qualifies and exit without writing. It will
enter the map through vetting.

---

# 3. The vetting gate

## C1 — No minimum sample floor, and the gate therefore selects small samples `[P0]`

**WHY.** `gates.evaluate_gates` never reads `trade_count`. It appears only as a tie-break in
`rank_cells`. `low_confidence` is the sole proxy and, with `N_MIN = 5` in `attribute.py`, only
fires below n=5.

The consequence is arithmetic, not accidental. On a bank averaging −0.070 R per trade, PF ≥ 1.5
is reachable only by luck, and luck requires small samples — more trades means regression
toward the true negative mean. So the gate is a small-n filter **by construction**.

Your own artifact demonstrates it: gate-qualified cells have n = 13, 20, 5; the cells you had
to designate have n = 100, 224, 172. **You overrode the gate to get well-sampled cells in.
That is the gate working backwards, and the designations were the correct response to it.**

**VERIFY.** For all 158 non-UNKNOWN cells: median n among cells passing PF ≥ 1.5 versus among
cells failing it. The verification report found 9 versus 24.5. Reproduce.

**ACT.** Hard reject below 30 OOS trades — matching the 30-trade floor already used elsewhere
in the codebase. Add it to `GATES` so it appears in the map header and in rejection reasons.

**CONFIRM.** Re-run vetting. Report which cells the floor removes and which now rank top.
Expect the current three qualifiers to fail.

## C2 — Shrinkage is computed and discarded `[P1]`

**WHY.** `attribute.py` writes `win_rate_shrunk`, `profit_factor_shrunk` and `sharpe_shrunk`.
`vet._load_cells` selects `a.win_rate, a.profit_factor, a.sharpe` — the raw columns. The gate
never sees a shrunk value.

A computed-and-discarded safeguard is worse than none: it appears in the schema, in MLflow, and
in every description of the system, so everyone believes small samples are being moderated when
nothing is.

**VERIFY.** Confirm the column list in `vet._load_cells`. Then report, for the three qualified
cells, raw versus shrunk PF, Sharpe and win rate.

**ACT.** Either point the gate at the shrunk columns **and** raise `N_MIN` well above 5, or
delete the shrunk columns entirely. Both are defensible; the current state is not. If you keep
them, note that shrinking toward the strategy's own global does nothing when the strategy is
uniformly bad — consider a neutral prior (PF = 1.0) instead.

**CONFIRM.** Gate reads shrunk values; re-run and report the change in survivor count.

## C3 — Infinite PF becomes 100 and takes the capital `[P0]`

**WHY.** `vet._cap` maps `inf → 100.0`. A cell with zero losing trades has PF = ∞ and
recovery = ∞. `composite_score = 0.5·sharpe + 0.3·pf + 0.2·recovery − maxdd` gives that cell
roughly **50**, against 2–3 for a normal cell. `normalized_weights` then applies a softmax at
temperature 1.0, where `exp(−47) ≈ 0`.

So one zero-loss cell takes essentially the entire regime's capital, with every other qualifier
pinned at the 0.05 floor. PF = ∞ is a statement about sample size, not performance, and the
cap converts it into maximum conviction.

**VERIFY.** Count cells in the latest attribution run with non-finite PF (the verification
report found 11 of 209). Check whether any reached the map. Then compute what
`normalized_weights` would produce for a regime containing one capped cell and three normal
ones.

**ACT.**
- Exclude non-finite PF cells from qualification outright — a cell with zero losses has not
  demonstrated a loss distribution.
- Cap at something that cannot dominate the composite (e.g. 5.0), and cap `recovery_factor`
  likewise.
- Consider raising `TEMPERATURE` so weights degrade gracefully rather than collapsing.

**CONFIRM.** Re-run; no single weight exceeds a declared maximum (suggest 0.50).

## C4 — Clamped metrics feed the gate `[P1]`

**WHY.** `compute_attribution` clamps `sharpe` to `MAX_PLAUSIBLE_SHARPE` and `max_drawdown` to
`MAX_PLAUSIBLE_DRAWDOWN` when `validate_metrics` flags them, logs a warning, and persists the
clamped value. The gate then reads it. A cell whose n=5 Sharpe computed to 40 is stored at the
clamp and passes `Sharpe ≥ 0.8` comfortably.

Clamping is right for display. Feeding a clamped value into a threshold silently converts an
implausible number into a passing one.

**VERIFY.** Count cells that triggered clamping in the latest run (grep the warning), and check
whether any passed the gate.

**ACT.** Flag clamped cells with `metrics_clamped = true` and reject them at the gate. A metric
outside plausible bounds is a sample-size artifact, not a performance claim.

## C5 — The corrupt-attribution guard cannot fire `[P1]`

**WHY.** `compute_attribution` initialises `violations: List[str] = []`, assigns
`cell_violations = MET.validate_metrics(m)` inside the loop, logs and clamps — and **never
appends to `violations`**. So `if violations: raise RuntimeError(...)` at the end is
unreachable.

The guard that is supposed to refuse shipping corrupt attribution has been dead since it was
written. Same pattern as the rest: the safeguard exists and is not connected.

**VERIFY.** Read the loop and confirm no `violations.extend(...)` or `.append(...)` exists.
*Confirms if:* the list is never mutated. This is a code read; it takes a minute.

**ACT.** Decide the intended behaviour. Given C4, raising on any violation is probably too
strict — clamp-and-flag is more useful. Either wire the guard or delete it. A dead safety check
is a false assurance.

**CONFIRM.** Unit test with a deliberately corrupt cell produces the intended outcome.

## C6 — MaxDD and Recovery are not binding gates `[P2]`

**WHY.** `MaxDD ≤ 0.25` passes 145/158 cells (92%). Drawdown is computed by
`MET.max_drawdown(r)` on the R sequence, so a 5-trade cell can barely draw down — survivors
show 0.0002 and 0.0005, which inflates `Recovery = return / maxdd` into the 8–23 range and
makes `Recovery ≥ 3.0` a function of sample size rather than of risk.

Two of six gates are doing no work, and one of them actively rewards thin samples.

**VERIFY.** Reproduce the per-gate pass rates across all 158 cells. Report the MaxDD
distribution and its correlation with `trade_count`.

**ACT.** Measure drawdown on a fixed-size R sequence rather than a compounding curve, or
replace both with a tail measure that does not degenerate at small n — e.g. worst 5-trade
rolling sum, or CVaR at 5%. Whichever, verify the pass rate is no longer above ~80%.

## C7 — No multiple-testing correction anywhere `[P1]`

**WHY.** 158 cells are evaluated and survivors are selected on out-of-sample metrics.
Selecting on OOS converts OOS into training data. An exhaustive grep for `bonferroni`,
`benjamini`, `hochberg`, `holm`, `fdr`, `deflated` returns zero non-test hits.

The verification report's null simulation is decisive: pure noise through this gate produces
~3 survivors; the real system produces 2. **The gate currently yields fewer survivors than
noise would.**

**VERIFY.** Repeat the grep. Then reproduce the null: permute regime labels within
`(strategy_id, granularity, is_oos)` blocks, run the real gate, 1,000 replications.

**ACT.** Add FDR control across all evaluated cells, and make the null simulation part of every
attribution run (see C8).

## C8 — Make the null floor a permanent gate component `[P1]`

**WHY.** The permutation test is the single most informative diagnostic this audit produced. As
a one-off it will drift out of date. As a per-run check it answers, every time, whether the
survivor set beats chance.

**ACT.** On every attribution run, compute the null survivor distribution and report the real
count alongside it. **If the observed count does not exceed the null, refuse to publish a map.**

**CONFIRM.** A run against permuted labels refuses to publish.

## C9 — The registry loses the qualified/designated distinction `[P2]`

**WHY.** `vet._update_registry` iterates every map entry and sets `is_qualified = true`,
designated ones included. Anything reading that column cannot tell a gate pass from an owner
override.

**VERIFY.** Compare `is_qualified = true` ids in `dim_strategy_registry` against the map's
`selection_basis` values.

**ACT.** Add `selection_basis` to the registry, or a separate `is_designated` column.

## C10 — Strategy 10 still counts toward the denominator `[P3]`

**WHY.** `INTEGRITY_DISQUALIFIED` is checked at vet time, not at attribution time. Strategy 10's
cells remain in `fact_strategy_regime_attribution` and count toward the 158, inflating the
denominator with cells that can never qualify.

Its measured +0.388 R original / −0.441 inverted in the engine test is a textbook lookahead
signature and independently confirms the ban was correct.

**ACT.** Exclude integrity-disqualified strategies at attribution time, or mark their cells so
they are excluded from any denominator.

---

# 4. Label unification

## L1 — The switch is built and set to the wrong value `[P0]`

**WHY.** `attribute.py` already has `SELECTION_SOURCE_LABEL` as a constant, with a whitelisted
`regime_structural` query pointing at `fact_regime_structural`, and a docstring explaining
exactly this defect. **The mechanism is in place. The constant still reads `"regime_causal"`.**

Selection therefore runs on the HMM label while routing, Gatekeeper features and System-3 stats
run on structural — 19–36% agreement, kappa −0.10 to +0.15 at every lag. The map's cells do not
correspond to the conditions that fire them.

**VERIFY.** Read the constant. Confirm `fact_regime_structural` exists and is populated: row
count, per-instrument min and max `bar_time_utc`, and coverage against `fact_market_prices`.

*Blocks if:* the table does not exist or is not fully backfilled. Complete
`REMEDIATION_R2.md` §R2.1–R2.4 first.

**ACT.** Once the table is populated, change the constant to `"regime_structural"` and re-run
attribution. Report before/after: cell count, coverage per granularity (expect ~40% → near
100%), and the full PF distribution.

**CONFIRM.** The map header's `source_label` reads `regime_structural`, and the Gatekeeper
routes on the same label.

## L2 — `REGIME_MODEL_VERSION` will drift when L1 flips `[P1]`

**WHY.** `REGIME_MODEL_VERSION = "hmm-v1.0.0"` is hardcoded in both `attribute.py` and
`vet.py`, and written into every attribution row and every map header. It is **not** tied to
`SELECTION_SOURCE_LABEL`. Flip the label and every artifact will still claim HMM provenance.

The `SELECTION_SOURCE_LABEL` comment argues that a constant is better than a docstring because
the two cannot drift. That reasoning is right and this constant breaks it.

**VERIFY.** Confirm both constants are independent of the label source. Check the current
`strategy_weights.json` header: it says `hmm-v1.0.0`, which is currently accurate.

**ACT.** Derive `REGIME_MODEL_VERSION` from `SELECTION_SOURCE_LABEL` — a dict lookup beside
`_REGIME_SOURCE_SQL`. Do this **before** L1, so the first structural run is labelled correctly.

## L3 — `persistence_smooth` is not causal and its docstring says it is `[P1]`

**WHY.** The docstring claims the label at bar t depends only on bars 0..t. The implementation
scans forward to find the segment end and decides its fate from the **total** length, so the
label at bar i depends on bars up to j−1. The leading-boundary fixup assigns a future label
backward explicitly.

This is the leak FIX-S1-013 describes. The fix added a correct function beside it and left this
one in place with its false docstring. It remains reachable at `hmm_regime.py:583` when
`CAUSAL_SMOOTHING = False` — one boolean away from putting a multi-bar leak back into a column
named `regime_causal`.

**VERIFY.** Construct a label sequence where a short segment is followed by a long one, run both
functions, and confirm they differ at the short segment. Confirm `CAUSAL_SMOOTHING` is currently
`True`.

**ACT.** Rename to `persistence_smooth_noncausal`, correct the docstring, and delete the
`CAUSAL_SMOOTHING = False` branch. A config flag that reintroduces leakage is not a feature.

## L4 — Three different lookback windows produce three labels `[P2]`

**WHY.** `run.py:62` uses `lookback_years=3`; `publish_strategy_stats.py` uses 25; the
Gatekeeper uses full history. `ewm(adjust=False)` seeds from the first row of whatever frame it
receives, so each window yields a slightly different label — measured at 0.998–0.999 agreement,
1–7 bars per pair. All three are called `regime_structural`.

**ACT.** Resolved by L1: once `fact_regime_structural` is populated, callers **read** rather
than recompute. `build_structural_labels` is invoked in exactly one place — the job that fills
the table, always over full history from a fixed anchor.

## L5 — The structural label is not persisted at decision time `[P0]`

**WHY.** `get_current_regimes` computes in memory and returns. Nothing writes it. So there is no
record of what regime the system believed at any past moment, live-versus-backtest divergence
cannot be checked retrospectively, and this mismatch was undetectable for exactly that reason.

**Every day without this is a day of decision history that cannot be recovered.**

**ACT.** `REMEDIATION_R2.md` §R2.2 — the append-only `fact_regime_structural_live` table, written
from `run.py` inside its own try/except so a logging failure can never block a signal.

---

# 5. Staleness and control

## S1 — The map has no expiry and the Gatekeeper fails open `[P0]`

**WHY.** `_evidence_window` computes `evidence_age_days` and documents the 2026-08-24 incident
where a map was published off trades that stopped on 2026-08-14. Its docstring says *"Reported,
never gated on here — the consumer decides what is too old."* The consumer does not gate on it
either. So the measurement exists and nothing acts.

A stale map keeps trading. That is failing **open**, which is worse than the FIX-S1-016 silent
stall — that at least failed closed.

**VERIFY.** Read `evidence_age_days` from the current map. Confirm no consumer reads it: grep
for the field across `src/`.

**ACT.** `REMEDIATION_R2.md` §R1.2–R1.3: add `expires_at_utc` and `source_label` to the header;
the Gatekeeper refuses to authorise trades on an expired map, a map older than
`MAP_MAX_AGE_DAYS` (7), or one whose `source_label` differs from the routing label. Refusal
means no signals, logged distinctly from "no signals generated."

## S2 — One live map cell no longer qualifies `[P0]`

**WHY.** `weekly_day_reversal_ea@D1` (n=5) fails on OOS = 11.89 months < 12 on current data — a
knife-edge flip caused by a data refresh shifting fold boundaries. It is still in the live map
as qualified. Nothing revalidates.

**VERIFY.** Recompute gate metrics for all three qualified cells against current data.

**ACT.** Remove any cell that no longer qualifies, today, independently of everything else.
Then add revalidation to every attribution run: any live map entry that fails on current data is
auto-expired and alerted.

## S3 — `fact_market_regime_v2` has been stale for ten days `[P1]`

**WHY.** Latest regime bar 2026-08-24; latest price bar 2026-09-04. The HMM batch job has been
failing or not running, silently. Also, only 12,414 of 31,149 H1 rows carry a causal label —
attribution currently sees ~40% of the population, with the exclusion correlated to fold
structure.

**VERIFY.** Check the job's schedule and last successful run. Report what attribution does with
trades on unlabelled bars — dropped, or bucketed as UNKNOWN. The code suggests UNKNOWN
(deliberately, per the `tag_regime_at_entry` docstring); confirm it.

**ACT.** `REMEDIATION_R2.md` §R4 — freshness contracts, job completion records, alerting. Note
that L1 largely resolves the coverage problem, since structural is defined for every bar past
warmup.

---

# 6. Engine and cost

Covered in detail by `ENGINE_VALIDATION_2.md`. Listed here so the register is complete.

| id | item | severity | status |
|---|---|---|---|
| E1 | Spread never reaches R (mid-to-mid fills) | P1 | Confirmed, fix after Q2 |
| E2 | v1 and v2 engine trades pooled in one population | P1 | Confirmed |
| E3 | STOP_FIRST intrabar ambiguity | P1 | Unquantified — Q4 |
| E4 | v1 contemporaneous fill (optimistic) | P1 | Confirmed |
| E5 | USD_JPY H4 at −0.228 R, median −1.0022 | P1 | Confirmed, cause unknown |
| E6 | Long/short asymmetry 0.059 R | P2 | Confirmed, cause unknown |
| E7 | Exit-reason vocabulary differs by engine | P2 | Confirmed |
| E8 | Sign error in `d2_` and `d5_` CSVs | P3 | Confirmed |

Do not act on E1 until `ENGINE_VALIDATION_2.md` Q2 returns the measured stop distance — the
cost baseline may be wrong by 1.5×, which changes what "correct" means.

---

# 7. Reporting

`audit/reports/fix_register/report.md`, one section per item:

- Status: `CONFIRMED` / `NOT A PROBLEM` / `BLOCKED` / `FIXED`
- The verification output, verbatim
- The diff or DDL, if acted on
- The confirmation output
- Anything the item's WHY got wrong

Plus a **"Not in the register"** section. Every pass so far has surfaced something bigger there
than in the spec — the engine split, the designation weight overwrite. Assume it will again.

---

# 8. Order of work

**Today, before anything else:**
1. **S2** — remove the cell that no longer qualifies. Live risk.
2. **G1 verify** — pull the shadow counters. One number, tells you how much the gate would filter.
3. **D1, D2 verify** — status promotion and equal weights. D2 is already confirmed from the artifact.

**This week:**
4. **L5** — persist the structural label. Time-sensitive; every day loses recoverable history.
5. **S1** — map expiry and fail-closed Gatekeeper.
6. **D1, D2, D3, D5, D6** — make designation do only what it was meant to do.
7. **C5** — the dead guard. A minute to verify, small to fix.
8. **G2** — Gatekeeper load-time assertion.

**Then, in order:**
9. **L2** → **L1** — version constant first, then flip the label. Requires `fact_regime_structural`
   populated.
10. **ENGINE_VALIDATION_2 Q1–Q3** — the cost baseline and the engine split.
11. **E1** — spread into R, once Q2 has settled the baseline.
12. **C1, C2, C3, C4, C6, C7, C8** — the gate rebuild. After the label and the cost model, so
    re-running vetting measures something real.
13. **G5** → wire the Gatekeeper threshold, shadow for one week, then enforce.
14. **D4, D7, D8, D9, D10, C9, C10, L3, L4, S3** — the remainder.

**Expected outcome of step 12:** zero qualified cells. That is the correct result, not a failure
of the remediation. Plan for the map to be empty and for the system to be stopped by its own
gate rather than by a decision.