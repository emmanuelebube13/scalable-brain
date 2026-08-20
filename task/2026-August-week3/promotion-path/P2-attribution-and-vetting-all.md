# P2 — Attribution and vetting over the whole universe

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Est:** 3–4 h · **Risk:** medium — regenerates the live map.
**Needs:** P1. **Blocks:** P3.

---

## Why

`attribute.py` and `vet.py` already do the right thing; they have simply never seen more
than ten strategies. Once P1 puts every strategy's trades in `fact_trade_outcomes`, both
should widen with little or no change. **Verify that rather than assume it** — this is the
step where a hidden assumption about "ten strategies" will surface.

---

## Hard constraints

1. **Do not touch `gates.py`.** No new thresholds, no configurability, no soft mode. The
   gates keep meaning exactly what they mean today — that is what makes `designated` in P3
   an honest label rather than a rebrand.
2. **`INTEGRITY_DISQUALIFIED` stays and stays checked before the performance gates.**
   `Range_Stochastic_Divergence` (id 10) must remain barred; its metrics are fiction.
3. `vet` writes `results/reports/proposed_*` unless `--live`. Keep that.
4. OOS-only metrics throughout.
5. Only `regime_causal`.

---

## Execution plan

### Step 1 — Widen attribution

Run `python -m src.system1.attribution.attribute` and see what happens with ~62 strategies.
Look specifically for:

- anything that assumes a small strategy count (hardcoded ranges, `LIMIT`, fixed arrays)
- Bayesian shrinkage behaviour on thin cells — many new cells will be thin, and shrinkage
  was tuned when there were 40 cells, not hundreds
- runtime: if it becomes slow, say so with a number rather than optimising blindly

Report cells produced, OOS trades, and any UNKNOWN-regime rows.

### Step 2 — Add the regime dimension honestly

Attribution joins trades to the regime at entry. The trial (`regime-aware/STATE.md`)
measured that regime routing produces **no** significant improvement — 126 comparisons, the
one significant cell being a USD_JPY-deletion artifact.

So: keep attributing by regime for reporting, but **do not build regime routing into the
promotion decision** on the strength of the trial, because the trial says it does not work.
If a future measurement changes that, it changes then.

Where a regime label is needed, use `structural` (see
`docs/design/REGIME_STATE_AND_HOW_TO_RUN.md`), not `d1_trend` and not `hmm_causal`.

### Step 3 — Vet the whole universe

```
python -m src.system1.vetting.vet            # log-only proposal first
python -m src.system1.vetting.vet --live     # only after the proposal is reviewed
```

Report: cells scored, qualifiers, and the full rejection profile per gate. **The expected
result is a very small number of qualifiers, possibly zero.** That is information, not
failure — do not tune anything to change it.

### Step 4 — A ranking that survives 62 strategies

With ~62 strategies the existing composite will produce a long tail of near-ties and some
flattering artifacts. Produce a ranked report carrying, per strategy:

- the pooled OOS metrics and every gate it fails
- **a bootstrap CI on mean R** — a point estimate over ~100 trades decides nothing
- **per-pair dispersion**: cells passed of cells attempted, and the share of trades in the
  largest pair. A pooled pass with 0/5 cells passing is a concentration artifact, and
  `nnfx_backtrader` is exactly that today (113 trades, best cell 16 trades)
- **tail dependence**: total R with the top 3 winners removed. `weekly_day_reversal_ea`
  loses ~77% of its profit that way — the owner must be able to see that before choosing

This report is what the owner reads in order to choose. Make it honest and make it short.

### Step 5 — Tests + `STATE.md`

- attribution handles a strategy with zero trades without crashing or dropping it silently
- vetting's rejection counts sum to the cells scored
- a disqualified strategy is rejected before the performance gates, in its own category
- the ranking report's CI and dispersion columns are populated for every row

---

## Definition of done

- [ ] Attribution covers every registered strategy; count stated
- [ ] `vet` run log-only first, reviewed, then `--live` with the owner's knowledge
- [ ] Ranking report with CI, dispersion and tail-dependence columns
- [ ] `gates.py` **unchanged** — verify with `git diff` and say so
- [ ] Qualifier count reported honestly, whatever it is

## Reviewer will check

- `git diff src/system1/vetting/gates.py` is empty.
- Strategy 10 still barred.
- That the ranking report's tail-dependence and dispersion columns are real, since those
  are the two things that unmasked the last two false positives.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix |
|---|---|---|---|---|
| | | | | |
