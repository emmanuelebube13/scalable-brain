# R5 — Documentation bundle

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Estimated time:** 2–3 hours · **Risk:** none — prose and diagrams only.
**Needs:** R0–R4 far enough along to describe honestly. Write it last.

**Read `STATE.md` first — it is the source of what actually happened, including failures.**

---

## Why this task exists

The owner asked for proper documentation of the regime-aware side: the models used, the
training, the sampling, parameter tuning, and everything that goes with it. This produces
it. It also produces the note that ships to Systems 2 and 3.

**Document what was built, not what was intended.** If R3 found nothing, say so in the first
paragraph. The value of this system's documentation has consistently come from it recording
the things that did not work — finding B, the pair-selection artifact, the look-ahead
disqualification. A write-up that reads like a brochure is worth less than nothing, because
someone will act on it.

---

## Deliverable 1 — `docs/design/REGIME_AWARE_MODEL.md`

The technical reference. Sections, at minimum:

### 1. What the regime-aware model is
The gate, not a re-tuning. `ParamBlock` per regime, `enabled` selects. Include the
continuous-indicator explanation — why indicators are computed over the full frame and each
bar selects its column, and what goes wrong if you segment instead.

### 2. The models used
- **D1 trend label** — `EMA(50)` vs `EMA(200)` on daily closes, `shift(1)`, warm-up
  `UNKNOWN`. **Nothing is fitted.** No training, no scaler, no version, no artifact. State
  this plainly — it is the main reason it was chosen.
- **HMM label** — 4-state Gaussian HMM, `LABEL_ORDER="trend_first"`, `CAUSAL_SMOOTHING=True`,
  `TAU_BY_GRANULARITY {D1:0.25, H4:0.25, H1:0.10}`, K-Means fallback below the 0.70 accuracy
  gate. Fitted, versioned, walk-forward refitted for the causal column.
- **Why D1 trend is the routing instrument and the HMM label is not.** Include the occupancy
  table from `README.md` §3. The H4 zeros must appear in this document.

### 3. Training and refitting
Only the HMM trains. Walk-forward, fold-fit, forward-only inference. Where the folds come
from (`src/system1/validation/walk_forward.py`, min_train 36mo / step 6mo / OOS 6mo,
anchored) and why two fold implementations would be a defect. The kappa figures and the
≥0.40 gate.

### 4. Sampling
How trades are attributed to folds, what counts as OOS, the point-in-time join of regime to
decision bar, and why the decision bar rather than the fill bar. The trade floor from R3 and
why a metric from 6 trades is not reported.

### 5. Parameter tuning — and why there was none
This week the arms differ **only** in `enabled`. No parameter or risk differences. Record
that explicitly, and record the reasoning: per-regime tuning multiplies the search space by
four against intervals that already straddle 1.0, and this project has already produced one
significant-looking result that was entirely an artifact. If tuning is ever added it must
happen inside the walk-forward **train** fold only.

### 6. The pre-registration
The R2 mask assignment protocol, its hash, and why declared-family assignment is a
hypothesis while performance-derived assignment is a fit.

### 7. Limitations
Everything that would let a future reader misuse this. At minimum: one week is not
statistical evidence; the HMM label is unusable as an H4 gate; nothing here is promoted to
live and the v2→live path does not exist; the number of comparisons run in R3.

---

## Deliverable 2 — `results/regime_aware/TRIAL_SUMMARY.md`

The plain-English account for the owner. What we did, what happened, what it means, what it
does not mean. One page. Lead with the honest headline, whatever it is.

---

## Deliverable 3 — the bundle for Systems 2 and 3

Assemble `task/2026-August-week3/regime-aware/notes-for-systems-2-3/` into something
sendable:

- `DASHBOARD-NOTE.md` — already drafted; update it against what R4 actually published
- the published artifact's contract (`contracts/regime-status-contract.json`)
- a short covering note: what is new, what they need to do, what they are **not** blocked on

Follow the house correspondence style in `docs/comms/` — those documents lead with a
"short version" numbered list and are explicit about what action is required from the
recipient and what is merely informational.

**Do not send anything.** Assemble it and tell the owner it is ready. Sending is the owner's
call.

---

## Definition of done

- [ ] `docs/design/REGIME_AWARE_MODEL.md` with all seven sections
- [ ] `results/regime_aware/TRIAL_SUMMARY.md`, one page, honest headline first
- [ ] Systems 2/3 bundle assembled, not sent
- [ ] Every claim traceable to a run recorded in `STATE.md`
- [ ] Limitations section written before anyone asks for it
- [ ] `STATE.md` updated

## What the reviewer will check

- That the documentation matches what the code does, not what the task file said it would
  do. Docstrings describing unbuilt behaviour is a recurring failure in this repo — a
  capability is verified by running it, not by reading about it.
- That failures recorded in `STATE.md` appear in the write-up.
- That the H4 occupancy zeros are present in `REGIME_AWARE_MODEL.md`.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
