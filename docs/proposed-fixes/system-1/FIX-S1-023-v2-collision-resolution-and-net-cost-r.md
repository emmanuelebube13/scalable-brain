# FIX-S1-022 — v2 engine: M15 same-bar stop/TP collision resolution (O-29) and r_multiple net of round-trip cost

**Status:** FIXED 2026-09-17 (code landed, uncommitted; **fact rebuild pending — see Blast
radius**) · **Severity:** high (changes the definition of every v2 `r_multiple`) ·
**Register:** task/OPEN.md O-29 (collisions) + owner decision 2026-09-17 (costs) ·
**Author:** Claude (Fable 5), owner-authorized

---

## Summary

Two owner-approved measurement changes to `src/layer0/strategies/position_engine.py`, the
v2 execution path:

1. **O-29 — same-bar stop/TP collisions are now resolved against M15 bars.** A bar whose
   range contained both the working stop and a take-profit level used to fill the stop only
   (F5, "stop before target, always"). That rule is a measured pessimistic bias of
   **+0.026 R at v2 H4 and +0.029 R at v2 D1** against M15 ground truth
   (`audit/reports/engine_validation_2/report.md` §Q4.3, §B1;
   `q4_counterfactual_R_v2_measured.csv`). The engine now walks the M15 bars inside the
   collision bar and takes whichever level the market touched first.

