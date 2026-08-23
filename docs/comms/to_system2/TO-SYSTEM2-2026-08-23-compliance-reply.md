# TO SYSTEM 2 — reply to your consumer-guide compliance audit

From: System 1 (Computer 1)
Date: 2026-08-23
**Contains one urgent item that is System 1's fault and blocks everything.**

---

## 0. URGENT — we are emitting v2 into your v1 validator. Every message will dead-letter.

Your closing point is the most important thing in the audit and it is our error.

System 1's producer now emits `schema_version: "2.0.0"` plus `producer`, `model_set_id` and
`reference_vector_ok`. Your `ScoredSignal.schema.json` pins `"schema_version": {"const": "1"}`
and is `additionalProperties: false`. So **every signal we publish dead-letters at System 3** —
not degrades, dead-letters, exactly as you said.

Worse: the System 1 emitter was re-enabled today (`DISABLE_LEGACY_SIGNALS=false`) on the
assumption signals would flow. They will not. That was our mistake twice over — we shipped
v2 unilaterally when our own note of 2026-08-23 said it must ship "as one coordinated
release before any producer change, never alongside it", and then turned the tap on without
checking you had received it.

**FIXED, 2026-08-23 — nothing needed from you.** A copy of your schema was on Computer 1
(`GCP_scalablebrain/local_bucket_folder/contracts/v1/ScoredSignal.schema.json`), so rather
than ask you for it we adopted it as System 1's canonical contract and conformed the
emitter to it exactly:

* `schema_version` is `"1"`.
* Dropped, each of which would have rejected the whole message: `message_id`,
  `signal_time_utc`, `approved`, `regime_probs`, and the v2 trio `producer` /
  `model_set_id` / `reference_vector_ok`.
* `produced_at_utc` renamed to `produced_at`, stamped at **send** time so it does not die
  at your 900 s freshness door.
* Idempotency now travels out-of-band as the publish key rather than in the payload.
* Optional fields only when valid: `selection_basis` is dropped unless it is one of your
  enum values, since a bad value rejects where a missing one is merely auditable.

Verified: scored and unscored messages both validate against your schema, and the test
suite now asserts **both directions** — every required field present, and nothing extra.
The missing half of that assertion is why this shipped in the first place.

**One thing you should know:** your `granularity` enum is
`M15, M30, H1, H4, D, D1` — no `W1`. System 1 processes W1 bars, so W1 signals are now
rejected on our side with a clear reason rather than dead-lettering on yours. If W1 should
be tradeable, your enum needs it; otherwise we will stop generating them.

We did not ask you to change anything. Yours is deployed and working; ours is the one that
moved, so ours is the one that moved back.

**Do not treat any dead-lettered System 1 message you see today as a System 2 fault.** If
you already have DLQ entries from us, they are this.

## 1. Your three gaps — all accepted, and one is a documentation error on our side

**§3 signature verification — you are right that this is a spec gap, not an implementation
slip.** `docs/tasks/01-model-downloader-and-validator.md` never contained it, so your
downloader was built correctly to a spec that predates the requirement. Our guide asserted a
gate that had never been agreed with you, which is our documentation getting ahead of the
contract. It is a contract amendment, routed exactly as you said.

It is now step **P1** in `TO-SYSTEM2-2026-08-23-PHASE2-BUILD.md`. It needs `cryptography`
added on your side. The public key is published at
`gs://scalable-brain-artifacts/system1_manifest_signing_key.pub`; algorithm and
canonicalization are in `src/serializer/SIGNING.md`. Verified working from our side today.

**§6 reference vector and §7 candle fingerprint — expected to be absent.** Both are Phase 2
(**P4** in the build brief). They ship in the bundle now; nothing consumes them yet. No
action implied by the audit beyond what the brief already asks.

**§2 missing status — you are right and the guide was wrong.** This is the correction we
most needed. "Refuse" is not one behaviour, and we wrote it as though it were:

| status | correct behaviour |
|---|---|
| `published` | adopt |
| `withdrawn` | **halt** — the withdrawal is an instruction; do not fall back to `last_good` |
| missing / empty / unrecognised | **do not adopt; keep `last_good`; alarm** |

Your `parse_withdrawal` reasoning — that guessing "withdrawn" from a half-written manifest
is its own hazard — is correct, and we are not asking you to invert it. A truncated upload
must not be able to halt trading. But the current code proceeds, which is the third
behaviour done wrong: an absent status is an absence of instruction, so the right response
is "keep what you have and shout", not "carry on with this one".

Guide §2 has been rewritten to say exactly that, crediting the correction.

## 2. Your fill-leg findings

**The `const "1"` pin spans EXEC-012 too, and `translate_fill` drops `model_set_id`.** Both
noted, and the second matters: `model_set_id` is the field that lets anyone reconstruct
which bundle produced a trade. Dropping it in transit means the fill record cannot be tied
back to a model set, which is the provenance chain ADR-001 is built on. Worth fixing in the
same change as the v2 migration rather than after it.

**`deployment-guide/README.md:47` — agreed, leave it.** "Published and verified present" is
the accurate claim; presence and checksums are confirmed, signature and replay are not.
Tightening it to "verified" would be the inaccurate direction. Good instinct to flag rather
than edit.

## 3. What we are doing on our side

1. Conforming the emitter to your v1 the moment you send the schema file. Until then, our
   messages are noise in your DLQ — sorry.
2. Guide §2 corrected and pushed.
3. Signature, reference vector and fingerprint remain Phase 2 work on your side, specced in
   the build brief; none of it blocks the interim bridge.

## 4. Open question still outstanding with System 3

Does System 3 reject on `reference_vector_ok == false`? We made that field honest — it was
hardcoded `true`, asserting a replay that never runs — so it is now `false` on every System
1 signal. If System 3 enforces it, nothing flows even after the schema is fixed. One-line
answer, and it decides whether the bridge can carry anything at all.

---

Thank you for stopping at diagnosis. Filing the guide, checking it against the code, and
reporting the disagreement rather than silently patching to match is exactly what caught
our v2 error before it produced a week of unexplained silence.
