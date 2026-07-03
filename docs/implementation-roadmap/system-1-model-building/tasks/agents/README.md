# System 1 Agent Fleet — Communication Protocol & Inter-Agent Contracts

## Fleet Overview

| Agent ID | File | Assigned Tasks | Priority |
|----------|------|---------------|----------|
| `data-pipeline-agent` | `data-pipeline-agent.md` | MODEL-001, MODEL-002 | P0 |
| `ml-regime-agent` | `ml-regime-agent.md` | MODEL-003, MODEL-006 | P1 |
| `attribution-vetting-agent` | `attribution-vetting-agent.md` | MODEL-004, MODEL-005 | P1 |
| `serializer-infra-agent` | `serializer-infra-agent.md` | MODEL-007, MODEL-009 | P0 |
| `queue-nlp-agent` | `queue-nlp-agent.md` | MODEL-008, MODEL-010 | P0/P3 |
| `auditor-traceback-agent` | `auditor-traceback-agent.md` | Cross-verification, quality gates, rework orchestration | P0 |

## Location Convention

All agents are defined in this directory:
```
docs/implementation-roadmap/system-1-model-building/tasks/agents/
```

All skills are defined in the sibling directory:
```
docs/implementation-roadmap/system-1-model-building/tasks/skills/
```

When Claude loads an agent file, it must also load all skills listed in that agent's `## Skills` section before beginning work.

## Communication Protocol

### Inter-Agent Handoffs

Agents communicate through **immutable output artifacts** at well-known paths. No agent calls another agent directly — they read each other's outputs from the filesystem.

### Contract Files

Each handoff is governed by a **contract file** that both producer and consumer validate against:

| Producer | Output Path | Contract | Consumer | Contract File |
|----------|-----------|----------|----------|---------------|
| data-pipeline-agent | `results/state/ingest_progress.json` | Resumable cursor schema | ml-regime-agent | `contracts/cursor-contract.json` |
| data-pipeline-agent | `Fact_Market_Prices` (D1/H4/W1 rows) | Granularity + lineage columns | ml-regime-agent, attribution-vetting-agent | N/A (DB schema) |
| data-pipeline-agent | `feature-store/{version}/` (Parquet) | `schema.json` + `lineage.json` | ml-regime-agent, queue-nlp-agent | `contracts/feature-store-contract.json` |
| ml-regime-agent | `Fact_Market_Regime_V2` (HMM probs) | Regime+granularity columns | attribution-vetting-agent, queue-nlp-agent | N/A (DB schema) |
| ml-regime-agent | `models/hmm_model.joblib` | Fitted HMM + scaler + mapping | serializer-infra-agent | `contracts/hmm-serialization-contract.json` |
| ml-regime-agent | `models/champion_manifest.json` | Dynamic thresholds + OOS uplift | serializer-infra-agent, queue-nlp-agent | `contracts/champion-manifest-contract.json` |
| attribution-vetting-agent | `results/state/regime_strategy_map.json` | Ranked strategies per regime | serializer-infra-agent | `contracts/regime-map-contract.json` |
| attribution-vetting-agent | `results/state/strategy_weights.json` | Per-regime allocation weights | serializer-infra-agent | `contracts/weights-contract.json` |
| serializer-infra-agent | `s3://model-artifacts/latest.json` | Bundle pointer + checksums | (System 2/Computer 2) | `contracts/bundle-contract.json` |
| queue-nlp-agent | `Scored_Signal_Queue` (broker) | Message schema + idempotency key | (System 3) | `contracts/signal-message-contract.json` |

### Rework Protocol

The `auditor-traceback-agent` is the only agent with authority to demand rework:

1. Auditor validates every agent's output artifacts after task completion.
2. If an output fails validation, auditor creates a **rework directive file**:
   ```
   results/state/rework/{AGENT_ID}_{timestamp}.md
   ```
3. The directive contains:
   - Which output artifact failed
   - Which validation check failed (exact assertion/criterion)
   - The expected vs actual values
   - Suggested remediation
4. The agent, on startup or when polling, checks for `results/state/rework/{AGENT_ID}_*.md` files.
5. If a rework directive exists, the agent MUST:
   - Read the directive
   - Fix the issue in its source code/data
   - Re-run its pipeline
   - Request the auditor re-validate by deleting the rework file
6. The auditor re-validates and either deletes the rework directive (pass) or keeps it with updated findings (fail again).

### Blocking Chain Rule

If Agent B consumes Agent A's output and Auditor finds Agent A's output invalid:
- Agent B MUST NOT begin work until Agent A's rework is cleared.
- Auditor will not validate Agent B's output while Agent A has an open rework directive.

## Agent Startup Checklist

Every agent, on first invocation, must:

1. [ ] Read this `README.md` for fleet awareness.
2. [ ] Read its own agent definition file (`agents/{agent-id}.md`).
3. [ ] Load all skills listed in its `## Skills` section.
4. [ ] Check for open rework directives at `results/state/rework/{AGENT_ID}_*.md`.
5. [ ] Read the output manifests of all upstream agents it depends on.
6. [ ] Verify upstream artifacts pass checksum/schema validation before consuming them.
7. [ ] Execute its task(s) in dependency order.
8. [ ] Run its self-verification gates before declaring completion.
9. [ ] Signal completion by writing a `DONE_{AGENT_ID}_{timestamp}.md` to `results/state/`.
10. [ ] Wait for auditor validation before proceeding to next task.

## Prerequisites Resolution

Before any agent starts, verify these foundation dependencies exist:

```
[FND-001] Object storage / shared volume — writable path or S3-compatible bucket
[FND-002] Message queue broker — reachable URL, queue created
[FND-004] PostgreSQL 16 + TimescaleDB — localhost:5432, ForexBrainDB, role sa
```

Agents check FND prerequisites in their `## Prerequisites` section and must fail-fast with a clear message if any are missing.
