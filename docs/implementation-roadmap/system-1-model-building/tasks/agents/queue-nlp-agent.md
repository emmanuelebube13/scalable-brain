# Queue Producer & NLP Agent

**Agent ID:** `queue-nlp-agent`
**File:** `docs/implementation-roadmap/system-1-model-building/tasks/agents/queue-nlp-agent.md`
**Role:** Scored signal queue publication (decoupling System 1 from Systems 2/3) and FinBERT macro sentiment integration.

---

## Assigned Tasks

| Task | Description | Priority | Est. Days | Prerequisites |
|------|-------------|----------|-----------|---------------|
| [MODEL-008](../08-scored-signal-queue-producer.md) | Scored Signal Queue Producer | P0 | 2d | FND-002 |
| [MODEL-010](../10-finbert-macro-feature-integration.md) | FinBERT Macro Feature Integration | P3 | 3d | MODEL-006 |

---

## Skills

Before starting, load these skill files:

- `skills/queue-decoupling.md` — Message contracts, idempotency, backpressure, DLQ
- `skills/point-in-time-leakage.md` — No-look-ahead for macro event sentiment joins
- `skills/layer3-contract.md` — Champion manifest, dynamic thresholds for scoring
- `skills/postgres-patterns.md` — DB reads for `Fact_Signals`, `Fact_Macro_Events`, `Fact_Market_Regime_V2`

The following packages must be in `requirements.txt` before starting:
```
# For MODEL-008 (choose one):
pika>=1.3.0            # RabbitMQ client
# OR
redis>=5.0.0           # Redis client

# For MODEL-010 (already present but verify):
torch>=2.1.0
transformers>=4.36.0
```

---

## Communication With Other Agents

### Upstream (dependencies)
| Producer Agent | Consumed Artifact | Path |
|----------------|-------------------|------|
| `ml-regime-agent` | Champion manifest (dynamic thresholds) | `models/champion_manifest.json` |
| `ml-regime-agent` | Champion model + preprocessor | `models/champion_model.pkl`, `models/champion_preprocessor.pkl` |
| `ml-regime-agent` | `Fact_Market_Regime_V2` (regime probs at signal time) | DB |
| `ml-regime-agent` | `Fact_Signals` (signals to score) | DB |
| `data-pipeline-agent` | Feature store (for gatekeeper inference features) | `feature-store/{version}/` |
| (External) | `Fact_Macro_Events` (FinBERT-scored macro events) | DB |
| (External) | `src/nlp/finbert.py`, `src/nlp/macro_scraper.py` | `src/nlp/` |

### Downstream (consumers)
| Consumer | Consumes | Contract |
|----------|----------|----------|
| System 3 | `Scored_Signal_Queue` messages | `contracts/signal-message-contract.json` |
| System 3 | `macro_veto.json` (or queue message) | `contracts/macro-veto-contract.json` |
| `auditor-traceback-agent` | Queue metrics (published count, DLQ count, backpressure events) | Metrics/logs |

---

## Input Contracts

### MODEL-008 Inputs
- **Champion artifacts**: `models/champion_model.pkl`, `models/champion_preprocessor.pkl`, `models/champion_manifest.json`.
  - Must contain `dynamic_thresholds` map (from MODEL-006) OR fall back to static `LAYER3_APPROVAL_THRESHOLD` from `.env`.
- **`Fact_Signals`**: signal-level data with full feature columns.
  - Column `Is_Active` is optional (schema-aware code).
  - H1/H4 granularity contract preserved (D1 added by MODEL-001/003 but existing H1/H4 must work).
- **Message queue**: broker URL from `.env` (`QUEUE_URL`), queue name `SCORED_SIGNAL_QUEUE`, `MAX_QUEUE_SIZE`, DLQ name.

### MODEL-010 Inputs
- **`Fact_Macro_Events`**: populated by `src/nlp/macro_scraper.py` + `src/nlp/finbert.py`.
  - Columns: event metadata, currency/instrument mapping, FinBERT sentiment score, impact level, release timestamp.
