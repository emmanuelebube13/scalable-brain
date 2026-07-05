# MODEL-010 — FinBERT Macro Feature Integration

**Task ID:** MODEL-010
**System:** System 1 — Model Building
**Priority:** P3-Low
**Estimated Effort:** 3d
**Prerequisites:** MODEL-006
**External Dependencies:**
- **`torch` / `transformers`** — FinBERT inference (GPU preferred, CPU acceptable for batch).
- **`ForexBrainDB` (PostgreSQL 16 + TimescaleDB, FND-004)** — read `Fact_Macro_Events`, write/extend veto export; via `src/common/db.py`. *(DB = PostgreSQL 16 + TimescaleDB; any historical SQL-Server mention is obsolete.)*
- **Macro sources** (ECB/Fed RSS + economic calendar via `src/nlp/macro_scraper.py`) — event stream.
- **Object storage / queue** (FND-001/FND-002, via MODEL-007/008) — export the veto signal to System 3.
- **MLflow** — log the macro feature set + veto export version.

## Objective
Integrate FinBERT macro sentiment (`Fact_Macro_Events`) as Layer 3 features and as a time-based veto signal exported for System 3.

## Current State
- `src/nlp/finbert.py` + `src/nlp/macro_scraper.py` scrape ECB/Fed RSS and calendar events and populate `Fact_Macro_Events`. This data is **not used** as Layer 3 features and **not enforced** as a veto — it is a built-but-idle auxiliary (a Known Gap in CLAUDE.md).

## Target State
FinBERT-derived macro sentiment becomes (1) **point-in-time features** for the Layer 3 gatekeeper (MODEL-006), and (2) a **time-based veto signal** — windows around high-impact events where trading should be suppressed/down-weighted — **exported for System 3** to enforce (System 1 produces the signal; System 3 acts on it). Optional/last in the sequence; integration is additive and behind a flag.

## Technical Specification

**Macro features (point-in-time, joined at signal time):** from `Fact_Macro_Events`, derive per (currency/instrument, time) features such as `macro_sentiment_score` (FinBERT polarity, e.g. [-1,1]), `macro_event_impact` (high/med/low), `time_to_next_event`, `time_since_last_event`, and `in_event_window` (boolean). Join to signals **as known at signal time** — only events published at/before the signal timestamp may contribute (no look-ahead on scheduled-but-future event outcomes; the *schedule* of a known upcoming event is allowed, its *result/sentiment* is not until released).

**Feature delivery:** add the macro features through the existing MODEL-006 feature-alignment/`ColumnTransformer` path so train/inference columns stay aligned. The gatekeeper can then learn to down-weight signals near adverse macro sentiment.

**Time-based veto export (for System 3):** produce a `macro_veto.json` (or queue message) describing veto windows: per currency/instrument, the time intervals around high-impact events during which trading is vetoed or down-weighted, with reason and source event. Exported alongside the model bundle (MODEL-007) or as a control message on the queue (MODEL-008), versioned and checksummed. **System 1 only emits the veto; enforcement is System 3's responsibility** (preserves the decoupling — Layer 4/execution does not gain new in-process logic here).

**`macro_veto.json` (shape, illustrative):**
```
{
  "schema_version": "1.0.0",
  "generated_at_utc": "...",
  "veto_windows": [
    {"currency": "USD", "event": "FOMC", "impact": "high",
     "start_utc": "...", "end_utc": "...", "action": "veto|downweight",
     "sentiment": -0.6, "source_event_id": "..."}
  ]
}
```

**Versioning / lineage:** macro feature set version + scraper run + FinBERT model version recorded in MLflow; veto export carries `schema_version` and checksum (verified by System 3).

**Data flow (text):** scraper populates `Fact_Macro_Events` → FinBERT scores event text → build point-in-time macro features for training (MODEL-006) and compute veto windows for high-impact events → export veto artifact/message for System 3 → log versions.

## Testing & Validation
- **Leakage test:** macro sentiment for an event is only available to signals at/after the event's release time; scheduled future events expose only their timing, never their (future) sentiment.
- **Feature-alignment test:** macro features flow through the gatekeeper preprocessor with train/inference column parity.
- **Veto-window test:** windows correctly bracket high-impact events (start/end, currency mapping); veto JSON validates against schema; checksum verifiable by consumer.
- **Uplift check:** re-run MODEL-006 OOS uplift with macro features — must not degrade incumbent performance (gate to keep them).
- **Edge cases:** missing/late events, conflicting events in the same window, low-confidence FinBERT scores, instrument unaffected by an event's currency.

## Rollback Plan
Fully optional and additive behind a flag. Roll back by removing the macro features from the gatekeeper feature list (reverts to MODEL-006 behavior) and by not emitting `macro_veto.json`. `Fact_Macro_Events` and the scraper are untouched; no other layer is affected.

## Acceptance Criteria
- [ ] FinBERT macro features are joined point-in-time (no result look-ahead) and flow through the MODEL-006 feature-alignment path.
- [ ] A versioned, checksummed time-based veto artifact (`macro_veto.json` or queue message) is exported for System 3 to enforce.
- [ ] Enforcement stays in System 3; System 1 only emits the veto signal (decoupling preserved).
- [ ] Adding macro features does not degrade OOS uplift versus the incumbent gatekeeper.
- [ ] Macro feature/veto versions and FinBERT model version are recorded in MLflow.

## Notes & Risks
- Event-timing vs event-outcome leakage is the subtle trap — the schedule of a known upcoming release is fair game; its sentiment is not until released.
- Lowest priority and optional; only enable if it demonstrably improves OOS uplift, otherwise keep as an emitted veto signal without feeding the model.
- The veto is advisory to System 3 by design — do not reintroduce execution-side coupling in System 1 to enforce it.
