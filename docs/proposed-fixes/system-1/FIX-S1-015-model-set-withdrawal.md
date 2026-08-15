# FIX-S1-015 — the live pointer had no way to say "there is no model"

**Raised:** 2026-08-14 · **Severity:** high — the live artefact contradicted the live state
for 15 days.
**Landed:** 2026-08-15 · **Executed against the production bucket:** 2026-08-15T21:55:07Z,
authorised by System 2 in `docs/comms/S2-REPLY-2026-08-15.md` §4.1.

---

## 1. The finding

`publish_model_set.py` implements a promotion contract: read the two sub-pointers, resolve
their immutable prefixes, verify every SHA256 from the backend, flip `latest.json` last. It
is a *pure function of the two sub-pointers*, and that is exactly why it could not express
this state.

On 2026-08-14 FIX-S1-014 disqualified `Range_Stochastic_Divergence`, the only qualified
strategy. The correct live state became **"nothing qualifies"**. Three mechanisms then held
the wrong artefact in place, each behaving as designed:

1. The `non_empty_map` deployment gate refuses to promote a bundle with zero qualified
   strategies — correctly. It exists to stop a model built on nothing reaching production.
2. `publish()` can only move the pointer *forward* to a better model set. There was no verb
   for "there is none".
3. So `latest.json` went on serving `2026-07-26T00-27-51Z-b48f48d3_gk-656f09e2`, whose whole
   map is a strategy that cannot fire causally.

**The shape of this failure is worth naming.** Every individual control worked. The gate held,
the publish contract held, the checksums held. What was missing was a *verb*, and no amount of
correctness in the existing verbs could supply it.

## 2. A second finding, found while fixing the first

Between 2026-08-14 and 2026-08-15 this module carried a module docstring describing
`withdraw()` in full detail — the status flag, the mandatory reason, the
`previous_model_set.json` archive, the double-withdraw no-op, the CLI-only restriction —
**and no implementation.** `S1-NOTICE-2026-08-15` §2 told System 2 that the withdrawal path
"now exists in code" on the strength of reading that docstring.

It did not exist. A docstring written in the present tense is indistinguishable from one
describing behaviour, and this repository now has two known instances of the same trap — the
other is `registry.qualified()` claiming "`vet.py` reads from here", which `vet.py` does not
do (see `CONTRACT_V2_AND_POSITION_ENGINE.md` §11.1).

**Rule going forward: a docstring describing unbuilt behaviour must say so in its first
line.** Design intent belongs in a fix doc or a design doc, not in the present tense above
the code that does not do it.

---

## 3. The fix

### 3.1 Withdrawal is a separate verb

`withdraw(reason, dry_run=False, storage=None)` writes:

```json
{
  "schema_version": 1,
  "status": "withdrawn",
  "model_set_id": null,
  "withdrawn_at": "2026-08-15T21:55:07Z",
  "reason": "<mandatory, human, in words>",
  "supersedes": "<the model_set_id it replaces>",
  "artifacts": []
}
```

Deliberate properties:

| Property | Why |
|---|---|
| **Not a promotion with zero artifacts** | A promotion means "here is a better model". This means "there is no model". Conflating them would let `non_empty_map` be argued around. |
| **`model_set_id` is explicitly `null`, not absent** | A consumer keying on the id sees a value that cannot match anything it holds, rather than a missing key it might read as "unchanged". |
| **Mandatory `--reason`, rejected if blank or whitespace** | The artefact states its own cause. The next reader should not need this document. |
| **Never deletes** | The superseded manifest is archived to `previous_model_set.json`. Reinstating is an ordinary `publish()` — no special flag, no restore path to get wrong. |
| **Withdrawing twice is a no-op** | The second call must not archive the withdrawal over the rollback breadcrumb. That would replace the last real model set with an empty manifest and leave nothing to reinstate. |
| **CLI-only; `--reason` without `--withdraw` is an error** | An automated retrain deciding on its own to blank the live model is the single-flag failure mode System 2 objected to on 2026-08-02. A guard test asserts the orchestrator source contains no reference to `withdraw`. |

### 3.2 `status` is now stated explicitly on every manifest

System 2's consumer rule, agreed in `S2-REPLY-2026-08-15` §4.1:

> Any of missing, unreadable, `status != "published"`, empty `artifacts`, or a `status` we do
> not recognise ⇒ REJECT. **Unknown is not a permissive default.**

**Before 2026-08-15 the model-set manifest carried no `status` field at all.** Under that rule
a correct future promotion reads as "not published" and is refused. The rule is right and the
producer was wrong: `build_manifest()` now emits `status: "published"`, and the analytics
pointer does the same, so both artefacts obey one rule instead of two.

This is a fail-closed deadlock that would have surfaced at the *first* real promotion, months
from now, with nobody remembering why. It was found only because the consumer wrote its rule
down in the same week the producer changed.

### 3.3 Provenance binding — `qualification_run_id`

Requested by System 2 in the same reply, and shipped rather than deferred. Their 2026-08-15
incident is the argument: two stale committed mirrors **agreed with each other**, sharing a
`qualification_run_id` of `a5153ca0`, so internal consistency proved nothing. Only binding an
artefact to the *running* qualification run caught it.

`build_manifest()` now reads `qualification_run_id` out of the bundle's
`regime_strategy_map.json` **in the backend** — never from a local file, so it describes what
a consumer will actually download. The analytics pointer already carried it.

---

## 4. What was executed

| Artefact | Before | After |
|---|---|---|
| `gs://scalable-brain-artifacts/latest.json` | `2026-07-26T00-27-51Z-b48f48d3_gk-656f09e2` | `status: "withdrawn"`, 0 artifacts |
| `gs://…/previous_model_set.json` | — | the 2026-07-26 manifest, intact |
| `gs://…/system1/analytics/latest.json` | `2026-08-02T00-28-54Z-6f291067` (run `47fa3bd0`) | `2026-08-15T21-55-37Z-2908027a` (run `4f608511`), `cells: []` |

The analytics bundle was **republished empty rather than withdrawn** — it rebuilds from the
live map, which is empty, so the honest bundle is a valid one containing nothing:
`trade_returns.json` is `{"cells": []}` and all ten strategies in the catalog are
unqualified. A consumer gets a true empty state rather than an error.

## 5. Tests

`src/system1/serializer/tests/test_publish_model_set.py` — 9 added, 15 total:
status stated on publish · provenance run id read from the backend · withdrawal is empty and
keeps its reason · archives the superseded set and deletes nothing · double withdrawal does
not clobber the breadcrumb · reason mandatory · dry-run writes nothing · **publish reinstates
a withdrawn pointer** · the orchestrator cannot withdraw.

## 6. Rollback

Reinstating the 2026-07-26 model set is an ordinary publish — but **do not**. It is the
contaminated set; that is what `previous_model_set.json` records, not what it recommends. The
correct exit from this state is a new qualifying strategy.
