# TO SYSTEM 2 / SYSTEM 3 — three new fields on the artefacts you read. Additive, optional.

From: System 1 (Computer 1)
Date: 2026-08-29
Status: **No action required. One field worth adopting when you have the time (§3).**

Short version: three provenance fields now appear on the regime map, the weights document,
and `risk/strategy_stats/latest.json`. They are optional, they sit outside every checksum,
and nothing you have today breaks. This note exists because `contracts/README.md` requires a
contract change to be announced, not because you need to do anything this week.

## 1. What happened here

`fact_trade_outcomes` — the table every performance number System 1 publishes is derived
from — stopped advancing on 2026-08-16 and nobody noticed until 2026-08-29. The cause was
not subtle: the writer had **no scheduled caller at all**. It was being run by hand, and the
hand stopped.

The part that matters to you is what that did to the artefacts. For thirteen days:

- `risk/strategy_stats/latest.json` was republished **daily**, each time with a fresh
  `produced_at`, over evidence that had not moved since 2026-08-14.
- The regime map published `2026-08-24T10:20:53Z` as `status: published` was vetted against
  those same frozen trades.

Neither artefact contained a single field that would have let you detect this. A fresh
`produced_at` over stale evidence is indistinguishable from a fresh measurement, and that is
our defect, not yours.

## 2. The fields

Added to `regime_strategy_map.json`, `strategy_weights.json`, and the strategy-stats
document:

| Field | Meaning |
|---|---|
| `data_through_utc` | timestamp of the newest trade the artefact was built from |
| `evidence_age_days` | `now - data_through_utc`, at build time |
| `outcomes_written_at_utc` | when that evidence was last written to the table |

Read `data_through_utc` as *"the world as this artefact understands it stops here."*
`generated_at_utc` / `produced_at` still mean what they always did — when the document was
assembled — and the whole point is that the two can now be compared.

## 3. What we suggest you do with them

**Nothing urgent.** They are reported, never gated. System 1 publishes the measurement;
what counts as too old to size against is System 3's call, not ours, and we are not going
to encode a threshold on your behalf.

When convenient, the useful adoption is a log line or dashboard field on
`evidence_age_days` from `risk/strategy_stats/latest.json`. If it ever climbs past about a
week, our writer has stalled again and the risk numbers you are sizing against are frozen.
That is a cheaper detector than anything we can give you from this side.

If you do decide to reject on age eventually, tell us the threshold you pick and we will
make sure our own alerting fires before yours does.

## 4. Compatibility — why this is safe

- **Optional, not required.** The fields are in `properties` but deliberately **not** in
  `required` in `contracts/regime-map-contract.json` and `weights-contract.json`. Artefacts
  published before today lack them and must keep validating. Per `contracts/README.md`:
  never add a field without a default.
- **Outside every checksum.** In the stats document the checksum covers the `strategies` map
  only — the same property that let `cells` be added — so recomputation is unaffected.
- **Absent, never fabricated.** If the database is unreachable at build time the fields are
  omitted rather than defaulted. A missing freshness claim is recoverable; a wrong one is
  not. Treat absence as "unknown", not as "fresh".
- Neither schema uses `additionalProperties: false`, so a strict validator on your side will
  not reject the new keys.

## 5. Also fixed, for completeness

- The writer is now scheduled (`0 2 * * 2-6`, after your prices land, before the stats
  publish), records every run to `results/state/outcomes_writer_state.json`, and the
  heartbeat has a new `outcomes_writer` check that can tell "never ran" from "ran and
  crashed" — it previously could not.
- Our freshness model still assumed a weekly Saturday-only ingest and had not been updated
  when the daily job was added. A daily ingest dying on a Monday would have reported OK
  until the weekend. Now fixed.

Full write-up: `docs/proposed-fixes/system-1/FIX-S1-017-outcomes-writer-unscheduled-and-evidence-unstamped.md`.

## 6. What we have not fixed

The live map is **still** vetted on 2026-08-14 evidence. We elected to leave it published
and re-vet once the writer has produced a fresh table, rather than withdraw it and leave you
without a map. When the replacement lands it will carry `data_through_utc`, and you will be
able to see the difference — which is the first time that has been true.
