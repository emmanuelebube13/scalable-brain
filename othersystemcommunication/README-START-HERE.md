# Measurement & Analytics Work Packages — START HERE

Created 2026-07-16 from the operator's seven measurement questions. Each file in this
folder is a **self-contained agent prompt**. Run them independently; order below.

## How to run each one

| # | File | Run WHERE | Depends on | What you get |
|---|---|---|---|---|
| 1 | `EXEC-012-trade-close-tracking.md` | **This machine** (System 2 repo) | nothing | 🚨 CRITICAL FIX: broker-side SL/TP closes flow back to System 3 (yesterday all 6 closes were missed; ledger was hand-repaired from broker records — see prompt for the incident) |
| 2 | `S1-EXPORT-002-strategy-analytics.md` | **Computer 1 / System 1** (scalable-brain repo) | nothing | System 1 publishes the strategy catalog, per-trade backtest returns, and trade-frequency stats to GCS so this machine can consume them |
| 3 | `TELEM-002-strategy-profile-screen.md` | **This machine** | #2 improves it (works partially without) | "Strategy" screen on the telemetry dashboard: profile, qualification, pairs, style, live-vs-backtest health |
| 4 | `SIM-001-profitability-simulator.md` | **This machine** | **#2 required** | "Simulator" screen: yearly return estimate, Monte-Carlo equity bands, user deposit amount, compounding toggle, recurring deposits |
| 5 | `S1-HANDOFF-2026-W31.md` | **This machine** + the **VM** | nothing | 🚨 **START HERE for the 2026-W31 handoff.** Everything System 2 / System 3 / the VM must implement after System 1's fix sprint: two position-sizing unit bugs (one **breaches the hard risk cap**), the jammed sizing gate, the phantom-position divergence, the VM code that has no source control, and which GCS pointer you should be reading. Includes ready-to-apply patches + tests. |

To start one: open a fresh Claude Code session in the stated repo and paste the file's
contents (or reference the file) as the task. For #2, give the file to the System 1
operator/agent — instructions for them are at the top of that prompt.

> **2026-07-29 — read #5 first.** `S1-HANDOFF-2026-W31.md` supersedes the operating picture
> below in three places: the live account has now taken **10 trades and lost all ten**
> (profit factor 0.0, lifetime −15,934.81 CAD); the sizing gate is **jammed shut** and that jam
> is currently the only thing preventing further loss; and two position-sizing unit bugs were
> confirmed, one of which **breaches the hard risk cap by 27% on GBP-quoted crosses**. The
> qualification numbers in the snapshot below are still accurate — they are backtest priors,
> and the gap between them and the live result is the open question.

## Answers snapshot (2026-07-16, from live data — the screens will keep these fresh)

1. **Strategy profile:** ONE qualified strategy — #10 `Range_Stochastic_Divergence`
   (stochastic-divergence range-fade). Variants: `@H1` (active in Trending-Up,
   Trending-Down, Ranging) and `@H4` (Ranging only, portfolio weight 8e-08 ⇒
   effectively off). 72 candidate variants were evaluated; 68 failed the gates.
2. **Qualification gates (walk-forward 2016→2026, anchored, 14 folds, OOS ≥60 mo):**
   PF ≥1.5, Sharpe ≥0.8, MaxDD ≤25%, WinRate ≥40%, RecoveryFactor ≥3. Per-regime OOS:
   Ranging PF 2.94 / Sharpe 3.80 / WR 73% (335 trades); Trending-Down PF 3.24 / 2.58 /
   77% (117); Trending-Up PF 1.84 / 1.01 / 65% (79). High-Vol: deliberately NO trading.
3. **Pairs:** watchlist 8 (EUR_USD GBP_USD USD_JPY USD_CHF AUD_USD USD_CAD NZD_USD
   EUR_GBP) — **effectively tradeable 3**: EUR_USD, GBP_USD, AUD_USD
   (= USD-quoted ∩ S2 `TRADEABLE_INSTRUMENTS` ∩ S3 conversion-rate capable).
   NZD_USD needs one line in `.env.system2`; crosses need an S3 rates source.
4. **Trading style: day-trade to short swing.** H1 bar signals; SL = 1×ATR(H1)
   (~8–14 pips), TP = 3×ATR (~25–40 pips); max hold 48 h; flat over weekends;
   no High-Vol entries. Typical hold observed: 1.5–6 h. NOT positional.
5. **How you'll know it's profitable:** (a) S3's own ledger — `trade_journal`,
   `equity_curve`, `daily_summary` tables; (b) the built-in **stage system**: paper
   stage graduates to micro only after ≥50 trades, ≥45% win rate, ≥4 weeks with ≥2
   profitable weeks and zero hard circuit-breakers — "the system works" ⇔ it advances
   stages; (c) live win-rate/expectancy vs the backtest priors per regime (TELEM-002
   screen); (d) day 1 reality: 6 trades, 6 stop-outs, −$2,808 (−3.2%) — every loss
   was ≈0.5% as designed; sample far too small to judge.
6. **Trade frequency:** signals are evaluated every closed H1 bar per pair; trades
   happen when the gate approves AND margin allows (~3 concurrent max at current
   sizing). Trading window: Sun ~17:00 → Wed 15:00 Atlantic (≈70 H1 bars/wk).
   Observed day 1: **6 trades in one day**. Realistic: ~3–10 trades/day inside the
   window, zero Thu–Sat. Precise distribution comes from SIM-001 + S1 data.
7. **Yearly profit rate + deposit simulation:** cannot be honestly computed from data
   on this machine (we have per-regime PF/WR but not the per-trade return series or
   frequency-per-pair mapping). That's exactly what **S1-EXPORT-002 → SIM-001**
   deliver: Monte-Carlo yearly return distribution (not a single misleading number),
   with user deposit, compounding on/off, and recurring monthly deposits.

## Daily health check-in (until stable)

Quick list, ~2 minutes: ① Telegram digest arrived 18:00 Atlantic; ② S3
`http://127.0.0.1:8300/state` — mode/state sane, no stuck positions; ③ S2
`http://127.0.0.1:8002/signal` — signals_today > 0 on trading days, heartbeat age
< 5 min; ④ hosted dashboard fresh; ⑤ `ams.log` — last reconcile line says
"no divergence"; ⑥ open trades on OANDA match S3's book count.
