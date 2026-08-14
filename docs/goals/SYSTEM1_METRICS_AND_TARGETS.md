# System 1 — metrics and targets, stage by stage

**Written:** 2026-08-13 · **Baselines measured the same day**
**Companion:** `docs/goals/VALUE_MILESTONES.md` (the M1–M4 ladder this serves)
**Sibling documents to be produced by the other machines:** `SYSTEM2_METRICS_AND_TARGETS.md`,
`SYSTEM3_METRICS_AND_TARGETS.md` — see §12 for the brief and the rules that make all three
compose.

---

## The rule this document is built on

> **A metric without a threshold and a consequence is decoration.**

Every row below has four columns for that reason: what is measured, where it stands, what it
must reach, and **what happens when it fails**. If the consequence column would read "we look at
it and feel concerned", the metric does not belong here.

A second rule, learned the hard way in this repo:

> **Prefer metrics that can fail.** `regime_accuracy = 0.9389` looked excellent for months while
> being ~0.58 chance agreement. A metric that cannot go red is not monitoring anything.

---

## 1. MODEL-001 — Ingest

| Metric | Current | Target | On failure |
|---|---|---|---|
| Freshness vs last market close | H1 at last close ✅ | ≤ 1 bar behind last scheduled ingest | heartbeat CRITICAL; block downstream retrain |
| Pairs active | **5** | **13** (8 backfilling) | evaluation proceeds, pair reported `skipped` |
| Granularity coverage | D1/H4/H1/W1/M15/M30 ✅ | D1/H4/H1/W1 current | CRITICAL if a modelling granularity is stale |
| Bars quarantined per run | not tracked | < 0.1% of fetched | > 1% ⇒ abort run, do not upsert |
| Unexpected gaps per run | reported, not gated | 0 outside market close | > 0 ⇒ WARN + manifest entry |
| Incomplete bars ingested | 0 ✅ | **0, always** | any ⇒ severity-1 defect |
| `fact_market_prices` rows | **4,687,448** | grows monotonically | any decrease ⇒ severity-1 |

**Note:** ingest is weekly (`0 0 * * 6`). Mid-week staleness of up to 5 days is by design, not a
fault. Any freshness rule must compare against the last *scheduled* ingest, not wall clock.

---

## 2. MODEL-002 — Feature store

| Metric | Current | Target | On failure |
|---|---|---|---|
| Determinism (byte-identical re-run) | asserted in tests | **100%** | severity-1; features are the base of everything |
| Look-ahead probe | trailing-only by construction | **0 violations** | block promotion |
| Feature NaN rate post-warmup | not tracked | < 0.5% | > 2% ⇒ investigate before regime fit |
| Feature-set version pinned in bundle | ✅ | always | publish abort |

---

## 3. MODEL-003 — Regimes

| Metric | Current | Target | On failure |
|---|---|---|---|
| **Cohen's kappa** (chance-corrected) | D1 0.853 · **H4 0.322** · H1 0.947 | **≥ 0.40 all granularities** | `KAPPA_GATE` fails ⇒ K-Means fallback |
| Raw holdout agreement | 0.9389 / 0.7143 / 0.9644 | ≥ 0.70 (kept, secondary) | fallback |
| Label share of dominant regime | **75% / 75% / 43%** | **≤ 60%** | flag degenerate taxonomy |
| Labels unused after thresholding | Tr-Down unused at τ>0 | **0 unused** | taxonomy review — see FIX-S1-012 |
| Flicker rate (smoothed) | 0.0072 / 0.0076 / 0.0237 | ≤ 0.05 | investigate over-segmentation |
| Causal-label look-ahead | **2-bar leak** (FIX-S1-013) | **0 bars** | enable `CAUSAL_SMOOTHING` |
| Rows | **847,151** | tracks prices | — |

**The kappa row is the one that matters.** H4 is the current failure and it is not a separate
defect — it is the dominant-label problem showing up in the only metric that can see it.

