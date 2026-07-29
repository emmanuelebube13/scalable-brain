# T5 — De-risk the Money Layer · Technical Report

**Date:** 2026-07-29 · **Status:** COMPLETE (fix package) · **BLOCKED** (VM capture — one
command for the user, §1)

Fix package: `task/2026-W31/T5-fix-package/` — 23 tests green, red-before evidence captured.
Nothing was applied to any live system; `OtherSystems/` is untouched.

---

## 1. VM capture — BLOCKED, and exactly how to unblock it

**This machine cannot reach the VM.** Measured, not assumed:

| Probe | Result |
|---|---|
| `~/.ssh/config` | does not exist |
| `gcloud compute instances list` | `Required 'compute.instances.list' permission for 'projects/scalable-brain'` → 0 items |
| Active gcloud identity | `system1-rw@scalable-brain.iam.gserviceaccount.com` — an artifact-storage service account with no compute scope |
| `deployment-guide/` at repo root | does not exist (it lives at `../OtherSystems/deployment-guide/`, outside this repo) |
| System-3 reference copy | `../OtherSystems/system-3-account-management/` contains **only `docs/` and `tasks/`** — no source |

So the Layer-5 sizing gate and telemetry publisher still exist **only on the VM, with no
version-controlled source**. That is unchanged by this task and remains the largest
unmitigated risk in the money layer: if that machine is lost, the code that sizes real
positions is lost with it.

### The unblocking action — run this on the VM (< 5 minutes)

```bash
# On the VM:
cd /  # adjust to wherever the sizing gate + telemetry publisher live
tar czf /tmp/layer5-capture-$(date +%Y%m%d).tgz \
    <path-to-sizing-gate> <path-to-telemetry-publisher>
sha256sum /tmp/layer5-capture-*.tgz          # record this
hostname; pwd; date -u                        # record for PROVENANCE.md
```

Then either upload it to a bucket path this machine's service account can read, or copy it
across by hand, and place it at `live-vm-capture/layer5-sizing/`. Once it lands, the pristine
capture should be committed **as-is first** (unreviewed), then a second commit adding the
README — so the captured state is preserved separately from any interpretation of it.

---

## 2. The two unit-confusion defects — both present in THIS repo

Neither defect had to be reconstructed from docs. The retired Layer-4/Layer-7 code that
became System 2/3 is still in this tree, and both defects are verbatim:

| Fix | File | Line | Defect |
|---|---|---:|---|
| S3-002 | `src/layer4_executor/live_pipeline.py` | 1108–1112 | `total_exposure = len(open_positions)`; `>= MAX_TOTAL_EXPOSURE_PCT * 10`; `exposure_pct = total_exposure / 10` |
| S3-004 | `src/layer7/oanda_executor.py` | 246 | `units_decimal = risk_capital / sl_distance` |
| S3-004 | `src/layer7/oanda_executor.py` | 402 | `pip_distance = sizing.sl_distance * Decimal('10000')` |

### S3-004 — wrong vs right, side by side

```python
# WRONG — units of (account ccy) / (quote ccy per unit).
# Correct ONLY when quote currency == account currency.
units = risk_capital / sl_distance

# RIGHT — convert the per-unit risk into account currency first.
risk_per_unit_account = sl_distance * quote_to_account_rate
units = risk_capital / risk_per_unit_account          # ROUND_DOWN
```

The invariant being enforced: `units × sl_distance × quote_to_account_rate ≤ risk_cap`.

Measured consequences for a 10,000 account at 2% (cap 200) — every number computed by
`fx_units.py`, the same code the tests pin:

| Instrument | Unpatched units | Actual risk | Error | Corrected units |
|---|---:|---:|---:|---:|
| EUR_USD (quote = account) | 40,000 | **200.00** | 0.0% | 40,000 |
| USD_JPY (quote JPY @150) | 666 | **1.33** | **−99.3%** | 100,000 |
| USD_CAD (quote CAD @1.36) | 50,000 | **147.06** | −26.5% | 68,000 |
| EUR_GBP cross (quote GBP, GBPUSD 1.27) | 50,000 | **254.00** | **+27.0%** | 39,370 |

Only the USD-quoted pair is coincidentally correct. **The cross-pair case does not merely
under-size — it breaches the hard risk cap outright.** See `sizing_error_magnitude.png`.

The `* 10000` pip display is a related symptom of the same blindness: on a JPY-quoted pair a
0.30 stop is 30 pips, not 3,000.

### S3-002 — wrong vs right, side by side

```python
# WRONG — a COUNT compared to a percentage through a fabricated *10 bridge.
total_exposure = len(open_positions)
if total_exposure >= MAX_TOTAL_EXPOSURE_PCT * 10:   # >= 2.5 -> fires at the 3rd position
    exposure_pct = total_exposure / 10              # 2 positions -> "0.2", any size

# RIGHT — a real fraction of equity.
exposure_pct = sum(units * entry_price * quote_to_account_rate) / account_equity
```

The defining test: **a $1,100 book and a $110,000 book both report `0.2`.** Two maximal
positions are 2,200% of equity and the unpatched gate approves them, because it never looks at
size. A count cap is preserved as its own explicitly-named `MAX_CONCURRENT_POSITIONS` so
behaviour is never weaker than today.

---

## 3. Red-before / green-after evidence

`RED-BEFORE.txt` (captured output of `red_before_evidence.py`, exit 1):

