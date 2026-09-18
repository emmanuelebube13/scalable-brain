# Brief for external agent (Gemini) — dashboard observability: signal diagnostics, honesty chips, trade replay, alerts wiring

Issued 2026-09-18. A Claude session reviews, lands, and deploys this work; **do not push, publish, commit, or deploy anything yourself**. You work in the working tree only. Your output is edited files plus a written report.

---

## 0. The single most important instruction

**Honesty over completeness.** On this dashboard, *absent renders absent*. No `COALESCE(x, 0.5)`, no `|| 0`, no defaulted direction, no invented placeholder number. A confident wrong number is worse than a blank panel — this rule exists because the current Notifications bell shows a hardcoded "0 ACTIVE" with no data source behind it, which is exactly the failure you are being hired to remove, not repeat. If a data source doesn't exist, render "n/a" / "unavailable" and write the gap in your report.

## 1. Ground rules (binding)

1. **Two repos are in scope.** Say which one you are in at all times:
   - `work/scalablebrain-umbrella/` — the live telemetry dashboard (React/Vite frontend at `telemetry-dashboard/`, FastAPI Cloud Run backend at `cloud/telemetry-web/`). Most of your work is here.
   - `scalable-brain/` — System 1. Only Tasks 6a and 7a touch it.

   Before writing any code, read `work/scalablebrain-umbrella/CLAUDE.md` (its "Writing instructions for agents" section binds you) and `scalable-brain/CLAUDE.md` + `scalable-brain/STRUCTURE.md`. Their rules override anything here that conflicts.

2. **Files you may create or edit — and nothing else:**

   In `work/scalablebrain-umbrella/`:
   - `cloud/telemetry-web/main.py` (only to add the `/api/alerts` GCS-cached endpoint, Task 6b)
   - `cloud/telemetry-web/routes/signals.py`, `cloud/telemetry-web/routes/trades.py`
   - New files under `cloud/telemetry-web/services/` (do not edit existing services except where a task names one)
   - New `cloud/telemetry-web/test_*.py` files and additions to existing ones
   - `telemetry-dashboard/src/components/assets/` (`AssetChartPanel.tsx`, `chartApi.ts`, `chartMath.js` + `chartMath.d.ts`, `riskRewardPrimitive.ts`, new files in this folder)
   - `telemetry-dashboard/src/components/views/Assets.tsx`, `telemetry-dashboard/src/components/views/Trades.tsx`
   - `telemetry-dashboard/src/components/layout/TopBar.tsx` (only the notifications dropdown, Task 6c)
   - New files under `telemetry-dashboard/src/components/ui-custom/` (follow the existing pattern there: pure display logic in a `.js` + `.d.ts` pair so it is unit-testable)
   - `telemetry-dashboard/src/connection.js` (minimal additions only — this is the single module that talks to the services; do not restructure it)
   - New tests under `telemetry-dashboard/src/__tests__/`

   In `scalable-brain/`:
   - `src/monitoring/alert_bridge.py` and `src/monitoring/tests/test_alert_bridge.py` (Task 6a only)
   - `src/analytics/assets.py`, `src/analytics/publish_analytics.py` and their tests (Task 7a only)
   - Your report file (see §9)

3. **Do NOT touch:** `telemetry-dashboard/src/App.jsx` (stale legacy — the live root is `App.tsx`), anything under `telemetry-dashboard/src/components/ui/` (generated shadcn primitives), `vite.config.js` / `vite.config.ts`, `cloud/telemetry-web/static/` and `telemetry-dashboard/dist/` (build outputs — the reviewer builds at deploy time), `cloud/telemetry-web/migrations/` (no schema changes in this brief), `shared/notforyou/` (legacy layer-5 app), `.agents/`, `services/db_client.py`, `routes/market.py`, `routes/commands.py`, anything in `work/scalablebrain-bridge/`, and any file on `trading-1` — the production VM is entirely out of scope.

4. **Prohibitions:** no database writes (SELECT only, through the existing helpers `execute_to_records` / `table_columns`); no GCS writes; no Pub/Sub; no crontab edits; no git commits or pushes; no `gcloud` commands; no network calls in tests (fake/monkeypatch everything); no regex- or script-based bulk patching of source files — edit by hand and run `python -m py_compile` (or `ast.parse`) on every Python file you touch, then check you have not introduced duplicate `def`s.

