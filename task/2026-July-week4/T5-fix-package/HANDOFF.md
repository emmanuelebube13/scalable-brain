# HANDOFF — Computer 3 session checklist

Everything in this folder was produced on Computer 1 (System 1). **Nothing here has been
applied to any live system.** This is the paste-ready session for the machine that runs
System 3.

---

## 0. Read this first — the sequencing decision

The live evidence (`S3-006-ROOT-CAUSE.md`) says the account has taken **10 realised trades,
all losers**: profit factor 0.0, expectancy −367 CAD/trade, lifetime −15,934.81 CAD. The
sizing gate that is currently locked shut is, right now, **the only thing preventing further
loss**.

The patches below make sizing **arithmetically correct**. They do not make the strategy
**profitable**. Correct sizing of a negative-edge strategy loses money *faster*, not slower.

So: **apply the correctness fixes, but do not unblock the lockout in the same session.**
Steps 1–4 are safe to do now. Step 5 is a strategy decision, not an engineering one.

---

## 1. Prevent recurrence of the currency defect (5 minutes, do this first)

S3-006 Finding 4: sizing ran in USD against a CAD account for three days and nobody noticed.

```python
# At startup AND on every broker reconnect:
account_ccy = broker.account_summary()["currency"]      # never default, never cache blindly
# On every sizing decision:
assert sizing.account_ccy == account_ccy, (
    f"sizing currency {sizing.account_ccy} != broker account currency {account_ccy}"
)
```

Reject the decision if they differ. This is the cheapest item here and it closes the exact
hole that hid a P1 for three days.

## 2. Apply S3-004 — risk cap in account currency

Follow `APPLY.md` §"S3-004". Take the `.bak` copies first.

```bash
pytest <your sizing tests> -v
```

**Verify by hand before letting it size anything real.** For a CAD account, a USD_JPY signal
with a 0.30 JPY stop should now produce roughly **150× more units** than before. If the number
did not move, the patch is not in the path being executed.

## 3. Prove the fix on the bench

```bash
# On Computer 1 these all pass; re-run them wherever you port the arithmetic.
cd task/2026-July-week4/T5-fix-package && pytest . -v      # 23 tests
python red_before_evidence.py                        # exits 1 — that IS the evidence
```

`RED-BEFORE.txt` is the captured failure output against the unpatched formulas: 6 invariants
fail, including USD_JPY under-risked by 99.3% and a cross pair **breaching** the hard cap by
+27%.

## 4. S3-001 before S3-002 — do not skip this order

`APPLY.md` §"S3-002" gives the exposure-gate change, **but it will still be inert until
`open_positions` is actually populated** (S3-001). An empty list makes
`sum(notional)/equity = 0`, which approves everything with better arithmetic.

```
a. Populate open_positions from the BROKER's position list each cycle
   (instrument, units, entry_price) — not from local state.
b. Reconcile against s2status.open_positions; on divergence, REJECT rather than
   proceed. S3-006 Finding 3: S3 believed it held 1 position while the broker held 0,
   and drawdown/exposure were being computed against that phantom.
c. Confirm prepare_broker_order no longer returns "units": None (live_pipeline.py:1282) —
   size must reach the gate.
d. THEN apply S3-002.
```

## 5. The lockout — a decision, not a patch

Do **not** lower `min_live_trades`. See `S3-006-ROOT-CAUSE.md`. The gate is arithmetically
unsatisfiable (20 required, ~7 possible in a 168h window) *and* it is currently protecting the
account. The engineering fix is a warm-up path with a provenance flag plus a startup assertion
that the parameters are mutually satisfiable — not a smaller number.

Answer first: **why did all 10 trades lose?**

## 6. Restart and verify in production

```bash
sudo systemctl restart <system3-service>
tail -f <logs> | grep -E 'sizing|units|exposure_pct|account_ccy'
```

### How to spot a wrong-units regression at a glance

For a **CAD 10,000** account at 2% risk (CAD 200 max risk per trade):

| Instrument | Stop distance | Correct units (order of magnitude) | Wrong-units symptom |
|---|---|---|---|
| EUR_USD | 0.0050 | **~40,000** | — (quote ≈ account, coincidentally right) |
| USD_JPY | 0.30 JPY | **~100,000** | **~666** ⇒ old bug still live (150× too small) |
| USD_CAD | 0.0040 | **~50,000** | ~68,000 ⇒ conversion applied twice or inverted |
| a GBP-quoted cross | 0.0040 | **~39,000** | ~50,000 ⇒ **over-risking, breaches the cap** |

**Rule of thumb: if a USD_JPY position is sized in the hundreds of units, the fix is not
live.** Correct sizing puts it in the tens of thousands.

Also confirm in telemetry:
- `account_ccy` matches the broker's `account_summary.currency` on **every** decision
- `exposure_pct` is a continuous number in [0,1], **not** a step function of 0.1/0.2/0.3
  (a step function means the count-based gate is still running)

## 7. Report back

Capture and send: the first 5 sizing decisions post-restart (instrument, stop distance, units,
account_ccy), plus `exposure_pct` for a 2-position book. Those numbers are enough to confirm
both fixes landed.

---

## What is NOT in this package, and why

- **No VM code capture.** This machine cannot reach the VM — see `DELIVERABLE.md` §1 for the
  exact command for you to run. The Layer-5 sizing gate and telemetry publisher still exist
  only on the VM, with no version-controlled source. **That remains the single largest
  unmitigated risk in the money layer**: if that machine is lost, the code that sizes real
  positions is lost with it.
- **No changes to `OtherSystems/`.** Verified clean; this machine did not touch System 2 or
  System 3 code.
- **S3-001, S3-003, S3-005** — triaged only, see `TRIAGE.md`.
