# S3-006 — live sizing-gate lockout · root cause and recommendation

**Source:** `docs/proposed-fixes/system-3/FIX-S3-006-live-sizing-gate-lockout-2026-07-22.pdf`
**Evidence window:** 2026-07-14 → 07-22 · OANDA practice `101-002-38449021-001` (**CAD**)

---

## Read this before fixing anything

The report's own financial context is the most important thing in this entire task:

> 10 realized trades, **all losers**. Profit factor **0.0**. Expectancy **−367.37 CAD/trade**.
> 30-day Sharpe **−11.49**. Cumulative **−3,673.68 CAD** over the window; lifetime account
> P/L **−15,934.81 CAD**. Guardian state `CAUTION` at 4.83% drawdown.
>
> *"The gates described below are currently the only thing preventing further loss. Fixing
> them without first addressing why every trade loses would convert a stalled system into a
> reliably losing one."*

**The lockout is not purely a bug. It is currently the only thing protecting the account.**
Every recommendation below is written to preserve that protection.

---

## Root cause of the lockout (Finding 1)

The sizing gate requires `live_trades >= min_live_trades (20)`, drawn from a live-stats
window capped at `max_stats_age_hours = 168` (7 days). Realised throughput is ~1 trade/day,
so a 168-hour window can hold **at most ~7 trades**. The threshold of 20 is therefore
**unreachable by construction** — not a tuning problem, an arithmetic impossibility.

It is worse than a stuck gate, because two gates now move in **opposite directions**:

- `live_trades` has been pinned at **9** since 2026-07-20. The only thing that increments it
  is closing a trade, and opening a trade is gated behind the counter. **Closed loop.**
- From 10:00 UTC on 07-22 a second gate began firing on the same population:
  `stale_live_stats`, `stats_age_hours 168.28 > max 168.0`.

Trades age *out* of the window faster than new ones can enter it, so `live_trades` will
decline from 9 toward 0 while the threshold stays at 20. **Left alone, the system will never
trade again.**

Rejection breakdown for 07-22 (96 decisions, all at `layer: "sizing"`):

| Outcome | Reason | Count | Account ccy |
|---|---|---:|---|
| REJECTED | `insufficient_live_stats` | 63 | CAD |
| REJECTED | `insufficient_live_stats` | 21 | USD |
| REDUCED | — | 7 | CAD |
| REJECTED | `no_conversion_rate` | 3 | USD |
| REJECTED | `stale_live_stats` | 2 | CAD |

## Recommendation

**Do not lower the threshold.** With profit factor 0.0 across 10 trades, opening this gate
re-enables a strategy with no demonstrated live edge. The gate is doing accidental good.

1. **Treat it as a bootstrapping problem, not a threshold problem.** A live-stats requirement
   a cold system cannot satisfy needs an explicit warm-up path — seed the window from
   backtested or paper statistics *with a provenance flag*, and require that flag to clear
   before real capital is committed.
2. **Make the parameters mutually consistent by construction.** Assert at startup that
   `min_live_trades` is achievable within `max_stats_age_hours` at the observed approval
   rate, and fail loudly if not. **A gate that cannot open is a configuration error, not a
   risk control.**
3. **Emit a distinct `gate_structurally_closed` telemetry signal** so this surfaces in
   minutes rather than days.
4. **Sequence the strategy question first.** Until there is a reason to believe the next 10
   trades will not also lose, unblocking the gate makes things worse, not better.

---

## The other three findings

**Finding 2 — approved orders are not becoming trades (P0, silent).** 7 orders published,
`trades: []`, broker reports `openTradeCount: 0`, `pendingOrderCount: 0`. They exist nowhere.
Same failure surface as FIX-S2-002 (broker return-contract mismatch). This *compounds*
Finding 1: orders that never become trades can never increment `live_trades`, so the lockout
cannot self-resolve.

**Finding 3 — S2/S3 disagree on open positions (P1).** S3 says `open_positions: 1`; S2, and
the broker, say zero. `reconciliation_divergence` = 6 against 529 snapshots. **The Guardian is
computing drawdown, exposure and state transitions against a position that does not exist**,
so its `CAUTION` verdict is not trustworthy — and neither is any correlation or exposure gate
reading position state (cf. FIX-S3-001). Also, `peak_equity` 88,294.53 is carried from outside
the retained series (which starts 07-19 at max 84,898.99), so the drawdown percentage cannot
be reproduced from published telemetry.

**Finding 4 — sizing ran in USD against a CAD account for 3 days (P1, corrected by restart).**
Every decision from 07-20 through 07-22 02:00 UTC used `account_ccy: "USD"` on a CAD-denominated
account; a restart at ~02:25 corrected it. **This is the live instance of FIX-S3-004** — the
same class of defect the patches in this package address. It went unnoticed for three days
because nothing asserts that sizing currency matches the broker's reported account currency.

> **Fix:** read account currency from the broker summary at startup **and on every reconnect**;
> never default it. Assert `sizing.account_ccy == broker.account_summary.currency` on every
> decision and reject if they differ.

**Finding 5 — telemetry aggregate 4 days stale (observability).** `telemetry/latest.json`
froze at 2026-07-18T22:50Z with every S2/S3 payload `null`, while `telemetry/latest-vm.json`
updates every few minutes with complete data. Any consumer reading the conventional filename
sees a dead system.

*System-1 status: already handled on this side.* The T4 heartbeat reads `latest-vm.json`
specifically and confirmed on 2026-07-29 that the VM publisher is alive. The stale
`latest.json` is System-2's to fix or delete — leaving a dead file at the conventional name
is a trap for the next reader.
