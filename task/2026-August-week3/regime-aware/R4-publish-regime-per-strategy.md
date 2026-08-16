# R4 — Publish regime per strategy per timeframe

**Engineer:** Gemini Pro · **Reviewer:** Claude
**Estimated time:** 3–4 hours · **Risk:** medium — this publishes to shared storage.
**Needs:** R2 (masks) DONE. R3 helps but is not strictly required.

**Read `STATE.md` first. Read `README.md` §2 and §8.**

---

## Why this task exists

Systems 2 and 3 need to see, in something close to real time, **which regime each strategy
is currently in, per timeframe** — and therefore whether it is trading or sitting out.
Today nothing publishes that.

This is the System 1 half of the job. The **view** is System 2/3's department and we do not
build it — see `notes-for-systems-2-3/DASHBOARD-NOTE.md`, which ships alongside this
artifact and specifies what they would render.

---

## What you are NOT building

**No frontend. No dashboard. No React.** The archived `archieved/layer5/frontend` is not a
port target — it renders regime per *asset* with no timeframe dimension, uses a different
four-label vocabulary (`Trending_HighVol` etc.), and its price/regime overlay is hardcoded
placeholder data banded by row index. Do not resurrect it. It is referenced in the note to
Systems 2/3 as prior art only.

---

## Hard constraints

1. **Follow the existing publish contract exactly** — read
   `src/system1/analytics/publish_analytics.py` and `src/common/storage/README.md` first.
   Immutable versioned prefixes, upload → SHA256 verify → **only then** the atomic pointer
   flip, superseded pointer archived, old versions never overwritten.
2. **`status` and `qualification_run_id` are mandatory** on the published artifact
   (`CONTRACT_V2_AND_POSITION_ENGINE.md` §11.4). `status` is exactly `"published"` or
   `"withdrawn"`. A consumer rejects on missing, unreadable, empty, or unrecognised status —
   unknown is never a permissive default. Both fields were added after two stale artifacts
   agreed with each other and fooled every age check; do not drop them.
3. **This is a new, separate artifact.** Do **not** touch the root `latest.json` model-set
   pointer or the analytics pointer. Publish under its own prefix.
4. **`--dry-run` is the default.** Publishing for real requires an explicit flag, and the
   owner's sign-off recorded in `STATE.md`.
5. Only `regime_causal`. Never `regime_smoothed`.

---

## The artifact

Suggested prefix: `system1/regime_status/<version>/` plus its own `latest.json`.

Per (strategy × granularity × pair):

| Field | Notes |
|---|---|
| `strategy_key` | v2 string id |
| `family` | from R2 |
| `granularity` | H1 / H4 / D1 |
| `pair` | instrument |
| `regime_current` | label in force at the most recent closed bar |
| `regime_source` | `d1_trend` or `hmm_causal` — never omitted |
| `as_of_bar_utc` | timestamp of the bar the label came from, **not** publish time |
| `is_trading` | whether the mask enables this regime for this strategy |
| `mask` | the frozen mask from R2 |
| `bars_in_regime` | how long the current label has held |

Plus, at document level: `status`, `qualification_run_id`, `generated_at_utc`,
`schema_version`, and a checksum over the payload.

**`as_of_bar_utc` and `generated_at_utc` must both be present and must be distinct fields.**
A consumer needs to distinguish "the label is old because the market has not printed a new
bar" from "this document is stale". Collapsing them is how a dead feed looks healthy.

### Freshness

Whatever refresh cadence you choose, the document must carry enough information for a
consumer to reject it on age **without** guessing. System 2 already rejects a profile older
than one hour on a similar artifact. State the intended cadence in the document itself.

---

## Execution plan

### Step 1 — Read the existing publisher

`publish_analytics.py`. Understand the verify-then-flip ordering and the retention
behaviour before writing a line. Do not invent a second publish mechanism.

### Step 2 — Build the document assembler

Pure function: inputs → document. No I/O. Testable without a network or a bucket.

### Step 3 — Build the publisher

Reusing `src/common/storage`. Dry-run by default, staging locally.

### Step 4 — A JSON schema contract

`contracts/regime-status-contract.json`, matching the house pattern of the existing three
contracts. This is the file Systems 2 and 3 validate against — it is the interface, and a
contract that lives only in the consumer is a contract only one side can check.

### Step 5 — Tests

- Checksum mismatch **aborts** and leaves the pointer untouched
- Missing `status` or `qualification_run_id` refuses to publish
- `as_of_bar_utc` and `generated_at_utc` are both present and independent
- Dry-run writes nothing remote
- Document validates against the contract schema
- A strategy sitting out reports `is_trading: false` rather than being omitted

### Step 6 — Dry-run, show the owner, then publish only on sign-off

Record the sign-off in `STATE.md` before any real publish.

---

## Definition of done

- [ ] Document assembler + publisher, dry-run default
- [ ] `contracts/regime-status-contract.json` written
- [ ] Tests above pass
- [ ] Dry-run output reviewed by the owner; sign-off recorded in `STATE.md`
- [ ] Root `latest.json` and the analytics pointer **untouched** — verify and state this
- [ ] No frontend code written

## What the reviewer will check

- Ordering: upload → verify → flip. Claude will read the code path, not the docstring.
- That a corrupted upload aborts without moving the pointer.
- That `status` and `qualification_run_id` cannot be omitted.
- That the model-set pointer was not touched.

---

## Failure log

| Timestamp | Step | What went wrong | Root cause | Fix applied |
|---|---|---|---|---|
| | | | | |