- **Existing gatekeeper feature pipeline** from MODEL-006: ColumnTransformer, feature-alignment module.
- **FinBERT model**: `ProsusAI/finbert` via HuggingFace `transformers`.

---

## Output Contracts

### MODEL-008 Outputs

1. **Scored_Signal_Queue messages** — Published per signal.
   ```json
   {
     "message_id": "signal_uuid:score_run_uuid",
     "signal_id": "...",
     "instrument": "EUR_USD",
     "granularity": "H1",
     "signal_time_utc": "2026-06-23T14:00:00Z",
     "direction": "long",
     "model_score": 0.83,
     "approved": true,
     "threshold_applied": 0.72,
     "regime": "Trending-Up",
     "regime_probs": {
       "trending_up": 0.72,
       "trending_down": 0.10,
       "ranging": 0.08,
       "high_vol": 0.10
     },
     "bundle_version": "2026-06-23T00:00:00Z",
     "produced_at_utc": "2026-06-23T14:00:05Z"
   }
   ```
   - `message_id` = deterministic idempotency key: `f"{signal_id}:{score_run_id}"`.
   - `approved` = `model_score >= threshold_applied` (threshold from dynamic map, per-regime).
   - `bundle_version` = the MODEL-007 bundle version this scoring run uses.

2. **Dead-Letter Queue messages** — Un-publishable messages routed to DLQ.
   - Additional fields: `dlq_reason`, `dlq_timestamp`, `original_message` (full message attempted).

3. **Metrics (logged, not queue)**:
   - `published_count`, `dlq_count`, `backpressure_events`, `current_queue_depth`.
   - Logged to `logs/` and optionally emitted as telemetry messages.

### MODEL-010 Outputs

1. **Macro features for gatekeeper** — Added through `ColumnTransformer` path (MODEL-006).
   - `macro_sentiment_score` (float, [-1,1])
   - `macro_event_impact` (categorical: high/med/low)
   - `time_to_next_event` (float, seconds)
   - `time_since_last_event` (float, seconds)
   - `in_event_window` (boolean)
   - Joined point-in-time: only events with `release_time <= signal_time` contribute.

2. **`results/state/macro_veto.json`** (or queue message for System 3)
   ```json
   {
     "schema_version": "1.0.0",
     "generated_at_utc": "2026-06-23T14:00:00Z",
     "bundle_version": "2026-06-23T00:00:00Z",
     "finbert_model_version": "ProsusAI/finbert",
     "veto_windows": [
       {
         "currency": "USD",
         "event": "FOMC Press Conference",
         "impact": "high",
         "start_utc": "2026-06-24T18:00:00Z",
         "end_utc": "2026-06-24T20:00:00Z",
         "action": "veto",
         "sentiment": -0.62,
         "source_event_id": "event_uuid"
       }
     ],
     "checksum_sha256": "abc123..."
   }
   ```
   - **System 1 only emits** the veto signal. Enforcement is System 3's responsibility.

3. **MLflow run** — Log macro feature set version, scraper run, FinBERT model version, veto artifact checksum.

---

## Verification Gates (Self-Check Before Handoff)

### MODEL-008 Gates
- [ ] **Message schema validation**: every published message validates against the contract schema (all required fields present, correct types).
- [ ] **Idempotency**: publish the same scored signal twice → exactly one effective message at the consumer (verified with a stub consumer that deduplicates on `message_id`).
- [ ] **Backpressure**: fill queue to `MAX_QUEUE_SIZE` → producer applies backpressure (blocks or retries), queue depth never exceeds max, no messages silently dropped.
- [ ] **DLQ routing**: force a publish failure (e.g., invalid broker credentials during test) → message lands in DLQ with reason code, alert metric increments.
- [ ] **Decoupling regression**: static import check confirms System 1 scoring path has zero imports from `src/layer4_executor/`.
- [ ] **H1/H4 contract preserved**: message `granularity` field correctly reflects the signal's granularity.
- [ ] **Dynamic threshold resolution**: per-regime threshold from `champion_manifest.json` applied correctly; missing regime falls back to `fallback` threshold.
- [ ] **Publisher confirms**: broker acknowledges receipt (at-least-once semantics). No fire-and-forget publishing.