5. **Standing invariants (restated every brief):** never enable `go_live_enabled`, never issue `mode enforce`, never place/modify/cancel a broker order, never auto-remediate. Nothing in this brief needs any of those.

6. **SQL rules:** column aliases in raw SQL must stay double-quoted (unquoted aliases fold to lowercase and silently break the Pydantic mapping — this caused the 2026-09-06 every-asset-default-regime incident; see the comments at `services/layer1_client.py` L24–28). `strategy_id` is a string on the wire and in `ams_decision_log` but INTEGER in `s1_scored_signals_log` — cast explicitly on any join.

7. **Toolchain:** Python via the venv at `/home/emmanuel/Documents/Scalable_Brain/.venv`. Backend tests: run `pytest` **from `cloud/telemetry-web/`** — the full suite must stay green. Frontend: `npm test` (node native tests) must stay green and `npm run build` (which runs `tsc -b`) must pass — but do not copy the build output anywhere. `black` on any `scalable-brain/` Python you touch.

8. **Evidence, not claims.** "It works" means: you ran the test/endpoint and you paste the actual output and counts in your report. Where a task depends on live data shapes, the required fixtures are named in the task; if a shape you need is not observable from the repo (fixtures, migrations, tests), do not guess — render "unknown", skip that field, and record the gap in your report under "Blocked / needs owner decision".

9. **Independence:** each task stands alone. If one is blocked, skip it, say why, and continue with the others.

## 2. What this system is (one paragraph)

A three-system algorithmic FX pipeline: System 1 (research/signals) publishes artefacts to GCS bucket `gs://scalable-brain-artifacts`; System 2 executes; System 3 supervises. The dashboard is a Cloud Run FastAPI app (`cloud/telemetry-web/`) serving a built React SPA, reading (a) a GCS telemetry snapshot republished every ~30 s, (b) Postgres tables (`fact_live_trades`, `s1_scored_signals_log`, `fact_trade_outcomes`), and (c) an OANDA candle proxy at `/api/v1/market/candles`. The asset detail chart is `telemetry-dashboard/src/components/assets/AssetChartPanel.tsx` (TradingView Lightweight Charts v5). Its own header docstring (lines 1–10) is the authoritative map of which data comes from where — read it first and keep it updated if you change a data path.

## 3. The problem you are solving

The chart shows *what price is doing* but not *what the system is thinking*, and the dashboard hides several load-bearing truths: why no signals fired, whether each data source is fresh or silently stale, whether the pipeline is even capable of trading right now, and what a past trade looked like when it fired. This system's worst historical failures were all **silent staleness** (price ingest dead 16 days unnoticed; trade outcomes frozen for months). Every task below converts a dead-end or a silence into a diagnostic.

---

## 4. Tasks

### Task 1 — Per-strategy signal breakdown (highest priority)

**Where:** `cloud/telemetry-web/routes/signals.py` (new endpoint) + a new panel section in `AssetChartPanel.tsx` replacing the bare "None for {pair} in the latest 100 logged signals" text.

**Backend.** Add `GET /api/v1/signals/breakdown?pair=EUR_USD&limit=200`: aggregate the most recent `limit` rows of `s1_scored_signals_log` for that pair, grouped by `strategy_key`, returning per strategy: `strategy_key`, `fired_count`, `last_signal_time_utc`, `last_model_score`, `last_wire_action`, `last_gate1_outcome`, `last_scoring_status`, `last_refusal_reason`, `last_shadow_verdict`. Also return `total_logged_for_pair` and `window_earliest_logged_at` so the frontend can say what window it is describing. The DDL is at `cloud/telemetry-web/migrations/004_s1_scored_signals_log.sql` — read its SQL COMMENTs; they encode traps.

**Three semantic traps you must carry into both code and UI copy:**
- `shadow_verdict IS NULL` means **"no verdict reached"**, NOT `would_refuse`. Counting NULL as a refusal is the FIX-S1-010 denominator error. Render NULL as "no verdict".
- `threshold_applied` is a hardcoded 0.5 placeholder, **not an enforced cutoff** (FIX-S1-018). If you display it, label it "placeholder", or better, don't display it.
- `wire_action` can carry `suppressed_duplicate`, which is not in migration 004's CHECK constraint. Handle it in display code; note the constraint gap in your report.

