# S1-HANDOFF-2026-W31 — What System 2 / System 3 / the VM must implement

## Instructions for the operator (read first)

**Run on: the OTHER computer** — the machine hosting System 2 (execution) and System 3
(guardian/AMS), and the VM running the Layer-5 sizing gate + telemetry publisher.

This is a handoff from **Computer 1 / System 1** after the 2026-W31 fix sprint. Everything
below was found, measured or fixed on the System-1 side between 2026-07-27 and 2026-07-29.
Full evidence lives in `scalable-brain/task/2026-W31/deliverables/` on Computer 1; the
ready-to-apply patches and tests live in `scalable-brain/task/2026-W31/T5-fix-package/`.

**Nothing in this note has been applied to any live system.** System 1 cannot reach your
machines: no SSH config, and its `gcloud` identity (`system1-rw@…`) is storage-only, so
`compute.instances.list` is denied. Every action below is yours to execute.

---

## 0. READ THIS BEFORE FIXING ANYTHING

From `FIX-S3-006` (2026-07-22 live telemetry audit), confirmed against the account ledger:

> **10 realised trades. All ten lost.** Profit factor **0.0**, expectancy **−367.37 CAD/trade**,
> 30-day Sharpe **−11.49**, cumulative **−3,673.68 CAD**, lifetime account P/L
> **−15,934.81 CAD**. Guardian state `CAUTION` at 4.83% drawdown.

The sizing gate is currently **jammed shut** by an arithmetic impossibility (§3). That jam is,
right now, **the only thing preventing further loss**.

**Consequence for the order of work below:** apply the *correctness* fixes (§1–§2, §4–§5), but
do **not** unblock the lockout in the same session, and do not "fix" it by lowering the
threshold. Correct sizing of a negative-edge strategy loses money **faster** — the mis-sized
yen positions have been accidentally limiting the damage.

The strategy question comes first. See §9.

---

## 1. 🚨 P0 — Capture the VM sizing code into version control (5 minutes)

**The Layer-5 sizing gate and telemetry publisher exist only on the VM, with no
version-controlled source anywhere.** If that machine is lost, the code that decides how much
real money to put at risk is lost with it. This is the single largest unmitigated risk in the
money layer and it is also the cheapest to close.

On the VM:

```bash
cd /                                   # adjust to where the sizing gate actually lives
tar czf /tmp/layer5-capture-$(date +%Y%m%d).tgz \
    <path-to-sizing-gate> <path-to-telemetry-publisher>
sha256sum /tmp/layer5-capture-*.tgz     # record this
hostname; pwd; date -u                  # record for PROVENANCE.md
```

Then either upload to a GCS path `system1-rw` can read, or copy it across by hand, and tell the
Computer-1 operator. It will be committed **as-is first** (pristine, unreviewed), then
documented in a second commit — so the captured state stays separate from any interpretation
of it.

---

## 2. 🚨 P0 — Assert the sizing currency matches the broker's account currency

**This already bit you.** `FIX-S3-006` Finding 4: every sizing decision from **2026-07-20
through 2026-07-22 02:00 UTC** ran with `account_ccy: "USD"` against an account denominated in
**CAD** (`account_summary.currency: "CAD"`). 192 decisions on 07-20, 193 on 07-21. It was
corrected by an incidental restart at ~02:25 UTC on 07-22 — **not by any alarm**. Nothing in
the system checks this.

```python
# At startup AND on every broker reconnect — never default, never cache blindly:
account_ccy = broker.account_summary()["currency"]

# On every sizing decision:
if sizing.account_ccy != account_ccy:
    reject(f"sizing currency {sizing.account_ccy} != broker account currency {account_ccy}")
```

Reject the decision on mismatch (default-safe posture: missing/divergent ⇒ REJECT). This is the
cheapest item in this document and it closes the exact hole that hid a P1 for three days.

---

## 3. 🚨 P0 — S3-004: the risk cap is computed in the wrong currency

**Scope:** `oanda_executor.py` → `calculate_position_size`, step 6 (was line ~246).

### The defect

```python
units = risk_capital / sl_distance     # WRONG
```