---

## 4. MODEL-004 — Attribution

| Metric | Current | Target | On failure |
|---|---|---|---|
| Outcomes freshness | **14 days stale** ❌ | ≤ 1 ingest cycle | CRITICAL; verdicts are stale |
| `fact_trade_outcomes` rows | **134,407** | ≥ prior vintage | **any decrease ⇒ severity-1** (DELETE-then-rebuild has no transaction) |
| Attribution cells | **1,120** | ≥ strategies × regimes × grans populated | — |
| Cells flagged `low_confidence` | not summarised | < 40% of cells | report; never silently qualify |
| Regime join is causal | ✅ (with the 2-bar caveat) | point-in-time, always | severity-1 |
| **Discrimination — `n_discriminating`** | **0 of 10** | **≥ 3 of 10** | if 0 after FIX-S1-012, regime conditioning is not earning its place |

---

## 5. MODEL-005 — Vetting

| Metric | Current | Target | On failure |
|---|---|---|---|
| Qualified cells | **4** (all one strategy) | **≥ 8 across ≥ 3 strategies** | concentration risk stands |
| Distinct qualified strategies | **1** | **≥ 3** | finding C unresolved |
| Regimes with coverage | 3 of 4 (High-Vol empty) | **4 of 4** | starvation flagged |
| Min weight in any regime | **8e-8** (finding A) | **≥ 0.05** | weight starvation; softmax/rank fix |
| Strategies passing pooled but < half their cells | not tracked | **report always** | dispersion warning |
| Gate thresholds imported not copied | ✅ enforced by test | always | test failure blocks merge |

---

## 6. MODEL-006 — Gatekeeper

| Metric | Current | Target | On failure |
|---|---|---|---|
| OOS uplift vs baseline | 0.0377 | > 0 and bootstrap-significant | fail-closed, no promote |
| `beats_incumbent` | ratchet at 0.965 | beat incumbent **with tolerance band** | bare `>=` converges to luckiest draw |
| Leakage guard tests | ✅ green | always | block promote |
| Calibration honesty | manifest-checked | reported per bundle | publish abort |

---

## 7. MODEL-007 — Publish

| Metric | Current | Target | On failure |
|---|---|---|---|
| SHA256 verify before pointer flip | ✅ | **100%** | abort, delete partial, pointer untouched |
| Secret scan on bundle | ✅ | 0 findings | abort |
| Pointer-flip-last ordering | ✅ | always | severity-1 |
| Bundle reproducible from manifest | not tested | 100% | — |

---

## 8. MODEL-008 — Queue

| Metric | Current | Target | On failure |
|---|---|---|---|
| Provider | **`local`** ❌ | **`pubsub`** | S3 cannot read signals — dead end |
| Schema validation | ✅ | 100% | DLQ |
| DLQ depth | n/a | 0 sustained | alert |
| **Signals published (S1) = signals received (S2)** | **unmeasurable** | **exact match** | see §12 |

---

## 9. MODEL-009 — Orchestrator

| Metric | Current | Target | On failure |
|---|---|---|---|
| Cron liveness | **held on purpose** | held until Computer 2 asks | heartbeat must know this — see §11 |
| Single-flight lock respected | ✅ | always | severity-1 |
| Promotions with a failing gate | 0 | **0, always** | severity-1 |
| Time since last successful evaluation | 255h | < 192h when un-held | WARN |

---

## 10. Research sandbox (T6 + contract-v2)

| Metric | Current | Target | On failure |
|---|---|---|---|
| v2 strategies registered | **19** | 51 | — |
| **v2 strategies promotable to `qualified`** | **0 — no path exists** | full path | evaluation dead-ends |
| Strategies passing `assert_no_lookahead_v2` | required to register | **100%** | rejected |
| Golden fixture per strategy | required | **100%** | rejected unread |
| Per-cell verdicts reported | ✅ | always | pooled-only hides concentration |
| Native-vs-H1 resolution delta published | ✅ | always | fidelity claim unsupported |