**Verdict column derivation (frontend, in a testable `ui-custom/*.js` pure function):** map each strategy row to one of: `published` (wire_action=published) / `blocked` (dropped or suppressed, show refusal_reason if present) / `not scored` (gate1_outcome ≠ scored) / `no signal` (strategy known but zero rows in window). For the "strategies known but silent" rows, take the strategy list from the existing `/api/strategy-catalog` response (`{pointer, catalog}`). If the catalog does not expose which strategies apply to which pair, do **not** invent a "no map cell for this pair" verdict — render "no signal in window" and record in your report that pair→cell coverage is not derivable from any published artefact (that is a finding the owner wants).

**Frontend:** a compact table in the SYSTEM 1 SIGNALS section of `AssetChartPanel.tsx`, via a new fetch in `chartApi.ts` (keep the panel's convention: its network layer stays in `chartApi.ts`, not `services/api.ts`). Empty state: keep an honest sentence including the window ("0 of N logged signals in the last …").

**Tests:** backend — new `test_signals_breakdown.py` with an in-memory/sqlite-shaped fixture including at least one row per wire_action value **including `suppressed_duplicate`**, one NULL shadow_verdict row (assert it is not counted as refuse), and a pair with zero rows. Frontend — node test for the verdict-derivation function covering all four verdicts and the NULL trap.

### Task 2 — Per-source staleness chips

**Where:** new `ui-custom/FreshnessChips` component (pure logic in a `.js`/`.d.ts` pair) rendered in `AssetChartPanel.tsx`'s footer area (near the existing provenance text) and on `Assets.tsx` cards where data allows.

One chip per source with last-updated timestamp and an age tone (fresh / aging / stale):
- **Candles:** time of the last candle from the existing `fetchCandles` response vs its `granularity_sec` (stale = older than ~2 granularities, but only during market-open hours — weekends must not fire; if you cannot determine market-open cheaply on the frontend, cap the rule to "stale only if > 72h" and note it).
- **Regime:** `s2regime` grid entries already carry `as_of` and a `stale` boolean — use them, don't recompute.
- **Signals:** max `logged_at` from the Task 1 breakdown response.
- **Trades ledger:** latest fill/close time from the existing `fetchAssetTrades` response.
- **OOS inventory:** the pointer/version already surfaced by the asset-inventory fetch.

Absent source → chip renders "n/a", never a green dot and never an age of 0. All threshold logic in the pure `.js` module with node tests (fresh/aging/stale boundaries, missing input, weekend guard if implemented).

### Task 3 — "Can this system trade?" status strip

**Where:** new `ui-custom` component rendered at the top of `AssetChartPanel.tsx` (and optionally `Overview.tsx` is out of your allowlist — panel only).

One row of badges answering whether the pipeline could act right now: **model set** (status + `qualification_run_id` — take these from the `/api/s1model` payload; both fields are mandatory on published artefacts, so if either is missing render "unpublished" in amber, not blank), **execution queue** (inspect `connection.js` `buildModel()` for what `s2status`/`s2health` actually expose about the queue provider; if nothing does, render "unknown" and record the gap — do not hardcode "local"), **circuit breakers** (from the `s3breakers` slice of the model, if present), **market open/closed** (reuse whatever pure logic the `ForexTimezone` view uses if it is importable without editing it; otherwise omit and report).

The whole point of this strip is honesty: today the dashboard visually implies a live pipeline. Every badge must be traceable to a real payload field; every untraceable one renders "unknown".

**Tests:** node tests for the badge-derivation function: all-known, all-unknown, missing-model-set cases.

### Task 4 — Live trade markers on the chart

**Where:** `AssetChartPanel.tsx` + `chartMath.js` + `riskRewardPrimitive.ts` (extend, don't fork).

When the Trades toggle is on and the ledger has trades for the visible instrument (already fetched via `fetchAssetTrades`, already keyed by broker trade id via `chartMath.indexTradesByBrokerId`): entry marker at fill time/price (direction-aware arrow via `createSeriesMarkers`), exit marker at close time with close reason in the tooltip, and for **open** trades SL/TP price lines using the existing `RiskRewardPrimitive`. Snap timestamps to bar time with the existing `barTimeFor`. Trades outside the loaded candle window: skip silently on-chart but show a count ("2 trades outside loaded range").

Explicitly **not** in scope: backtest/hypothetical markers of any kind. Only ledger rows.

**Tests:** extend the chartMath node tests: marker derivation from a trade fixture (open trade → SL/TP lines; closed trade → entry+exit pair; trade outside window → excluded but counted).

### Task 5 — Trade replay (read-side "trade snapshot")

**Where:** `views/Trades.tsx`, `AssetChartPanel.tsx` (accept an optional "focus trade" prop), `chartApi.ts`, `routes/trades.py`.

**Goal:** click a trade row in the Trades view → the chart opens on that instrument, scrolled/zoomed to the trade's window (use the candle proxy's `to` parameter plus `count` to center the fill time), with the Task-4 overlays for that trade, plus a side card showing: strategy, direction, fill/close price and time, close reason, R outcome if present — and, if joinable, the fire-time context from `s1_scored_signals_log` (`model_score`, `regime`, `regime_structural`, `proposed_entry/sl/tp`).

**Backend:** add `GET /api/v1/trades/{broker_trade_id}/context` in `routes/trades.py`: the ledger row joined (best-effort) to its signal row. **Investigate the join key first** — candidates are `fact_live_trades.Correlation_ID` ↔ `s1_scored_signals_log.signal_id` (remember the string/UUID cast). Determine what actually links them from the fixtures (`cloud/signal-ingester/fixtures/2026-08-30-sample.ndjson`) and existing code in `services/layer4_client.py`. If no reliable join exists, ship the endpoint with `"signal_context": null` plus a `"signal_context_reason"` string, render the card without the fire-time block, and write the missing linkage up as the top finding of your report — the owner needs this gap named, not papered over.

**Why no image snapshots:** the fire-time context (regime label, gate score, proposed levels) is already captured at fire time in `s1_scored_signals_log` — the Postgres row *is* the snapshot; candles are deterministic to refetch. Do not build screenshot capture or new storage. Document the storage answer in one short section of your report: "a trade's snapshot = its `fact_live_trades` row (keyed by broker trade id) + its `s1_scored_signals_log` row (keyed by signal_id), replayed against OANDA candles on demand."

**Tests:** backend test for the context endpoint with a joinable fixture and a non-joinable one (assert honest null + reason, not fabricated context).

### Task 6 — Notifications panel wiring (three parts, frozen contract)

The current panel is 20 lines of hardcoded JSX at `TopBar.tsx` L357–378 ("0 ACTIVE" is a literal). The alert bridge's only sink is Telegram. You will build a publish surface, an endpoint, and a real panel. **The contract below is frozen — all three parts code against it exactly; if you believe it must change, stop and record why instead of changing it.**

**Contract — GCS object `telemetry/alerts.json`:**
```json
{
  "schema_version": 1,
  "generated_at_utc": "2026-09-18T09:30:00Z",
  "source": "alert_bridge",
  "alerts": [
    {
      "key": "emitter_stale",
      "severity": "warn",
      "message": "…",
      "first_seen_utc": "…",
      "last_seen_utc": "…"
    }
  ]
}
```
`severity` ∈ {`warn`, `critical`}. `alerts` empty array = genuinely checked and clear. Object absent from GCS = feed unavailable (these are different states and the UI must show them differently).

**6a (repo: `scalable-brain/`, file: `src/monitoring/alert_bridge.py`).** Add an optional GCS publish step: when env `ALERT_BRIDGE_GCS_PUBLISH=1` (default absent/off) and not `--dry-run`, write the contract object to `gs://scalable-brain-artifacts/telemetry/alerts.json` after `collect_alerts()`. Preserve everything the module promises today: it stays an observer (this artefact is telemetry export — nothing inside System 1 may read it back; say so in the docstring), `main()` still defaults to `--dry-run`, exit code stays 0 always, Telegram behaviour unchanged, publish failures are logged and swallowed. Do not add new alert conditions (map-expiry etc.) — out of scope. Extend the module docstring: name the problem (dashboard bell was a hardcoded stub), the design rule (one-way telemetry export, observer property preserved). **Tests** stay hermetic: fake the GCS client, assert the exact JSON shape against the contract, assert no publish on dry-run / env off / publish-error → still exit 0. Run `black`.

**6b (repo: umbrella, file: `cloud/telemetry-web/main.py`).** Add `GET /api/alerts` mirroring the existing `/api/s1health` GCS-cached pattern exactly (same auth, ~60 s cache, env-overridable object name, default `telemetry/alerts.json`). Absent object → a distinguishable `{"available": false}`-style response, not an empty alerts list. **Test:** new `test_alerts_endpoint.py` (fake GCS: present, absent, malformed JSON).

**6c (repo: umbrella, file: `TopBar.tsx` L357–378 region only).** Replace the stub: fetch `/api/alerts` (poll ~60 s), badge shows the active count with severity colouring; empty list → "No active alerts (checked {generated_at})"; feed unavailable → "Alerts feed unavailable" in amber with **no count at all** — never "0 ACTIVE" when unknown. Derivation logic in a pure `ui-custom/*.js` module with node tests (active list / empty / unavailable / malformed).

### Task 7 — OOS cumulative-R sparkline

**7a (repo: `scalable-brain/`, files: `src/analytics/assets.py`, `src/analytics/publish_analytics.py`).** Extend `build_asset_inventory` so each asset entry gains an optional `oos_r_curve` block: `{engine, n, points: [[iso_exit_time, cum_r], …]}` — cumulative sum of `r_multiple` from `fact_trade_outcomes` ordered by exit time, **filtered to `AUTHORITATIVE_ENGINE_FOR_VETTING` (`position_engine_v2`) only** — the table holds two engines whose `r_multiple` is not the same quantity (task/OPEN.md O-27) and pooling them is an explicit opt-in you must not take. Downsample to ≤ 120 points (keep first/last exactly). No data for an asset → omit the block entirely (absent is absent). Keep the bundle's existing publish flow untouched otherwise. **Tests:** hermetic, fake DB rows: cum-sum correctness, engine filter (a v1 row present must not leak in), downsampling endpoints, empty → omitted.

**7b (repo: umbrella, file: `views/Assets.tsx` + a new `ui-custom` sparkline).** Next to the existing Win Rate / Mean R / Trades tiles (L410–427 — note the comment there: `win_rate` is a **ratio**, not a percent), render a small cumulative-R sparkline from `oos_r_curve` when present; when absent render nothing (no empty axes). Label it "OOS, position_engine_v2, N=…". Recharts is already a dependency. **Test:** node test for the data-shaping function (present, absent, single-point).

Note the sequencing: 7b will show nothing in production until System 1 re-publishes the analytics bundle with 7a's change — that republish is the reviewer's job, not yours. Say so in your report so nobody files "sparkline missing" as your bug.

---

## 5. Explicitly out of scope (do not build, even if tempting)

- **Regime background shading / regime history ribbon** — blocked on an owner-level data-path decision (the only historical regime series lives in System 1's Postgres, unreachable from Cloud Run; the backend's `fact_market_regime_v2` died 2026-08-21; and the HMM labeller has a live retirement plan at `task/2026-September-week3/hmm-removal/PLAN.md`).
- Backtest/hypothetical trade markers (36/51 strategies carry a known look-ahead defect; overlays would render fiction).
- Gatekeeper-score sub-pane, key-level overlays, regime disagree badges — rejected by the owner.
- New alert conditions in the bridge; anything on `trading-1`; anything touching order placement, breakers, or commands.

## 6. Definition of done

- Full backend pytest suite green from `cloud/telemetry-web/` (paste count before/after).
- `npm test` green; `npm run build` passes (paste the tail); build output NOT copied anywhere.
- Every touched Python file passes `python -m py_compile`; no duplicate `def`s.
- Every new number on screen traceable to a real payload field; every absence renders as an explicit "n/a"/"unavailable" state with a node test proving it.
- No commits, no pushes, no deploys, no GCS/DB writes performed by you.

## 7. Deliverable

Write `GEMINI-REPORT-dashboard-observability.md` **next to this brief** containing: (1) files created/changed per task, one line each; (2) test evidence — suite counts and pasted output tails; (3) the Task 5 join-key finding (what links `fact_live_trades` to `s1_scored_signals_log`, or proof that nothing does); (4) the trade-snapshot storage note from Task 5; (5) **what you could not do and why**, per task; (6) things you noticed but did not touch (e.g., the `suppressed_duplicate` CHECK-constraint gap). A Claude session will review this report and the diff, then build, deploy to Cloud Run, verify the live bundle hash matches (traffic-pinning check), and republish the System 1 analytics bundle for Task 7.

When in doubt anywhere: stop, render the honest absent state, and write the question in the report. Do not guess.
