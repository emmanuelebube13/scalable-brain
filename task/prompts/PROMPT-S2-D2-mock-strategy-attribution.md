# Agent prompt — D2: mock strategy names are attached to real P&L in the live trade blotter

**Run this in the System 2 repo** (the one that owns the telemetry dashboard and its API).

**Priority: P0 — do this first.** A dashboard attributing real money to strategies that do not
exist is worse than an empty dashboard, because a reader cannot tell which rows are real.

**Owner:** System 2 · **Source:** `docs/comms/to_system2/TO-SYSTEM2-3-2026-09-03-dashboard-reconciliation-and-mock-data.md` §D2

> **⚠ Read `PROMPT-S2-D0-where-to-work.md` first.** There are two dashboard apps in that repo
> and one renders nothing. The live one is **`telemetry-dashboard/src/App.tsx`** (loaded via
> `index.html` → `src/main.tsx`). **Do not edit `src/App.jsx`, `src/screens/*.jsx` or
> `src/main.jsx`** — they are dead, and `CONNECTIONS.md` documents the dead app.
>
> **Especially relevant here:** you are about to grep for `Momentum_Breakout`. It will almost
> certainly hit **both** trees. Fixing only the `.jsx` copy changes nothing on the deployed page
> and will look like the mock data is regenerating itself. **Check the extension on every hit,
> and confirm your fix by what the live page renders — not by what the grep no longer returns.**

---

## The problem

The **Live Trades (last 10)** table on the Live Telemetry overview attributes **nine of ten
rows** to a strategy named **`Momentum_Breakout`**, each at a flat **65.0%** confidence, with
real dollar P&L attached:

```
17:45:15  EUR_USD  Momentum_Breakout  65.0%  Closed    -$0.08
11:15:36  USD_CAD  Momentum_Breakout  65.0%  Closed     $0.00
11:15:32  GBP_USD  Momentum_Breakout  65.0%  Closed     $0.00
08:15:31  EUR_USD  Unattributed (opened outside ledger)  Approved  -$210.42
11:15:31  EUR_USD  Momentum_Breakout  65.0%  Closed     $0.00
03:00:33  USD_CAD  Momentum_Breakout  65.0%  Closed  -$174.72
03:00:33  AUD_USD  Momentum_Breakout  65.0%  Closed  -$132.00
03:00:33  GBP_USD  Momentum_Breakout  65.0%  Closed  +$422.00
03:00:32  EUR_USD  Momentum_Breakout  65.0%  Closed  -$134.64
15:41:24  EUR_USD  Momentum_Breakout  65.0%  Closed  -$201.73
```

## `Momentum_Breakout` does not exist

Verified three independent ways in the System 1 repo on 2026-09-03:

| Check | Result |
|---|---|
| `dim_strategy` table | 67 registered strategies. **No match.** Nearest real names: `h4_box_breakout` (id 20), `kpl_donchian_breakout` (29), `demark_fractal_breakout` (16), `vshape_swing_breakout` (54) |
| System 1 source tree | **No occurrence** in any `.py` file |
| This week's signal ledger | Three distinct strategies emitted: `xard_ma_cross_daily_open` (58), `nnfx_backtrader` (36), `liquidity_grab_fade` (30) |

**This is the third notice on this specific name.** `PROMPT-gemini-telemetry-strategy-section.md`
(2026-08-24) stated:

> `Momentum_Breakout`, `Mean_Reversion`, `Regime_Adaptive`, `Trend_Following`,
> `Volatility_Breakout`, `Statistical_Arbitrage` … **None of those strategies exist. They are
> invented names.**

`TO-SYSTEM2-3-2026-08-23-telemetry-ui-fixes.md` §3 separately asked for legacy mock data to be
stripped from the frontend.

**What has changed is the severity, not the finding.** Previously these names rendered
confident zeros on a strategy breakdown page. They are now labelling rows in a live trade
blotter with real money against them.

## What we could not determine, and you must

System 1 cannot see your execution records. **We do not know whether these are real trades
wearing a wrong label, or fabricated rows.** Two observations to start from:

- Timestamps `11:15:31`, `11:15:32`, `11:15:36` fall on System 1's hourly cron minute (`:15`),
  which is suggestive of **real events with wrong attribution**.
- Timestamps `03:00:32`, `03:00:33` match **no System 1 cadence**. Our crons run at `:15`
  hourly, `22:30` weekdays, `02:00` Tue–Sat, `05:40` and `06:00` daily.

**Determine which before you fix anything.** The two cases need opposite fixes:

- **Real trades, wrong label** → fix the attribution join. Do not delete the rows.
- **Fabricated rows** → delete the component per the 2026-08-23 guidance.

## The one row that reconciles

`08:15:31 EUR_USD · Unattributed (opened outside ledger) · Approved · −$210.42` matches
`UNREALIZED P&L −$210.41` and `LIVE POSITIONS 1`, sourced `oanda:openTrades`. **The only row on
the table we can confirm as honest is the one labelled unattributed.** Whatever produces that
row is doing the right thing; extend that behaviour rather than replacing it.

## What to change

1. **Find the source of the string `Momentum_Breakout`** in the dashboard/API codebase. Search
   for the full mock set — `Momentum_Breakout`, `Mean_Reversion`, `Regime_Adaptive`,
   `Trend_Following`, `Volatility_Breakout`, `Statistical_Arbitrage`. They travel together.

2. **If the trades are real:** attribute each row to the strategy that actually produced the
   signal. The authoritative mapping is `strategy_key` in the System 1 signal ledger, joined on
   `signal_id`. If a trade has no matching ledger row, label it **`Unattributed (opened outside
   ledger)`** — the pattern already in use on this very table.

3. **If the rows are fabricated:** delete the component. Per
   `TO-SYSTEM2-3-2026-08-23-telemetry-ui-fixes.md` §3 — *"If a visual feature relies on mock
   data and has no backing real-time data from System 1's bundle, remove the component from the
   view entirely rather than faking it."* An empty blotter is correct and safe.

4. **Never hardcode strategy names.** When System 1 publishes a new model set or changes the
   map, the page must reflect it on the next refresh with no code change and no redeploy.

5. **Never default a missing strategy name to a plausible-looking one.** This is the same class
   of defect as the zero-imputation issue raised in the 2026-08-23 message §4: a missing value
   rendered as a confident value. Render "Unattributed" or an explicit unknown state.

## Acceptance criteria

- [ ] The strings `Momentum_Breakout`, `Mean_Reversion`, `Regime_Adaptive`, `Trend_Following`,
      `Volatility_Breakout`, `Statistical_Arbitrage` appear **nowhere** in the shipped bundle.
- [ ] Every row in Live Trades either names a strategy present in System 1's ledger, or is
      explicitly labelled unattributed.
- [ ] No row displays a confidence value that did not come from a real `model_score`. (See D3 —
      the flat 65.0% and the `AVG CONFIDENCE 0.650` tile share this root cause and resolve
      together.)
- [ ] With an empty trade set, the table renders an intentional empty state, not mock rows.
- [ ] You have stated, in writing, whether the nine rows were real-with-wrong-labels or
      fabricated. System 1 needs that answer to close its side of the audit.

## Where the data lives

| Object | Path | Use |
|---|---|---|
| Signal ledger | `gs://scalable-brain-artifacts/telemetry/signals/<YYYY-MM-DD>/<ts>-<sha8>.ndjson` | `signal_id` → `strategy_key` attribution |
| Live strategy map | root `latest.json` → `artifacts[]` where `name == "regime_strategy_map.json"` → `.path` | which strategies are live at all |

**Ledger caveats you must know before you build against it:**

- Each object holds **only rows appended since the previous upload**, not a growing file.
  Reconstruct a day by concatenating that day's objects in lexical order.
- There is currently **no index or pointer object** — discovery needs a prefix LIST. System 1
  owns closing that gap (their D8); tell them if you build the LIST path so their index does
  not break you.
- **Absence of a ledger row is not evidence a trade was not ours.** System 1 discards some
  candidates before a `signal_id` is minted, so they leave no row.

Read access to bucket `scalable-brain-artifacts` is required. Credentials are not in this file.