2. **`r_multiple` is now NET of a flat round-trip transaction cost** (owner decision
   2026-09-17). The module header used to promise the opposite ("r-multiples are spread-free
   by construction") — that header is rewritten. At exit:

       cost_price = ROUND_TRIP_COST_PIPS * pip_size(pair)
       r_multiple = (pnl_price − cost_price · Σ fraction) / stop_distance_price

## Defects being fixed

- **B1 (intrabar ambiguity):** the stop-first tie-break was an assumption, not a
  measurement, and the audit proved it costs real R at H4/D1. 6.5 % of v2 H4 OOS exits were
  collisions; ~52 % are resolvable at M15, 48 % are not (both levels inside one M15 bar).
- **Cost-free R:** every v2 `r_multiple` ignored spread/commission entirely, so strategy
  ranking, gates and attribution all ran on gross numbers no live fill can achieve. The
  measured live cost floor (§Q2) was invisible to every downstream consumer.

## Design choices

- **M15 first-touch walk (O-29).** Only when a bar touches BOTH the working stop and ≥1
  unfilled take-profit level, and the market did not gap through the stop (a gap-through
  means the stop was first by construction, F6 unchanged). The M15 bars covering the
  decision bar's span are walked in time order:
  - M15 bar touches only TP level(s) → those legs fill at their levels (nearest first,
    same convention as `_check_exit_legs`); the walk continues on the remainder;
  - M15 bar touches only the stop → remainder closes at the stop, ordinary `STOP` exit
    (resolved by evidence, not flagged);
  - M15 bar touches **both** → UNRESOLVABLE: resolve **stop-first** (conservative — it
    preserves the old floor, and the audit shows the honest alternative is a coin flip)
    and mark the trade's `exit_reason = "sl_tp_ambiguous"` so it is queryable. Never
    silent.
- **Fallback = stop-first + `sl_tp_ambiguous`, logged once per run** when M15 data is
  absent for the bar, the loader raises (no database), or M15 contradicts the coarse bar
  (stop touched on the decision bar but never in M15 — an ingest gap). The engine still
  runs everywhere; a dead DB disables the loader for the rest of that run instead of
  retrying per collision.
- **Lazy, injectable loading.** M15 rows are fetched per collision bar only (never the
  2.6M-row series), via `load_m15_window` → `src/common/db.py` (the only door), with an
  `lru_cache` so overlapping strategies do not re-query the same bar. `PositionEngine.run`
  accepts `m15_loader=` (tests inject frames; `None` declares no source) and
  `resolve_collisions=False` restores the pre-O-29 stop-first behaviour exactly — the
  audit's counterfactual stays reachable.
- **Bar span is inferred from the resolution index** (min positive step), not from the
  `granularity` label: the H1 harness passes the native label while resolving on H1 bars.
- **Flat 2.4 pips round trip.** The midpoint of the measured 1.8–2.9 pip live spreads
  recorded in `task/2026-August-week3/portfolio-eval/PREREGISTRATION.md` line 28. It is a
  flat bracket midpoint, deliberately not per-pair; refinable per pair from live fills
  later. Provenance is cited at the constant (`ROUND_TRIP_COST_PIPS = 2.4`).
- **Pip size per pair.** `cost_price = ROUND_TRIP_COST_PIPS * get_pip_value(pair)` — JPY
  pairs 0.01, everything else 0.0001, resolved at trade finalisation from the trade's own
  pair. Never a pooled/first-pair pip (the O-28 defect), and pinned by a USD_JPY test.
- **Leg treatment: cost charged once per leg's closed fraction.** The engine's leg model
  fills each `ExitLeg` at its own bar and price — every leg is its own exit crossing of
  the spread, so the honest charge is `Σ fraction_i · cost_price`. Because declared
  fractions sum to 1.0 (contract) this equals exactly one round trip for a fully closed
  position; the distinction would only matter for legs sharing one crossing, which the
  engine does not model. Stated here as the deliberate choice.
- **`r_multiple_gross` is a new trades column** (the pre-cost figure, the old
  definition). It keeps execution geometry testable, makes the cost decomposition
  bit-exact (`net == gross − (cost_price·Σfraction)/risk`, asserted to zero residual in
  `test_v1_equivalence`), and preserves the pre-change counterfactual. Both come from the
  single computation site `realized_r_multiple` (new optional `cost_price` argument).
- **`size_fraction` scales net and gross alike:** a half-size idea risks half an R and
  pays half the cost.

## Evidence and sanity check

- Audit ground truth: `q4_counterfactual_R_v2_measured.csv` (stop-first bias vs M15 truth:
  +0.0286 R at D1, +0.0257 R at H4, +0.0007 R at H1), `q4_m15_resolution_v2_measured.csv`
  (D1: 68 tp-first / 22 stop-first / 2 same-M15-bar).
- **Before/after on a real strategy** (this change, native D1, all 5 pairs,
  `inside_bar_reversal`, 615 trades, 75 collision bars — 12.2 %, the most
  collision-exposed strategy in the current fleet):
  - mean R before (gross, stop-first): **−0.1190**
  - mean R after (net, M15-resolved): **−0.0633** → total shift **+0.0556**
    - collision component: **+0.1153** (60 of 75 collisions flip to `TAKE_PROFIT`,
      1 unresolvable → `sl_tp_ambiguous`, rest confirmed `STOP`) — same sign as the
      audit's D1 measurement, larger because this strategy's collision share (12.2 %) is
      ~3.5× the pooled D1 rate;
    - cost component: **−0.0596** (≈ 2.4 pips / typical D1 stop distance).
  - The tp-first/stop-first/ambiguous split (60/14/1) matches the audit's D1 resolution
    proportions (68/22/2).
- Fleet scan under current strategy code: 179 collision bars across 37,325 v2 trades
  (~0.5 %). Far below the audit's 6.5 % H4 figure because that population predated the
  O-28 JPY pip fix (mis-sized tiny JPY brackets collided constantly; e.g.
  `smashing_forex_2` USD_JPY had 990 audit-era collisions and has 0 today). The mechanism
  is correspondingly less R-moving fleet-wide today, but every collision it does resolve
  is now measured, not assumed.

## Blast radius — full rebuild required

**Every v2 `r_multiple` changes definition** (net of cost; collision exits may also flip
side). Every row of `fact_trade_outcomes` produced by `position_engine_v2`, and everything
derived from it — attribution, gates, ranking, the regime-strategy map, weights — is stale
until rebuilt. `exit_reason` gains a new value `sl_tp_ambiguous` (fits the varchar(50)
column; `persist_all` writes it verbatim, no code change needed there).

**The session owner runs the rebuild** (`src.outcomes.persist_all`, then the downstream
vet per `run-vetting`) after sign-off. Deliberately NOT run as part of this change.

Also note: `is_winner` in `fact_trade_outcomes` (`r_multiple > 0`) now means net winner —
a trade that gains less than 2.4 pips per unit risk is now a loss, which is the point.

## Files changed (uncommitted)

- `src/layer0/strategies/position_engine.py` — header rewritten (cost + O-29 sections);
  `ROUND_TRIP_COST_PIPS`; `realized_r_multiple(cost_price=…)`; `load_m15_window` +
  `_CollisionContext` (lazy, cached, degrades once-logged); `_check_stop` collision
  detection + `_resolve_collision` M15 walk; `r_multiple_gross` trades column;
  `EngineConfigEcho.round_trip_cost_pips` / `.collision_resolution`;
  `run(m15_loader=…, resolve_collisions=…)`.
- `src/layer0/strategies/tests/test_position_engine.py` — `test_v1_equivalence` upgraded,
  not deleted: gross R must still match T6 **bit-for-bit** (legacy collision rule, no DB),
  and net must differ from gross by **exactly** the cost term (zero residual). Geometry
  tests assert gross; net asserted against the single computation site. Nine new tests:
  M15 tp-first (long), M15 stop-first (short), unresolvable same-M15-bar → stop-first +
  `sl_tp_ambiguous`, no-loader fallback, loader-failure fallback, legacy flag
  (`resolve_collisions=False`, loader never called), partial scale-out then stop within
  one collision bar, exact cost decomposition (EUR_USD), per-pair pip size (USD_JPY).
- `docs/proposed-fixes/system-1/FIX-S1-022-v2-collision-resolution-and-net-cost-r.md` —
  this document.

`persist_all.py` needed no change (exit_reason flows verbatim; verified column width).
`contract_v2.py`, `v2_harness.py`, strategy files, `src/signals/`: untouched (owned by
concurrent agents / out of scope).

## Verification

- `python -m pytest src/layer0 -q --ignore=src/layer0/strategies/research/tests` →
  **175 passed**.
- `python -m pytest src -q --ignore=src/layer0/strategies/research/tests` →
  **864 passed, 1 skipped** (855 passed before this change; the +9 are the new tests, no
  new reds).
- Unit tests are hermetic: no engine test touches the database (the equivalence fixture
  produces zero collision bars — verified — and every collision test injects its loader).
- `black` clean on both changed files.