### MODEL-010 Gates
- [ ] **Point-in-time leakage**: macro sentiment for an event is only available at signals with `signal_time >= event_release_time`. Scheduled future events expose timing but never their sentiment.
- [ ] **Feature alignment**: macro features flow through `ColumnTransformer` with train/inference column parity (verify same columns appear in transform as during fit).
- [ ] **Veto window correctness**: each veto window's currency mapping, start/end times, and action are correct. JSON validates against schema. Checksum verifiable by consumer.
- [ ] **OOS uplift check**: re-run MODEL-006 OOS uplift analysis with macro features enabled. Must NOT degrade OOS uplift versus the incumbent gatekeeper without macro features.
- [ ] **Enforcement in System 3**: verify that no veto enforcement logic exists in System 1 code. The veto is advisory/emitted only.
- [ ] **Edge cases**: events with missing/late scraping, conflicting event windows, low-confidence FinBERT scores (handle gracefully, don't crash).

---

## Failure Modes & Escalation

| Failure | Detection | Action | Escalate To |
|---------|-----------|--------|-------------|
| Queue broker unreachable | Connection error | Retry with backoff. If persistent, fall back to in-process Layer 3→4 path (if flagged) or abort. | `auditor-traceback-agent` |
| Queue at capacity (backpressure sustained) | Backpressure event count > threshold | Slow/block producer, investigate consumer lag, alert | System 3 operator (consumer-side issue) |
| Message repeatedly fails to publish | DLQ count growing | Route to DLQ, alert on DLQ growth rate, investigate reason codes | `auditor-traceback-agent` |
| Feature alignment mismatch (MODEL-010) | ColumnTransformer input cols ≠ training cols | Rebuild preprocessor with macro columns, verify alignment | `ml-regime-agent` (for MODEL-006 rework) |
| Macro features degrade OOS uplift | Uplift < incumbent | Disable macro features from feature list (flag), do not add to gatekeeper | `auditor-traceback-agent` (accept or reject macro features) |
| Point-in-time leakage (MODEL-010) | Leakage test fails | Fix join logic: `event_release_time <= signal_time`, never use future sentiment | Self (fix code) |
| FinBERT inference too slow for batch | Inference time exceeds budget | Batch inference, GPU if available, reduce frequency | Self (optimize or accept lower frequency) |

---

## Notes

- **MODEL-008 is the structural cut between System 1 and Systems 2/3.** The message contract must be minimal and versioned. Consumers (System 3) must agree on the schema. Any schema change is a coordinated, versioned change.
- **Backpressure must favor correctness over throughput**: never drop a valid scored signal to keep the producer fast. Block, retry, or DLQ — never silent drop.
- **Retain the in-process Layer 3→4 fallback** behind a feature flag during MODEL-008 transition. Remove the direct path only once System 3 consumption is proven stable.
- MODEL-010 is P3-Low and **fully optional**. Only enable macro features if they demonstrably improve OOS uplift. Otherwise, keep `macro_veto.json` as an advisory emission without feeding the gatekeeper model.
- **Event-timing vs event-outcome leakage** is the subtle trap in MODEL-010. The schedule of a known upcoming release is fair game for features. The sentiment/result of that release is NOT available until after release time. Test this explicitly.
- `src/nlp/finbert.py` and `src/nlp/macro_scraper.py` already exist and populate `Fact_Macro_Events`. MODEL-010 integrates their output — it does not rebuild the scraping/NLP pipeline.
