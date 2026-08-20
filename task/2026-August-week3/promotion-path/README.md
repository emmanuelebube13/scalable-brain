# The promotion path — one door from any strategy to a published model set

**Week:** 2026-August-week3 · **Engineer:** Gemini Pro · **Reviewer:** Claude · **Owner:** Emmanuel
**Repo:** `/home/emmanuel/Documents/Scalable_Brain/scalable-brain`
**Venv:** `source /home/emmanuel/Documents/Scalable_Brain/.venv/bin/activate`

**Read `STATE.md` first, always.** It is the resume ledger — if a session was cut off by a
rate limit, it says exactly where to restart.

---

## 1. What this builds and why

Today there are **three strategy universes and nothing joins them**:

```
LEGACY 10                    V2 RESEARCH (43)              REGIME-AWARE PORTS (9)
integer ids 1..10            string ids "kiss_h4"          string ids
a hardcoded Python list      v2_harness.discover()         src/regime_aware/strategies/
      │                             │                             │
BacktestEngine (v1)           PositionEngine                BacktestEngine (v1)
      │                             │                             │
fact_trade_outcomes           results/research/*.json       fact_regime_trial_outcomes
      │                          (ends here)                   (ends here)
attribution → vet → map
      │
serialize → publish_model_set → GCS latest.json → System 2
```

Only the left column reaches a model set. The other 52 strategies have **no route at all** —
`publish_model_set.py` packages the existing bundle and reads its map from `vet.py`, which
builds only from `fact_strategy_regime_attribution`. Naming a research strategy a champion
is not a flag we forgot to set; **no command exists that does it.**

**This task builds that door.** One door, governed, auditable, reversible.

Scoping reference: `docs/design/systems/CONTRACT_V2_AND_POSITION_ENGINE.md` §11.3, which
lists the nine gaps. This folder is that section becoming work.

---

## 2. The owner's decision that shapes the design

> "We would carefully choose the best strategy regardless and publish it."

The owner intends to publish a strategy that **does not pass the gates**. That is a
legitimate call — it is a practice account and the goal is forward evidence — but it must
not be done by weakening the gates, because every future measurement is calibrated against
them and a softened gate silently re-labels the whole history.

**So the design requirement is: publishing an unqualified strategy must be possible,
explicit, and permanently recorded — never silent, never a side effect.**

Concretely, a strategy in the map carries one of:

| `selection_basis` | meaning |
|---|---|
| `qualified` | cleared every gate in `vetting/gates.py` on OOS trades. Nothing else earns this. |
| `designated` | **a human chose it despite failing gates.** Requires a recorded reason, the gate failures it carries, and the human's name. |

`designated` is not a lesser flavour of qualified. It is a different claim, and the manifest
must carry the failures so no downstream consumer — or future reader — can mistake one for
the other. System 3 sizes on this; it must be able to size a `designated` strategy
differently, or refuse it.

**Do not weaken `gates.py`. Do not add a "soft gate". Do not make the threshold
configurable.** The gates keep meaning exactly what they mean today.

---

## 3. Hard constraints

1. **One promotion path.** `FIX-S1-009` made the orchestrator the single governed writer of
   the champion bundle. Extend that path; do **not** add a second writer. If the design
   seems to need one, stop and ask.
2. **Publish ordering is sacred:** upload → SHA256 verify → **only then** flip the pointer.
   Superseded pointer archived to `previous.json`.
3. **`status` and `qualification_run_id` stay mandatory** on every published artefact
   (agreed with System 2, 2026-08-15). A consumer rejects on missing/unreadable/unknown.
4. **OOS-only metrics.** Folds come from `src/system1/validation/walk_forward.py` — that
   module, never a reimplementation. Two fold implementations is how OOS stops being OOS.
5. **Only `regime_causal`.** Never `regime_smoothed` — it leaks the future.
6. **Nothing is published live without the owner's explicit sign-off**, recorded in
   `STATE.md` with a timestamp. A ledger entry claiming a sign-off that did not happen has
   occurred once already; it must not happen again.
7. **Dry-run is the default** on every promotion-capable command.
8. No new files at the repo root (`STRUCTURE.md`).

---

## 4. Task map

| Task | What | Est. | Blocks |
|---|---|---|---|
| **P0** | Unified strategy registry — every strategy, one view, stable integer ids | 4–6 h | everything |
| **P1** | Outcome persistence for v2 strategies, with real OOS provenance | 4–6 h | P2 |
| **P2** | Attribution + vetting over the whole universe | 3–4 h | P3 |
| **P3** | `selection_basis`, the map schema bump, and the designation command | 4–5 h | P5 |
| **P4** | Gatekeeper cold-start policy for a strategy with no history | 2–3 h | — |
| **P5** | **The live signal producer** — the missing link; nothing trades without it | 6–8 h | go-live |
| **P6** | Transport (Pub/Sub) + a rehearsed withdrawal drill | 3–4 h | go-live |

**P5 is the one that decides whether System 2 can trade at all.** Everything else makes a
model set *correct*; P5 makes it *act*. `ScoredSignalProducer` exists and has no caller;
System 2 deleted its own `live_signal_producer/` on 2026-08-02 at System 1's request
(commit `b3b0abc`). Right now no component in any of the three systems emits a signal.

---

## 5. Required reading

| # | Document | Why |
|---|---|---|
| 1 | `CONTRACT_V2_AND_POSITION_ENGINE.md` §11 | The nine gaps, and why the door was deliberately not built until now |
| 2 | `docs/design/REGIME_STATE_AND_HOW_TO_RUN.md` | Which regime label is fit for routing and which two are not |
| 3 | `docs/design/STRATEGY_EXPERIMENT_STANDARD.md` | The eight rules any claim must survive |
| 4 | `docs/comms/S1-NOTICE-2026-08-15.md` §2, §5 | What System 2 has been told, and the two mandatory fields |
| 5 | `task/2026-August-week3/regime-aware/STATE.md` | The trial: what was measured, and the null result |

---

## 6. What "done" looks like

A single command promotes a named strategy — legacy, v2 or regime-aware port — into a
published model set, with:

- a stable integer id and a recorded string↔int mapping
- OOS metrics computed by the shared fold module
- `selection_basis` of `qualified` or `designated`, with failures attached if designated
- direction and exits in the map, so System 2 never has to infer them
- `status` and `qualification_run_id` present
- SHA256-verified upload, pointer flipped last
- one documented command to undo it, exercised in a drill before it is needed

and a signal producer that turns that model set into scored signals on the queue.