---

## 11. Cross-cutting

| Metric | Current | Target | On failure |
|---|---|---|---|
| `pytest src/system1` | **266 passing** | green, never decreasing | block merge |
| `pytest src/layer0/strategies` | **242 passing** | green | block merge |
| Look-ahead defects found to date | **3** (FIX-S1-005, -013, swing audit) | trend to 0 | treat as house risk |
| Read-only incumbent files unmodified | checksum-pinned | always | block merge |
| **Alerts that are actionable** | **1 of 3** (2 are the deliberate hold) | **100%** | an alarm that cries wolf is worse than none |
| Open findings without a FIX doc | 2 (champion, ATR case-mismatch) | 0 | untracked defect |

---

## 12. Brief for Systems 2 and 3 — and the rules that make the three compose

Send this section to the other two machines.

### Produce the same shape

A table per stage with exactly four columns: **metric · current · target · on failure**. Current
must be *measured*, not estimated. If a metric is not currently measurable, write
`unmeasurable` — that is itself a finding, and more useful than a guess.

### Three rules

1. **Every metric needs a consequence.** If nothing changes when it goes red, delete the row.
2. **Prefer metrics that can fail.** State the baseline a metric is compared against. An
   absolute threshold on a skewed quantity is how `accuracy 0.94` hid `kappa 0.32` here.
3. **Default-safe reporting.** Missing or stale ⇒ the metric reads RED, never blank. This
   mirrors the system-wide REJECT-on-missing posture.

### The handoff metrics — these must reconcile across machines

This is the part that turns three dashboards into one system view. Each pair must match
**exactly**, and a mismatch is a severity-1 defect owned jointly:

| # | Boundary | S1 measures | S2/S3 measures | Must satisfy |
|---|---|---|---|---|
| H1 | S1 → S2 | scored signals published | signals received | **equal** |
| H2 | S1 → S2/S3 | bundle version + SHA256 published | bundle version + SHA256 loaded | **identical** |
| H3 | S2 → S3 | — | orders submitted / orders approved | approved ≤ submitted |
| H4 | S3 → broker | — | approved orders / broker fills | fills ≤ approved |
| H5 | round trip | strategies in live map | strategies actually traded | **equal** |
| H6 | P&L | expected r-multiple distribution | realised r-multiples | live within backtest envelope |

**H5 is the one that would have caught the current problem.** The live map contains one strategy;
the number of strategies actually trading is zero, because it cannot fire. A reconciliation
metric on that boundary makes that visible on day one instead of after ten losing trades.

**H6 is the M3 milestone in metric form.** It is the only row that can tell you whether the
backtest is honest.

### Ask each system for one number

Beyond the tables, each system should nominate **a single headline metric** — the one that, if
you could see only one, tells you whether that system is healthy.

- **System 1:** distinct strategies qualified through honest gates. *Today: 0.*
- **System 2:** proposed — fill rate vs intended orders, and slippage vs modelled.
- **System 3:** proposed — rejections by layer, and whether any breach reached the account.

---

## 13. How this ties to the value ladder

| Ladder rung | The metrics that prove it |
|---|---|
| **M1 — Honest zero** | §5 distinct qualified strategies = 0 *honestly*; §3 kappa ≥ 0.40; §3 causal leak = 0; H5 reconciles |
| **M2 — First qualifier** | §5 ≥ 1 strategy qualified, per-cell reported; §10 promotion path exists |
| **M3 — Forward test** | H6 live within backtest envelope for 6 months |
| **M4 — Verified curve** | H6 sustained 12 months, one adverse regime survived |

Review cadence: these numbers are re-measured **after every retrain**, and the deltas recorded.
A target that has not moved in two cycles is either done or not being worked on — both worth
knowing.
