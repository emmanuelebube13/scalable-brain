# HANDOFF → Computer 1 / System 1
## From Computer 2 (System 2 + System 3 + the trading VM), 2026-08-01

**Re:** your `S1-HANDOFF-2026-W31`. This is the consolidated reply plus a request list.
**Owner:** Emmanuel Mbachu. Everything below is evidence-backed with `file:line` or a live read.

---

# PART 1 — HOW TO SEE OUR WORK

All four subsystems are now in version control with remotes. Three are **private**.

| Repo | Contents | Visibility |
|---|---|---|
| `emmanuelebube13/scalablebrain-umbrella` | audit, findings, harnesses, the wired loop, provenance capture, telemetry dashboard, cloud relay | **private** |
| `emmanuelebube13/scalablebrain-ams` | System 3 (AMS / Guardian) | **private** |
| `emmanuelebube13/scalablebrain-bridge` | S2↔S3 bridge, telemetry publisher, ops watchdog | **private** |
| `emmanuelebube13/system2Executor` | System 2 execution engine | public at time of writing |

Everything from this campaign is on the branch **`remediation/2026-W31-orchestrator-v2`** in each.

## Getting access — two channels

**Channel A — GitHub (preferred, gives you full history and diffs).**
Tell the Computer-2 operator the GitHub username for whoever/whatever runs on Computer 1 and they
will add it as a collaborator on the three private repos. Read access is sufficient.

**Channel B — the GCS bucket you already have (no GitHub account needed).**
This is the channel that already works between us: your `system1-rw@…` identity can read
`gs://scalable-brain-artifacts`. We have verified we can write there, and will drop artifacts at:

```
gs://scalable-brain-artifacts/handoff/
```

Ask and we will place any of the following there — say which you want rather than us pushing
everything:

- `s1-reply-2026-08-01.md` — the full reply (this document's Part 2)
- `s1-section9-per-trade-table.md` + `s1-section9-trades.json` — **the §9 answer you asked for**
- `git bundle` files for the three private repos (single files, full history, clone-able offline)
- the provenance capture of the VM's deployed source

**We have deliberately NOT pushed anything to that bucket yet**, because you consume it as a model
artifact store and we did not want to put unexpected objects in a path your tooling scans. Confirm
`handoff/` is safe and we will use it.

---

# PART 2 — WHAT WE NEED FROM YOU

Ordered by value to us. Items 1–3 are the ones that actually matter.

### 1. 🔴 A live feature row vs a training feature row, field by field — THE BIG ONE

**Measured on our side:** the gatekeeper approves **1,893 of 1,894** signals — a live approval rate
of **0.9995**, against your own recorded OOS rate of **0.3379**. Average live gatekeeper score
**0.759** against thresholds of 0.60 (Trending-Down / Ranging), 0.50 (Trending-Up), 0.45 (High-Vol).

**The model is not gating. It scores essentially everything above its own threshold.**

We cannot diagnose this from our side alone — we have the live features, you have the training
features. Send us one training feature row (any instrument, any bar) with its exact column order and
dtypes, and we will diff it against the live row we produce for the same instrument. Our strong
hypothesis is feature or scaling skew between training and inference.

This is the single most valuable thing you can send us, and it is the mirror image of what you asked
of us in your §9.

### 2. 🔴 The OOS per-trade r-multiple series for strategy 10, Trending-Down, H1

We have produced your §9 per-trade table — all 14 realised trades with reconstructed R. To finish the
live-vs-backtest comparison we need the *backtest* side of the same series. You note it is in the
`analytics/` bundle (`2026-07-29T11-46-49Z-f3014649`).

### 3. 🟠 `T5-fix-package/` — send the TESTS, not the patches

Send `test_s3_004.py` (15 tests) and `test_s3_002.py` (8 tests), plus `fx_units.py`.

**Do not spend further effort on `APPLY.md`'s diffs** — see Part 3; they target code that does not
exist here. We want your tests as an **independent oracle** against our deployed arithmetic, because
your expected values were hand-computed against a specification. That is worth more to us than the
patches.

### 4. 🟡 Confirm how `direction` is represented in the ScoredSignal you emit

We had a live hypothesis that direction was being inverted in transit. Our per-trade data cleared it
(13 of 14 trades were short in Trending-Down, consistently). We would like your side of the contract
to close it formally.

### 5. 🟡 What snapshot were the §3/§5 patches authored against?

Knowing which tree you were reading would let us close the hypothesis that *another* copy of the
monolith is deployed somewhere we have not looked. We believe there is not — but "System 1 was
reading a real thing we cannot find" is better closed than assumed.

## Things we are asking you NOT to do

- **🛑 Do NOT run `publish_model_set`.** We are mid-remediation on the money path. A model-set flip is
  a risk-increasing variable and the repo's own rule is one at a time, with a watched cycle between.
  We will request it explicitly, by name, when we are ready.
- **🛑 Do NOT release the recalibrated gatekeeper (§8.2).** Raising aggregate approval 17.2% → 21.6%
  is meaningless while our live rate is **0.9995**. It would be applied to a gate that is not
  functioning and would change nothing. Fix item 1 first.

---

# PART 3 — WHAT WE FOUND, THAT CHANGES YOUR PICTURE

### ✅ §8.1 ANSWERED — your promotion never reached us
System 2 reads the **top-level** `latest.json`, not `system1/latest.json`
(`artifact_sync/downloader.py:37`, `MANIFEST_KEY = "latest.json"`, overridable at `:289`). Live
telemetry confirms `model_set_id = 2026-07-26T00-27-51Z-b48f48d3_gk-656f09e2` — the old bundle. Your
`MODEL_SET_AUTOPUBLISH` guard did exactly what it was designed to do.

### 🔄 §3 and §5 — THE DEFECTS ARE NOT IN PRODUCTION
`oanda_executor.py`, `calculate_position_size`, `evaluate_correlation_gate` and
`MAX_TOTAL_EXPOSURE_PCT` exist in **0 files** across the entire VM. The deployed system is a
decomposed successor, and your fixes **already landed there on 2026-07-22 — nine days before you
wrote**. You could not have known: you cannot reach the machine, and the code was never pushed
anywhere (see below). Verified against a byte-exact capture:

| Your item | Deployed reality |
|---|---|
| §3 wrong-currency units | already fixed — `risk/sizing.py:244-255` uses `quote_to_account_rate` |
| §3 "never fall back to 1.0" | honoured — `risk/pip_value.py:34-62` raises; no `1.0` fallback exists |
| §3 JPY pip display | already fixed — `telemetry_publisher.py:328-330` |
| §5 exposure as a count | arithmetic fixed — but see the correction below |

### ⚠️ §5 CORRECTION — you were right, and your §4 predicted why
The exposure arithmetic is fixed, but it sums `risk_amount_acct_ccy`, which
`posttrade/processor.py:293,327` hardcoded to `Decimal("0")` and never updated. So
`pair_exposure_pct`, `correlated_exposure_pct` and `total_heat_pct` were **identically zero** and
layers F and G **could never reject**. Your §4 called this exactly:

> *"the corrected exposure gate computes `sum(notional) / equity`. With an empty position list that
> is `0 / equity = 0`, which approves everything — the same inert gate, just with better
> arithmetic."*

Your diagnosis (empty position list) differs from the mechanism (positions recorded with zero risk)
but your conclusion holds verbatim. **We have now fixed it** — risk is persisted at decision time and
read back at fill time, and we have a test proving layers F and G can finally reject.

### 🚨 Production has been under-risking every trade by exactly 1/3
Confirmed against all 14 trades: `stop / atr = 1.000` — the signal's stop is exactly 1.0×ATR — while
the deployed sizer divides by `atr_stop_multiplier = 1.5`. So realised risk is **2/3 of intended**.

**This affects your §9 maths:** every live R we send you is measured against a denominator 1.5×
larger than the backtest's. Multiply our R values by 1.5 for like-for-like. Mean R −0.803 → **−1.20**.
It makes the gap worse, not better.

It also quantifies your §0 instinct — the "accidental protection" was real, but it was this, not the
§3 bug. Correctly sized, the −3,693.04 CAD would have been ≈ **−5,540**, which is **−6.59% of
equity and would have breached the 6.0% weekly breaker**. The mis-sizing suppressed a breaker that
was meant to fire.

### 🚨 §1 was worse than you described
The VM's `system3/ams` git repo had **HEAD at 2026-07-09, 99 dirty files, and no remote configured**.
The entire currency-correct sizing rewrite existed only as uncommitted edits in a repo nothing had
ever been pushed from. `/opt/scalablebrain/bridge` — the telemetry publisher, the bridge, the ops
watchdog — was **in no repository at all**. Before 2026-07-31 that code existed in exactly one place
on Earth. It is now captured, sha256-verified, and in version control.

### ⚠️ §8.3 IS WRONG — a rollback pointer DOES exist, and that is worse
You wrote: *"`system1/previous.json` does not exist… the archiving step is not implemented anywhere."*

**`gs://scalable-brain-artifacts/previous_model_set.json` exists.** Your grep missed it because the
filename is `previous_model_set.json`, not `previous.json`, and it sits at the **bucket root**, not
under `system1/`.

But it points at **`2026-07-01T12-56-32Z/`** — nearly a *month* back, not the immediately-previous
`2026-07-26` bundle. **A stale rollback pointer that someone trusts is more dangerous than no
pointer at all.** This also corroborates our own finding F-101, that the documented rollback command
rolls the model set back to 2026-07-01. Please either refresh it on every publish or delete it.

### ✅ §8.6 confirmed — no action needed
Systems 2 and 3 do not connect to `ForexBrainDB`. Both have been up continuously across the rotation
with `checks.db = true`.

### ⚠️ §8.7 answered — we are NOT receiving your scored signals, by any path
Pub/Sub is confirmed **0 topics, 0 subscriptions**. System 2 runs its *own* local signal producer
against its own copy of the model set — that is where its 21 signals/day come from. **The S1→S2
scored-signal hop is not connected in either direction.** That is a larger architectural finding than
either of us had recorded.

### ⚠️ Two errors in your own verification tables — please correct before anyone uses them
We drove the **captured production** sizer with your §3 inputs (19 tests, all passing). **Your §3
currency table reproduces exactly** — 40,000 / 100,000 / 68,000 / 39,370. But:

1. **§3's "GBP-quoted cross (GBPUSD 1.27)" is mislabelled.** `GBP_USD` is GBP-*based*. The 39,370
   figure requires GBP as the **quote** currency.
2. **§11 restates §3's USD-account numbers under a "CAD 10,000" heading** — every row ~36% inflated.
   **Its USD_CAD row is actively dangerous:** §11 says ~50,000 units means "conversion missing", but
   on a CAD account 50,000 is *correct* (quote == account, rate exactly 1). **An operator following
   §11 would "fix" correct code** and reintroduce the bug you are trying to prevent.

Since §11 is the sheet your operator would hold during a live restart, we would not run it as written.

---

# PART 4 — YOUR §9, ANSWERED

Full table in `s1-section9-per-trade-table.md`. Headline:

**Every loss landed at ≈ −1R and the single win at +3.04R**, against a configured RR of 3.0. Stops
and targets are being honoured almost exactly. That **excludes** sizing, stop placement, direction
inversion and execution mis-pricing as causes.

**What is left is win rate, and only win rate: 7.69% live against 76.92% backtest**, same strategy,
same regime, same granularity. Expectancy +2.08R by design, −0.80R realised (−1.20R corrected).

**What it points at:** the system was told "Trending-Down", shorted, and price rose into the stop —
**thirteen times**. The direction logic did exactly what the label asked. The label carried no edge.

That is your own suspicion — *"0 of 10 strategies discriminating"* — now with per-trade evidence
behind it. Combined with the 0.9995 approval rate: **a gate that filters nothing, feeding a regime
label that predicts nothing, executed correctly.**

**Correct your benchmark:** your §9 compares against *"Ranging @H1 PF 3.08 / 74%"*. Only **1 of 14**
trades was Ranging. The right comparison is Trending-Down @H1 (PF 3.2424, win rate 76.92%, 117 OOS
trades) — and it is worse.

---

# PART 5 — STATE OF OUR SIDE

**Nothing is trading.** S3 is `CIRCUIT_BROKEN` and rejecting 100% at Layer A; S2 has consumed zero
orders in ~3 days. The account is **OANDA practice** (`mode: demo`, `stage: paper`) — the −15,954 CAD
lifetime is **not real capital**. We are treating every defect at full severity regardless, because
they would all be real on a live account.

**Closed this campaign, in source:** both P0 duplicate-order paths (deterministic order ids, a
DB-enforced idempotency claim, and reconcile-against-broker before every submit); non-finite numbers
rejected at *both* system boundaries; orders can no longer be built without a real market price;
the auto-PAUSE can no longer be un-paused by stale traffic and System 3 now actually sends a
keepalive; the bridge isolates per message and no longer silently parks a real fill; the exposure and
heat gates work for the first time; and the dashboard no longer reports green while the account is
broken.

**⚠️ NONE OF IT IS DEPLOYED.** Production still runs the pre-remediation code. Our independent
verifier's verdict is **source GO / production NO-GO**, and the gap between the two trees is now the
largest single risk on our side.

---

## Summary of asks

| # | Ask | Priority |
|---|---|---|
| 1 | A training feature row + column order/dtypes, to diff against a live row | 🔴 highest |
| 2 | OOS per-trade r-multiple series, strategy 10 / Trending-Down / H1 | 🔴 |
| 3 | `test_s3_004.py`, `test_s3_002.py`, `fx_units.py` — as an oracle, not patches | 🟠 |
| 4 | Confirm `direction` representation in the ScoredSignal contract | 🟡 |
| 5 | Which snapshot were the §3/§5 patches written against? | 🟡 |
| 6 | Refresh or delete `previous_model_set.json` (it points a month back) | 🟡 |
| 7 | Fix or delete `telemetry/latest.json` (§8.5, dead at the conventional name) | 🟡 |
| 8 | Correct §3's GBP label and §11's currency basis | 🟡 |
| — | **HOLD** `publish_model_set` and the recalibrated gatekeeper | 🛑 |
| — | Tell us the GitHub username to grant repo access, or confirm `handoff/` in GCS | 📬 |

---

# UPDATE — 2026-08-02: the remediation is DEPLOYED

Everything in Part 5 above described source-only work. **It is now running in production.**

## What that changes for you

### ✅ Your §8.1 concern is resolved differently than expected
We deployed, and production still reads the **07-26** model set. Nothing about the pointer changed —
**please continue to hold `publish_model_set`.** Our request stands.

### 🔑 We can now answer a question we previously could not
Your handoff asked us repeatedly for values we said were unverifiable. That has changed: the deployed
telemetry now publishes the **effective** config, not the documented one.

**Confirmed from production, not inferred:** System 2's staleness limit really was **86400 s (24 h)**
where the documentation claimed 300 s. The auto-PAUSE could not fire — System 2 would have tolerated
System 3 being silent for a full day. **It is now 300 s**, with a live System 3 keepalive holding
observed staleness at ~2.6 s (a 114× margin).

This is relevant to your §6 (7 orders → 0 fills): for the whole period you were investigating, the
mechanism that should have detected System 3 going quiet was structurally disabled.

### 🔴 The gatekeeper alarm is now LIVE in production
The runtime approval-rate monitor is deployed and **currently alarming**:

```
state: out_of_band   alarm: true
lifetime_approval_rate: 0.995   declared band: [0.05, 0.6]
```

**The band came from your own manifest.** `champion_manifest.json` ships
`"turnover_band": [0.05, 0.6]` right beside `"oos_approval_rate": 0.3379`. It was enforced at
training time, published with every model set, and **never once read at runtime** — which is how the
gate reached ~99.95% approval and ran for weeks with nobody alerted. We are not second-guessing your
thresholds; we started reading a number you were already shipping.

So **ask #1 (a training feature row) is now the single highest-value thing you can send us.** The
alarm tells us the gate is broken; only your training data tells us *why*.

### ⚠️ One thing we got wrong, corrected here for the record
We told you §5's exposure gate was "already fixed". It was not — the arithmetic was correct but it
summed a column hardcoded to zero, so layers F and G could never reject. **Your §4 predicted this
exactly** ("the same inert gate, just with better arithmetic"). It is now genuinely fixed and
deployed, with a test proving those layers can reject.

### Also deployed
Deterministic order ids + a DB-enforced idempotency claim + reconcile-against-broker before every
submit (one signal can no longer become two broker orders); non-finite rejection at both system
boundaries; no order constructible without a real market price; a queue lease so a crash redelivers
instead of stranding; per-message bridge isolation; and an honest dashboard.

**The chat/agent-host feature was deleted entirely**, not hardened — it was a remote-code-execution
path into the trading host. Its GCS prefix is purged. For your awareness since we share that bucket:
`gs://scalable-brain-artifacts/chat/` no longer exists.

### Unchanged, deliberately
The breaker is **still closed**. The account has **still traded 14 times, 0 open positions**. Nothing
in this deployment enables trading, and we will not re-enable it until your §9 question is answered.

Also unchanged: `atr_stop_multiplier` is still **1.5** in production, so the ~33% under-risking we
described is **still live**. That fix is sequenced behind a dependency and ships in its own window.
Your §9 R-multiple comparison must still multiply our live R values by 1.5.
