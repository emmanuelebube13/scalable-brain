# TO THE TELEMETRY FRONTEND — build the Strategy House

From: System 1 (Computer 1)
Date: 2026-08-23
Data: `system1/analytics/latest.json` → `strategy_catalog.json` · **live now, 67 strategies**

---

## 1. What this is

One page answering, for every strategy the platform has ever built: **what does it do, how
does it enter and exit, and why isn't it trading?**

That last question is the one nobody can currently answer without reading commit messages.
The data now exists; it needs a surface.

## 2. Where the data is — never hardcode it

```
gs://scalable-brain-artifacts/system1/analytics/latest.json     ← pointer, read this first
  → { "version": "2026-08-23T00-55-54Z-319352a8", ... }
gs://scalable-brain-artifacts/system1/analytics/<version>/strategy_catalog.json
```

Resolve the pointer every load. Do **not** pin a version and do not copy the catalogue into
the frontend repo — the whole point is that it changes as strategies are added, edited or
retired, and a copy is a copy that goes stale.

> `telemetry/s1_analytics.json` is your aggregator's mirror and is currently **a day stale**
> (2026-08-21) against what System 1 has published. Either fix whatever refreshes it, or
> read the analytics pointer directly. Reading the pointer is simpler and always current.

## 3. The shape

Top level:

```json
{
  "schema_version": 1,
  "generated_at_utc": "2026-08-23T00:55:54Z",
  "qualification_run_id": "77f83887-...",
  "gates": { "profit_factor": 1.5, "sharpe": 0.8, "max_drawdown": 0.25,
             "win_rate": 0.4, "recovery_factor": 3.0, "oos_months": 12 },
  "empty_regimes": [...],
  "notes_overlay": "docs/strategy-notes.json",
  "notes_count": 9,
  "strategies": [ ... 67 ... ]
}
```

Per strategy, with current coverage across all 67:

| field | present | source | meaning |
|---|---|---|---|
| `strategy_id`, `name`, `family` | 67/67 | registry | identity |
| `description` | 67/67 | registry | one line |
| `granularities` | 67/67 | registry | `["H1"]` |
| `qualified`, `qualified_regimes` | 67/67 | vetting | is it live, and where |
| `gates_passed` | 67/67 | vetting | metrics per passing cell |
| **`gates_failed`** | 67/67 | vetting | **per-cell, with numbers** |
| `entries`, `exits`, `indicators` | 67/67 | **module source** | mechanics |
| `moves_to_breakeven` | 48/67 | module source | absent = no v2 module |
| `mechanics_source` | 67/67 | — | `"module"` or `null` |
| **`why_it_failed`** | 9/67 | **curated** | the honest reason |
| `what_was_tried` | 6/67 | curated | so nobody repeats a dead end |
| `next_step` | 9/67 | curated | or `null` if finished |
| `verdict` | 9/67 | curated | `live` / `retired` / `parked` / `candidate` |
| `notes_source` | 9/67 | — | present iff curated notes attached |

`gates_failed` is keyed `variant@granularity@regime` with the actual comparison:

```json
"liquidity_grab_fade@H4@Ranging": [
  "PF=0.35 < 1.50", "Sharpe=-1.92 < 0.80", "Recovery=-0.96 < 3.00"
]
```

That renders directly. No computation needed — the numbers and the thresholds are both
there.

## 4. Suggested page

**List view.** One row per strategy. Sort by `verdict` then `qualified`. Filters on
`family`, `verdict`, `qualified`, and "has notes" (`notes_source` present).

Badge each row by `verdict`, falling back to `qualified` when no verdict is set — most
strategies have no note yet, and "unreviewed" is honest.

**Detail view.** Four blocks, in this order:

1. **What it does** — `description`, `family`, `granularities`
2. **How it trades** — `entries`, `exits`, `indicators`, `moves_to_breakeven`.
   Say *"no v2 module"* when `mechanics_source` is null rather than showing empty lists as
   though the strategy has no mechanics.
3. **Why it isn't trading** — `why_it_failed` first if present, then the `gates_failed`
   table. Prose then evidence, not the reverse.
4. **What was tried / what's next** — `what_was_tried`, `next_step`. Hide the block
   entirely when both are absent; an empty "Next step" panel reads as "nobody knows",
   which is different from "not yet reviewed".

Show `generated_at_utc` and `qualification_run_id` in a footer. When someone asks why a
number differs from a report, the run id is the answer.

## 5. The part that matters most — you can edit it

The catalogue has two halves and they behave differently.

**Derived** (`entries`, `exits`, `indicators`, `gates_failed`, everything measured) is read
from source and from the vetting run. It cannot be edited by hand, by design — a
hand-maintained mechanics list drifts from the code and then lies.

**Curated** (`why_it_failed`, `what_was_tried`, `next_step`, `verdict`) lives in
`docs/strategy-notes.json` in the System 1 repo. It is a plain JSON object keyed by strategy
name:

```json
{ "strategies": {
    "demark_fractal_breakout": {
      "verdict": "retired",
      "why_it_failed": "Its USD_JPY H4 cell was the best result in the whole 47-strategy exercise — 610 OOS trades, PF 1.51, Sharpe 1.11, clearing every gate. Debunked: a pip-conversion bug (commit 2d3b432).",
      "next_step": null
    }
} }
```

**Anyone may edit that file, including you.** Unknown fields pass straight through to the
payload, so you can add anything the UI wants — `owner`, `tags`, `chart_url` — without a
code change on our side. Derived fields win a key collision, so a note can never contradict
what the code does. A malformed overlay is ignored with a warning rather than breaking the
publish.

If the dashboard ever grows an edit affordance, that file is the write target. Send us the
diff, or open a PR against the System 1 repo — do not fork the notes into the frontend, or
there will be two answers to "why did this fail" and no way to tell which is current.

## 6. Freshness

`generated_at_utc` advances when System 1 runs the analytics publish, which follows a
retrain or a vetting run — not on a fixed schedule. **A catalogue several days old is
normal and not an error.** Show the age; do not alarm on it. Same reasoning as
`s1_health.json`: System 1 is an offline factory and staleness is a reading, not an outage.

## 7. What it looks like today, so the first render is not a surprise

- **3 of 67 qualified**: `liquidity_grab_fade`, `macd_divergence`, `weekly_day_reversal_ea`
- **51 have populated `gates_failed`** — plenty to render
- **9 have curated notes**; the rest will show mechanics and gate failures only
- 48 of 67 resolve mechanics; the remaining 19 are legacy strategies with no v2 module

Worth surfacing honestly rather than smoothing over: the three qualified strategies passed
on **5, 13 and 20 out-of-sample trades**, after the out-of-sample gate was lowered from 60
months to 12 by owner decision. Their notes say so. A catalogue that presents PF 13.58 as a
triumph without the sample size beside it is worse than no catalogue.

## 8. Companion ask

`telemetry/s1_health.json` — the System 1 health panel, specified in
`TO-DASHBOARD-2026-08-23-add-s1-health-panel.md`. Different object, same bucket, same
"staleness is a reading" rule. Both in
`gs://scalable-brain-artifacts/handoff/adr001/`.