`risk_capital` is in **account currency**; `sl_distance` is a price difference, i.e. **quote
currency per unit**. Dividing them yields correct units only when quote == account. The loss at
stop is `units × sl_distance`, which is denominated in **quote currency**, and the code treats
it as account currency.

### Measured consequences — account 10,000 @ 2% (cap 200)

| Instrument | Unpatched units | Actual risk | Error | Correct units |
|---|---:|---:|---:|---:|
| EUR_USD (quote = account) | 40,000 | **200.00** | 0.0% | 40,000 |
| USD_JPY (quote JPY @150) | 666 | **1.33** | **−99.3%** | 100,000 |
| USD_CAD (quote CAD @1.36) | 50,000 | **147.06** | −26.5% | 68,000 |
| GBP-quoted cross (GBPUSD 1.27) | 50,000 | **254.00** | **+27.0%** | 39,370 |

**The cross-pair row is the one that matters.** This is not only an under-sizing bug — on
GBP-quoted crosses it **breaches the hard risk cap outright**, by 27%. The cap that is supposed
to be unbreakable is not.

### The fix

```python
if quote_to_account_rate is None or quote_to_account_rate <= 0:
    raise ValueError(f"no quote->account rate for {instrument}; refusing to size")
risk_per_unit_account = sl_distance * quote_to_account_rate
units = risk_capital / risk_per_unit_account          # keep ROUND_DOWN
```

**`quote_to_account_rate` must be fetched live, not hardcoded.** If unavailable, the sizer must
**refuse to size**. Do not fall back to `1.0` — that reinstates exactly this bug. For a CAD
account: EUR_USD → `1/USDCAD`… work each pair's quote→CAD conversion explicitly and assert it
is positive.

Also fix the pip display (was line ~402), which hardcodes 4-decimal pips and is **100× wrong**
for JPY-quoted pairs:

```python
pip_distance = sizing.sl_distance / pip_size(instrument)   # 0.01 for JPY-quoted, else 0.0001
```

### What you get from System 1

`task/2026-W31/T5-fix-package/` contains:

- `fx_units.py` — the unit-correct reference arithmetic (pure math, no I/O; a **specification**,
  not a library to import into production)
- `test_s3_004.py` — 15 tests, every expected value hand-computed in the docstring, each
  assertion naming the currency it asserts in
- `RED-BEFORE.txt` — the captured failure output: **6 risk invariants fail** against the
  unpatched formulas
- `APPLY.md` — exact diffs, order of operations, rollback commands

---

## 4. ⚠️ P1 — S3-001 **before** S3-002 (this order is not optional)

**S3-001:** `ExecutionPipeline.open_positions` is empty in production, so the correlation and
exposure guards evaluate against nothing and **can never reject**.

`FIX-S3-006` Finding 3 sharpens it: **S3 reports `open_positions: 1` while S2 and the broker
both report 0.** `reconciliation_divergence` = 6 against 529 snapshots. The Guardian has been
computing drawdown, exposure and state transitions against a **position that does not exist** —
so its `CAUTION` verdict is not trustworthy, and neither is any gate reading position state.

```
a. Populate open_positions from the BROKER's authoritative position list each cycle —
   instrument, units, entry_price — NOT from local state.
b. Reconcile against s2status.open_positions; on divergence, REJECT rather than proceed.
c. Confirm prepare_broker_order no longer returns "units": None (live_pipeline.py:1282) —
   today size never reaches the gate at all.
d. Only THEN apply S3-002.
```

**Why the order matters:** the corrected exposure gate computes `sum(notional) / equity`. With
an empty position list that is `0 / equity = 0`, which approves everything — the same inert
gate, just with better arithmetic. **S3-002 cannot deliver any value until S3-001 lands.**

---

## 5. ⚠️ P1 — S3-002: "25% portfolio exposure" is a position *count*

**Scope:** `live_pipeline.py` → `evaluate_correlation_gate` (was lines ~1108–1121).

### The defect

```python
total_exposure = len(open_positions)                  # a COUNT
if total_exposure >= MAX_TOTAL_EXPOSURE_PCT * 10:     # >= 2.5 -> fires at the 3rd position
    exposure_pct = total_exposure / 10                # 2 positions -> "0.2", ANY size
```

