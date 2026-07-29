# T3 — Promotion Sign-Off Evidence

**Prepared 2026-07-29 · Nothing has been promoted. The live pointer is untouched.**

You are being asked one question: **should the candidate bundle replace the live one?**

My recommendation is at the bottom. Read §4 first if you want the short version.

---

## 1. What was actually run

A full gated evaluation on post-T1 data — the real `hmm_regime` → `attribute` → `vet` →
gatekeeper pipeline, then the real `deployment_gates()` against the real live incumbent read
from GCS. Promotion was **not** called.

> **Deviation from the T3 prompt, and why.** T3 step 3 says run
> `orchestrator --force`. That command *promotes* whenever the gates pass — there is no
> dry-run flag. RUN-ALL's hard boundary says the champion is promoted only after you say
> "promote". I started the forced run, then killed it mid-HMM before it reached the publish
> stage, cleared the stale lock, and verified nothing had been promoted
> (`retrain_state.json` still reads `2026-07-26T00-27-51Z-b48f48d3`). The evidence below
> comes from an equivalent non-promoting path.

Raw output: `results/state/t3_evidence_20260729.json`, `logs/t3_evidence_20260729.log`.

## 2. The four deployment gates — all PASS

| Gate | Candidate | Threshold | Verdict |
|---|---:|---:|---|
| `regime_accuracy_ok` | **0.965** | ≥ 0.70 (absolute floor) | **PASS** |
| `non_empty_map` | **4** qualified entries | ≥ 1 | **PASS** |
| `oos_uplift_ok` | **0.03767**, bootstrap-significant | ≥ 0.0 **and** significant | **PASS** |
| `beats_incumbent` | **0.965** | ≥ 0.931225 (live 0.965 × 0.965 tolerance) | **PASS** |

Incumbent: `2026-07-26T00-27-51Z-b48f48d3`, **resolution `prefixed`** — see §3, this is the
first time that has ever happened.

## 3. Two gate defects found and fixed (this is the session's real output)

### FIX-S1-012 — the regression gate has never once bound

`build_storage()` read `os.environ` with a `local` default, and `scheduler.orchestrator`
never loads `.env`. So `_incumbent()` has been reading the **local `model-artifacts/` tree
instead of GCS** on every real retrain, finding no `system1/latest.json` there, logging
`NO INCUMBENT FOUND`, and taking the documented fail-open branch.

**All three 2026 promotions were therefore never compared against their predecessor:**

| Retrain | `regime_accuracy` | incumbent seen | `beats_incumbent` |
|---|---:|---|---|
| 2026-07-01 | 0.717 | `None` | fail-open |
| 2026-07-19 | 0.8603 | `None` | fail-open |
| 2026-07-26 | 0.965 | `None` (`resolution: absent`) | fail-open |

This is exactly the producer/consumer divergence FIX-S1-007 and FIX-S1-010 were written to
close. The abstraction was correct; the configuration was never loaded. A *worse* model could
have taken the live pointer at any point and nothing would have stopped it.

Fixed: `build_storage()` now loads `.env` itself (explicit env still overrides, so CI is
unaffected). The incumbent now resolves `prefixed` with `regime_accuracy: 0.965` — visible in
the gate evidence above.

### FIX-S1-011 — the ratchet

**The `0.965` named in the task prompt is not a configured factor.** It does not exist
anywhere in the code. It is the `regime_accuracy` of the live 2026-07-26 bundle, misread as a
threshold constant.

The real gate was a bare `candidate_accuracy >= incumbent_accuracy` — no tolerance at all.
Because each promotion republishes the challenger's own accuracy as the next baseline, the
baseline could only ever climb: a high-water mark over a *noisy* estimate, which converges on
the luckiest draw ever observed and then blocks everything behind it, including genuinely
better models that happened to sample lower. The baseline had already climbed
**0.717 → 0.8603 → 0.965** in three promotions.

Combined with FIX-S1-012, the next retrain would have been the first to enforce it —
against a 0.965 bar.

Fixed: the challenger must now stay within `BEATS_INCUMBENT_TOLERANCE = 0.965` of the
**currently live** incumbent, so the bar tracks what is live rather than the best ever seen
and can fall as well as rise. Downward drift stays bounded by the absolute 0.70 floor.