```
INVARIANT 1 — realised risk at stop must equal the 200 cap
  [PASS] EUR_USD  200.00  (+0.0%)
  [FAIL] USD_JPY    1.33  (−99.3%)
  [FAIL] USD_CAD  147.06  (−26.5%)
  [FAIL] EUR_GBP  254.00  (+27.0%)
INVARIANT 2 — reported exposure must track notional, not count
  [FAIL] $1,100 book -> 0.2 | $110,000 book -> 0.2   (identical)
  [FAIL] true exposure 22.00x equity, legacy reports 0.2 and APPROVES
INVARIANT 3 — pip distance must respect pip size
  [FAIL] USD_JPY 0.30 -> legacy reports 3000 pips (100x)
6 invariant(s) FAILED against the unpatched code.
```

Green-after: `pytest task/2026-W31/T5-fix-package/ -q` → **23 passed**, covering a USD-quote
pair, a JPY-quote pair (2-decimal pips), a CAD-quote pair and a cross, with every expected
value hand-computed in the test docstring and every assertion naming its currency.

---

## 4. S3-006 — the finding that reframes this entire task

Full note: `T5-fix-package/S3-006-ROOT-CAUSE.md`. The headline:

> **10 realised trades, all losers. Profit factor 0.0. Expectancy −367.37 CAD/trade.
> Lifetime account P/L −15,934.81 CAD.**
>
> *"The gates described below are currently the only thing preventing further loss. Fixing
> them without first addressing why every trade loses would convert a stalled system into a
> reliably losing one."*

**Root cause of the lockout:** the gate needs `live_trades >= 20` from a window capped at 168
hours, but throughput is ~1 trade/day — so the window can hold at most ~7. **Unreachable by
construction.** Worse, the counter has been pinned at 9 since 07-20 (closing a trade is the
only thing that increments it, and opening one is gated behind it — a closed loop), and from
07-22 a second gate began rejecting the same population as `stale_live_stats`. The two gates
move in opposite directions: left alone, the system will never trade again.

**Recommendation: do not lower the threshold.** Treat it as a bootstrapping problem (seeded
warm-up window with a provenance flag), assert at startup that the parameters are mutually
satisfiable, and emit a distinct `gate_structurally_closed` signal. A gate that cannot open is
a configuration error, not a risk control.

**S3-006 Finding 4 is the live instance of S3-004:** sizing ran with `account_ccy: "USD"`
against a **CAD-denominated** account for three days (07-20 → 07-22 02:00 UTC), corrected only
by an incidental restart. Nothing asserts that sizing currency matches the broker's reported
account currency — which is why a P1 went unnoticed for three days.

**Finding 5 corroborates System-1 work:** `telemetry/latest.json` froze at 2026-07-18 with all
payloads `null` while `latest-vm.json` stayed current. T4's heartbeat already reads
`latest-vm.json` and confirmed on 2026-07-29 that the publisher is alive.

---

## 5. Triage of S3-001 / S3-003 / S3-005

Full detail in `T5-fix-package/TRIAGE.md`. Summary:

| Fix | Severity | Call | Why |
|---|---|---|---|
| S3-001 gates blind to open positions | P1 | **before S3-002** | `open_positions` is empty in production, so the corrected exposure gate computes `0/equity = 0` and stays inert. S3-002 cannot deliver value until this lands. |
| S3-003 Kelly inert + stale edge | P1 | next week | The cap always wins, so Kelly never influences a bet. Do **not** "activate" it — measured live edge is negative; an active Kelly on a hardcoded positive win rate would size *up* into a losing system. |
| S3-005 auditor entry-bar leakage | P2 | next week | Pre-fill price action can decide WIN/LOSS. Corrupts retraining data — same class as the causal-label leakage FIX-S1-005 fixed on this side. Cheap to fix. |

Recommended order: S3-006 Finding 4 (currency assertion) → S3-004 → S3-001 → S3-002 →
S3-006 Finding 2 (zero fills) → S3-003 / S3-005.

---

## 6. What the user must do, in order

`T5-fix-package/HANDOFF.md` is the paste-ready session. Condensed:

1. Add the `sizing.account_ccy == broker.account_summary.currency` assertion (5 min).
2. Apply S3-004 per `APPLY.md`; verify a USD_JPY signal now sizes ~150× larger.
3. Populate and reconcile `open_positions` from the broker (S3-001).
4. Then apply S3-002.
5. **Do not** unblock the lockout in the same session — that is a strategy decision.
6. Run the VM capture command from §1 so the sizing code finally exists in version control.

**Production sanity check:** for a 10,000 account at 2%, a USD_JPY position should be in the
**tens of thousands** of units. If it is in the **hundreds**, the fix is not live.

---

## 7. Acceptance criteria status

- [x] VM capture — **BLOCKED**, with a precise <5-minute instruction (§1)
- [x] S3-002 + S3-004 patches with red-before/green-after tests incl. JPY 2-decimal pip and cross-pair unit assertions
- [x] S3-006 root-cause note; S3-001/003/005 triaged
- [x] `HANDOFF.md` is a paste-ready Computer-3 session
- [x] `OtherSystems/` untouched; no live system touched from this machine

## 8. Follow-up this task surfaced

**The defective code is still in `src/layer4_executor/` and `src/layer7/` in this repo**, not
only in `archieved/`. CLAUDE.md marks those layers retired, but the live-looking copies remain
importable and are what a future reader will find first. T7 (archive/cleanup) should decide
whether they are deleted or clearly tombstoned — leaving two copies of known-defective sizing
code in the tree invites someone to fix the wrong one.