No position's size, notional or risk is ever summed. The `* 10` and `/ 10` are a fabricated
bridge between a count and a percentage.

**The defining test:** a **$1,100** book and a **$110,000** book both report `0.2`. Two maximal
positions are **2,200% of equity** and the gate approves them. Changing the constant from 0.25
to 0.40 would change the rule from "3rd position" to "5th position", not from 25% to 40% of
capital.

### The fix

```python
notional = sum(
    Decimal(p["units"]) * Decimal(p["entry_price"]) * quote_to_account_rate(p["instrument"])
    for p in open_positions
)
exposure_pct = notional / account_equity
if exposure_pct > MAX_TOTAL_EXPOSURE_PCT:
    reject(f"portfolio exposure {exposure_pct:.4f} exceeds cap {MAX_TOTAL_EXPOSURE_PCT}")
if MAX_CONCURRENT_POSITIONS is not None and len(open_positions) >= MAX_CONCURRENT_POSITIONS:
    reject(f"concurrent position count {len(open_positions)} at cap")
```

Add `MAX_CONCURRENT_POSITIONS = 3` as its **own explicitly named constant** so behaviour is
never *weaker* than today (today's effective rule is "reject the 3rd position") — but stop
overloading one percentage-named constant to mean two different things.

Tests: `test_s3_002.py`, 8 cases, in the same package.

---

## 6. 🚨 P0 — S3-006 Finding 2: approved orders are not becoming trades

**System 3 reports `orders_published_total: 7`. The day ledger shows `trades: []`. OANDA
reports `openTradeCount: 0`, `openPositionCount: 0`, `pendingOrderCount: 0`.**

Seven orders were published on 2026-07-22 and **none of them exists at the broker in any
state** — not open, not pending, not recorded as closed. Either publication is not reaching the
broker adapter, or fills are returning and being discarded. This is the same failure surface as
`FIX-S2-002` (live OANDA fills recorded as FAILED under a broker return-contract mismatch); this
is evidence it is still live or has recurred.

**This compounds the lockout:** orders that never become trades can never increment
`live_trades`, so the gate in §7 **cannot self-resolve**.

Please instrument the publish→fill path end to end and report where the seven orders went.

---

## 7. 🔒 DECISION, NOT A PATCH — the sizing-gate lockout (S3-006 Finding 1)

The gate requires `live_trades >= min_live_trades (20)` from a live-stats window capped at
`max_stats_age_hours = 168`. Realised throughput is **~1 trade/day**, so a 168-hour window can
hold at most **~7 trades**. **The threshold of 20 is unreachable by construction.**

Worse, two gates now move in **opposite directions**:

- `live_trades` has been pinned at **9** since 2026-07-20. The only mechanism that increments
  it is closing a trade, and opening a trade is gated behind the counter. **Closed loop.**
- From 10:00 UTC on 07-22 a second gate began firing on the same population:
  `stale_live_stats`, `stats_age_hours 168.28 > max 168.0`.

Trades age *out* of the window faster than new ones can enter. `live_trades` will decline from 9
toward 0 while the threshold stays at 20. **Left alone, the system will never trade again.**

### Recommended direction — do NOT lower the threshold

1. Treat it as a **bootstrapping** problem, not a threshold problem. Seed the window from
   backtested or paper statistics **with a provenance flag**, and require that flag to clear
   before real capital is committed.
2. Assert at startup that `min_live_trades` is **achievable** within `max_stats_age_hours` at
   the observed approval rate, and fail loudly if not. **A gate that cannot open is a
   configuration error, not a risk control.**
3. Emit a distinct `gate_structurally_closed` telemetry signal so this surfaces in minutes
   rather than days.

With profit factor 0.0 across 10 trades, opening this gate re-enables a strategy with no
demonstrated live edge. **The gate is doing accidental good. Sequence §9 first.**

---

## 8. What changed on System 1 that affects you

### 8.1 ⚠️ A new model bundle is live — but your pointer may not see it

| Pointer | Bundle |
|---|---|
| `gs://scalable-brain-artifacts/system1/latest.json` | **`2026-07-29T11-46-42Z-55dacdbf`** ← new |
| `gs://scalable-brain-artifacts/latest.json` (model set) | `2026-07-26T00-27-51Z-b48f48d3` ← **old** |

The orchestrator logged `top-level model set NOT refreshed (MODEL_SET_AUTOPUBLISH not set)` —
that guard is deliberate for staged rollout. **If you consume the model set, you are still on
the 26 July bundle.**

**❓ ACTION — please confirm which key System 2/3 actually reads.** System 1 does not know, and
it determines whether the promotion reached you at all. If you read the model set, the
Computer-1 operator needs to run `python -m src.system1.serializer.publish_model_set`.

What the new bundle contains (unchanged in structure): same 4 qualified entries, all
`Range_Stochastic_Divergence` — Trending-Up @H1, Trending-Down @H1, Ranging @H1+H4. High-Vol
still has **no qualifying strategy** — deliberately no trading there.

**Honest note:** the new bundle's recorded OOS uplift is **0.03649** vs the superseded bundle's
**0.03891** — about 6% lower. The promotion gate compares only `regime_accuracy`, so no gate
flagged it. It is not alarming, but you should know.

### 8.2 The gatekeeper champion is UNCHANGED

`GATEKEEPER_AUTOPROMOTE` remains unset by design. The recalibrated gatekeeper — which would
raise aggregate approval from **17.2% to ~21.6%** — has **not** been released. That is real
extra trade volume for you to absorb, and it will not arrive without a deliberate decision.
Tell Computer 1 when you are ready for it.

### 8.3 There is no rollback pointer, and there never was

`system1/previous.json` does not exist. `grep -rn 'previous.json' src/` returns nothing — the
archiving step documented in the publish contract **is not implemented anywhere**. Rolling back
means manually re-pointing `system1/latest.json` to `2026-07-26T00-27-51Z-b48f48d3`, which is
intact under its immutable prefix. Recoverable, but not one-click. Plan accordingly.

### 8.4 Analytics bundle refreshed

`system1/analytics/2026-07-29T11-46-49Z-f3014649` — strategy catalog, OOS per-trade r-multiple
series, frequency stats and regime occupancy. This is what TELEM-002 and SIM-001 consume. Built
from **134,407 trade outcomes now current through 2026-07-24** (they had been frozen at
2026-06-23 for five weeks — that is fixed; the numbers you pull are honest again).

### 8.5 ⚠️ `telemetry/latest.json` is dead and is a trap (S3-006 Finding 5)

`gs://scalable-brain-artifacts/telemetry/latest.json` froze at **2026-07-18T22:50Z** with every
S2/S3 payload `null`, while `telemetry/latest-vm.json` updates every few minutes with complete
data. **Any consumer reading the conventional filename sees a dead system.**

System 1's new daily heartbeat reads `latest-vm.json` specifically and confirmed on 2026-07-29
that your VM publisher **is alive**. But please either fix or **delete** `latest.json` — leaving
a dead file at the conventional name will mislead the next reader.

### 8.6 The DB password was rotated

The `ForexBrainDB` `sa` password was rotated on 2026-07-29 (it had been committed in 11 tracked
files since April). The Computer-1 operator confirmed **System 2/3 do not connect to that
database**, so no action is expected. **If that is wrong, tell Computer 1 immediately** — your
connections will be failing.

### 8.7 Scored signals still dead-end on Computer 1

`QUEUE_PROVIDER=local` — scored signals land in `results/state/queue/` on Computer 1, which you
cannot read. The three Pub/Sub topics (`Scored_Signal_Queue`, `AMS_Outbound_Queue`,
`AMS_Inbound_Queue`) are still unprovisioned. **❓ Please confirm whether you are currently
receiving scored signals by some other path, or whether this is the reason the live loop is
running on something else.**

---

## 9. ❓ The question System 1 cannot answer, and most wants answered

**Why did all ten trades lose?**

System 1's own analysis says the live model is **one strategy** and the regime classifier
**does not discriminate** between strategies (max win-rate spread 0.075 against a 0.10 bar,
0 of 10 strategies discriminating). Ten trades, ten losses is the empirical version of the same
problem.

The most valuable thing you can send back is the **live-vs-backtest gap per trade**: for each of
the 10 realised trades — instrument, regime at entry, entry/exit price, stop distance, units,
realised R — against what the backtest predicted for that same signal. The backtest says
Ranging @H1 has PF 3.08 / win rate 74%. Live says 0/10. **That gap is the most important
unknown in the whole system**, and it is measurable only on your side.

`EXEC-012` (trade-close tracking) is the prerequisite — if broker-side SL/TP closes are still
being missed, the ledger cannot answer this.

---

## 10. Recommended order of work

```
1. §1  VM capture                          5 min   — removes a single-point-of-loss
2. §2  currency assertion                  30 min  — closes the hole that hid a P1 for 3 days
3. §3  S3-004 risk cap in account ccy      2 h     — packaged + tested, ready
4. §6  why 7 orders produced 0 fills       ?       — blocks everything downstream
5. §4  S3-001 populate + reconcile         4 h     — unblocks S3-002
6. §5  S3-002 exposure as a fraction       2 h     — packaged + tested, ready
7. §8.1 confirm which pointer you read     5 min   — determines if the promotion reached you
8. §9  the live-vs-backtest gap            ?       — the actual question
9. §7  the lockout                         DECISION — not before §9
```

Triaged, not packaged (detail in `T5-fix-package/TRIAGE.md`): **S3-003** (Kelly sizing is inert
— the hard cap always wins, so Kelly never influences a bet; do **not** "activate" it, its edge
premise is empirically false) and **S3-005** (the auditor scans from the entry bar *inclusive*,
so pre-fill price action can decide WIN/LOSS — this corrupts retraining data, same class as the
causal-label leakage System 1 fixed in FIX-S1-005).

---

## 11. How to verify in production

After applying §3, for a **CAD 10,000** account at 2% (cap CAD 200):

| Instrument | Stop distance | Correct units | Wrong-units symptom |
|---|---|---:|---|
| EUR_USD | 0.0050 | ~40,000 | — (coincidentally right before) |
| USD_JPY | 0.30 JPY | **~100,000** | **~666** ⇒ fix is not live (150× too small) |
| USD_CAD | 0.0040 | ~68,000 | ~50,000 ⇒ conversion missing |
| GBP-quoted cross | 0.0040 | ~39,000 | ~50,000 ⇒ **over-risking, breaches the cap** |

> **Rule of thumb: if a USD_JPY position is sized in the hundreds of units, the fix is not
> live.** Correct sizing puts it in the tens of thousands.

Also confirm in telemetry:

- `account_ccy` matches the broker's `account_summary.currency` on **every** decision
- `exposure_pct` is a **continuous** number in [0,1] — **not** a step function of 0.1 / 0.2 /
  0.3, which would mean the count-based gate is still running

**Please send back:** the first 5 sizing decisions post-restart (instrument, stop distance,
units, `account_ccy`) and `exposure_pct` for a 2-position book. Those numbers are enough for
Computer 1 to confirm both fixes landed.

---

## 12. Evidence index (on Computer 1)

| What | Where |
|---|---|
| Ready-to-apply patches, tests, rollback | `task/2026-W31/T5-fix-package/` (`APPLY.md`, `HANDOFF.md`) |
| S3-006 full root cause, all 5 findings | `task/2026-W31/T5-fix-package/S3-006-ROOT-CAUSE.md` |
| S3-001 / S3-003 / S3-005 triage | `task/2026-W31/T5-fix-package/TRIAGE.md` |
| Red-before failure output | `task/2026-W31/T5-fix-package/RED-BEFORE.txt` |
| Sizing-error magnitude chart | `task/2026-W31/deliverables/T5/sizing_error_magnitude.png` |
| Promotion evidence + gate results | `task/2026-W31/deliverables/T3/` |
| Week overview | `task/2026-W31/deliverables/WEEK-EXECUTIVE-SUMMARY.md` |