**Note for honesty:** under the *old* bare `>=` rule this particular candidate would also
have passed (0.965 ≥ 0.965, exactly equal). The fix changed no decision today; it prevents a
future lock-out.

## 4. What promotion would actually change: almost nothing

| | Live (2026-07-26) | Candidate (2026-07-29) | Δ |
|---|---:|---:|---:|
| `regime_accuracy` | 0.965 | 0.965 | 0.000 |
| `oos_uplift` | 0.03891 | **0.03767** | **−0.00124** |
| qualified entries | 4 | 4 | 0 |
| qualifying strategy | `Range_Stochastic_Divergence` | same | — |

The strategy map is **structurally identical** — same 4 entries, same single strategy, same
granularities (Trending-Up @H1, Trending-Down @H1, Ranging @H1+H4). No cell was gained or
dropped. Per-cell metric changes are in the second decimal and split both ways: Ranging@H1 and
Trending-Up@H1 improved slightly, Ranging@H4 and Trending-Down@H1 declined slightly.

**The candidate's OOS uplift is marginally worse than the incumbent's** (−3.2% relative). The
orchestrator's `beats_incumbent` compares only `regime_accuracy`, so this does not block
promotion — but you should know it before deciding.

High-Vol still has **no qualifying strategy at all** in either map, and the entire model is
still one strategy. Findings A (weight starvation), B (regimes don't discriminate) and C
(concentration) are unchanged by this candidate.

## 5. Status of the seven fixes T3 lists

| Fix | Current doc status | Reflected in the live 2026-07-26 bundle? |
|---|---|---|
| S1-001 metrics sanity bounds | IMPLEMENTED, pending promotion sign-off | Yes |
| S1-002 true-OOS gate | VERIFIED (log-only) | Yes |
| S1-004 weight collision | VERIFIED (log-only) | Yes |
| S1-005 causal regime labels | VERIFIED (log-only) | Yes |
| S1-006 fail-closed uplift gate | VERIFIED (log-only) | Yes |
| S1-009 single governed writer | IMPLEMENTED 2026-07-05 | Yes |
| S1-010 calibration / manifest honesty | Implemented, nothing promoted | Partly — `GATEKEEPER_AUTOPROMOTE` still off |

**T3's premise is out of date.** It says "the live champion and strategy map still reflect the
pre-fix world". They do not: the 2026-07-26 bundle was produced by the already-fixed pipeline.
What the live bundle *does* reflect is **stale trade outcomes** — it was built while
`fact_trade_outcomes` had been frozen since 23 June. The candidate is the first bundle built
on genuinely current data (T1's repair).

That is the honest case for promoting: **same numbers, but honestly measured.**

## 6. `GATEKEEPER_AUTOPROMOTE` — recommendation, not a decision

**Leave it off.** It is off now and nothing in this session changed that.

Recommended criteria before arming it, in order:
1. `beats_incumbent` demonstrated **actually binding** on at least one real retrain — i.e. a
   retrain log showing `incumbent_resolution: "prefixed"` with a real comparison. Until
   FIX-S1-012 landed today this had never happened, so there is no track record yet.
2. **Three consecutive clean weekly retrains** with the T4 heartbeat green throughout.
3. A deliberate decision about the **+4.4pp approval-rate jump** the recalibrated gatekeeper
   brings (17.2% → ~21.6% per FIX-S1-010) — that is a real change in trade volume for
   Systems 2 and 3 to absorb, and it should not ride along silently with a routine retrain.

## 7. Recommendation

**I do not think you should promote today, and it is a close call.**

For promoting: the candidate is the first bundle measured on non-stale trade data, all four
gates pass honestly, and it carries no regression in the map.

Against: it is not better. Its OOS uplift is slightly *worse*, its accuracy is identical, and
its map is structurally identical. Promotion would consume a pointer flip and a version to
buy nothing measurable, while adding one more untested change on the same day two gate
defects were fixed.

The stronger play is to let the **next scheduled Sunday retrain** (2026-08-02) be the first
run where `beats_incumbent` genuinely binds, with the heartbeat watching. If that candidate
clears the gates on a real comparison, promote it with a track record behind the gate rather
than on the same day the gate was repaired.

**If you disagree — say "promote" and I will run it through the orchestrator, verify the GCS
pointer flip and `previous.json` archive, and confirm the SHA256 verify preceded the flip.**
That path is ready; nothing about it is blocked.
