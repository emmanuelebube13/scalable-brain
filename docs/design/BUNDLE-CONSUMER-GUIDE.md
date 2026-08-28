# Model bundle — consumer guide

**Audience:** whoever operates System 2 (execution) or System 3 (risk), or any future
consumer of System 1's published model set.

**What System 1 publishes:** a versioned, checksummed, signed bundle in GCS containing the
trained models *and* the strategy code needed to run inference.

> **Status as of 2026-08-22: the bundle is real; the topology is not yet.** ADR-001 is
> approved by Systems 2 and 3 but **cutover has not happened.** System 1 still runs the
> signal producer today (the "bridge"), so trading still depends on Computer 1 being up —
> the exact coupling ADR-001 exists to remove. Everything in this guide about *fetching and
> verifying a bundle* is live and correct now. §9's topology describes the **post-cutover**
> arrangement. Do not read this document as saying System 1's producer is already
> decommissioned.

> Verify before you trust. Every step below that says *refuse* means refuse — a bundle that
> fails any check must not be used, and falling back to a previous bundle is safer than
> proceeding with one that failed. **Never fall back to locally-authored signals.**

---

## 1. What is in a bundle

| artifact | what it is |
|---|---|
| `regime_strategy_map.json` | which strategies are live, per regime, with their metrics |
| `strategy_weights.json` | per-regime weights, summing to 1 |
| `hmm_model.joblib` | the 4-state Gaussian HMM regime model |
| `champion_model.pkl` | the XGBoost gatekeeper |
| `champion_preprocessor.pkl` | its fitted preprocessor — **must** be used with it |
| `champion_manifest.json` | gatekeeper feature contract, thresholds, approval bands |
| `model_metadata.json` | provenance |
| `code_bundle.zip` | **strategy implementations + pinned dependencies + verification evidence** |

Inside `code_bundle.zip`:

```
src/layer0/strategies/…          the strategy implementations
src/layer0/data_access/indicators.py   hand-rolled ADX/ATR — do NOT substitute a library
src/regime/structural.py         CSRM structural labels (diagnostic)
requirements.txt                 pinned dependency set (== pins, NOT hash-locked)
DETERMINISM.md                   the comparison contract
reference_vector.json            fixed inputs + the exact outputs System 1 produced
candle_fingerprint.json          SHA256 of recent closed bars, to prove price agreement
```

## 2. Fetch

The authoritative pointer is the model-set manifest at bucket root of
`gs://scalable-brain-artifacts`. Do **not** read `system1/latest.json` — it is a
*sub*-pointer and can be newer or older than the combined set.

```bash
gsutil cp gs://scalable-brain-artifacts/latest.json          ./manifest.json
gsutil cp gs://scalable-brain-artifacts/latest.json.sig      ./manifest.sig
```

Adopt the manifest only when `manifest.json` has `"status": "published"`.

**Corrected 2026-08-23** after System 2 pointed out this section conflated two different
outcomes. "Refuse" is not one behaviour, and the distinction matters:

| status | meaning | correct behaviour |
|---|---|---|
| `"published"` | this set is live | adopt it |
| `"withdrawn"` | System 1 is instructing you to **stop** | halt inference; do **not** fall back to `last_good` — the withdrawal is the instruction |
| missing, empty, or unrecognised | System 1 has said **nothing** | **do not adopt this manifest**; keep running `last_good` and alarm |

The third row is the one this guide got wrong. A half-written or unrecognised manifest is an
absence of instruction, not an instruction to stop — inferring "withdrawn" from silence
would let a truncated upload halt trading, which is its own hazard. System 2's
`parse_withdrawal` reasoning on that point is right. But the code currently does neither:
it proceeds. Not adopting and alarming is the third behaviour, and it is the one required.

Unknown is still never a permissive default — it just means "keep the last good set",
not "stop".

## 3. Verify the signature — before anything else

A checksum proves the file was not corrupted. It does **not** prove who wrote it. Anyone
with write access to the bucket could rewrite an artifact *and* its checksum. The signature
is what makes the manifest authentic, so check it first and refuse if it is absent.

Public key (safe to distribute, never the private one):

```bash
gsutil cp gs://scalable-brain-artifacts/system1_manifest_signing_key.pub ./s1.pub
```

```python
import json, base64
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

manifest = json.load(open("manifest.json"))
signature = base64.b64decode(open("manifest.sig", "rb").read())
public_key = load_pem_public_key(open("s1.pub", "rb").read())

# Canonicalization is load-bearing: sort_keys=True, default separators, UTF-8.
payload = json.dumps(manifest, sort_keys=True).encode("utf-8")

public_key.verify(
    signature,
    payload,
    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
    hashes.SHA256(),
)   # raises InvalidSignature -> REFUSE THE BUNDLE
```

Algorithm: **RSA-PSS**, MGF1/SHA256, maximum salt length, SHA256 digest.

## 4. Verify every artifact's checksum

For each entry in `manifest["artifacts"]`, download `path` and confirm its SHA256 equals
`sha256`. A single mismatch means refuse the whole bundle — not just that artifact.

```python
import hashlib
for a in manifest["artifacts"]:
    data = download(a["path"])
    assert hashlib.sha256(data).hexdigest() == a["sha256"], a["name"]
```

## 5. Install the code bundle

> **Caveat on the dependency set.** `requirements.txt` inside the bundle uses exact `==`
> pins, but it is **not hash-locked** (`--hash=sha256:…`) and it is not yet derived from
> the environment the models were actually trained in. Treat it as "the versions System 1
> intends", not as a supply-chain guarantee. Hash-locking is outstanding work.

Unpack `code_bundle.zip` and install its `requirements.txt` **into a separate virtualenv**
from your execution path. Bumping numpy or scikit-learn under your order-execution code to
satisfy an inference dependency moves the execution path for an inference change — that is
the wrong trade and System 1 does not ask for it.

```bash
unzip code_bundle.zip -d bundle/
python -m venv .venv-inference
.venv-inference/bin/pip install -r bundle/requirements.txt
```

Do **not** substitute a technical-analysis library for
`src/layer0/data_access/indicators.py`. Those ADX and ATR implementations are hand-rolled
specifically to stay byte-identical to what the models were trained against. A second
implementation of the same indicator in the same process is train/serve skew reintroduced
through the back door.

## 6. Replay the reference vector — a hard gate

This is the check that makes running System 1's code safe rather than merely convenient.
`reference_vector.json` contains fixed input bars and the exact outputs System 1's own code
produced from them. Replay it and compare.

**If it does not match, refuse to run.** Not warn — refuse. A mismatch means your execution
of the bundle differs from what was validated, and every metric in the map describes a
different implementation from the one you would be trading.

Tolerances, from `DETERMINISM.md`:

| output | rule |
|---|---|
| feature values, raw state probabilities | relative **1e-9** |
| regime label, direction, instrument, granularity, bar timestamp | **exact equality** |

A flipped label is a different trade; no tolerance makes that acceptable.

Two things the replay must respect:

- **Sequence length is part of the contract.** hmmlearn scores a *sequence*; the same bars
  at a different window length yield a different label. Use the window the vector states.
- **Replay against the bundle you have loaded in memory, not the one on the symlink.** If
  your model cache is swapped atomically but your consumer caches the loaded model, the
  replay will pass against the new bundle while production keeps inferring from the old
  one, and it will have proven nothing. Force a reload on swap.

## 7. Check the candle fingerprint

`candle_fingerprint.json` is a SHA256 over the last N **closed** bars per instrument ×
granularity, across `(bar_time_utc, o, h, l, c)`. Compare it against your own price series
to prove you and System 1 are looking at the same market.

- Closed bars only, and **exclude the most recent bar** — boundary races otherwise produce
  false alarms.
- Treat a mismatch as a gate, not a log line. A regime label computed from a different price
  series is a different label.
- System 1 reads OANDA **practice** (`api-fxpractice.oanda.com`) and stores true mid
  (`price=MBA`). If you fetch `price=M` from the same endpoint the series should agree.
- **Caveat:** before 2026-08-21 the System-1 ingest wrote *bid* into the mid columns.
  Repaired so far: W1 in full, and 2026-05-03 → 2026-07-03 on D1/H4/H1. Rows outside those
  ranges written by the old path may still be about half a spread low. Fingerprints over an
  unrepaired range will disagree by design — check the range before raising an alarm.

## 8. The signal contract

Signals are validated against `contracts/signal-message-contract.json` (Scored_Signal_Queue
message contract **v2**). It is `additionalProperties: false` on both sides — **a field name
not listed is dead-lettered, not ignored.** Producer and consumer must agree on exact
spelling.

Field names follow System 3's convention: `pair`, `proposed_entry`, `proposed_sl`,
`proposed_tp`, `atr`, plus provenance `producer`, `model_set_id`, `reference_vector_ok`.

Two semantics that are easy to get wrong:

- **`model_score` is nullable.** NULL means *unscored* — the gatekeeper did not know this
  strategy and refused to score it. It never means "scored zero" and must never be coerced
  to a number. System 3 branches on it.
- **`selection_basis` is deliberately not required**, so a missing basis produces an
  auditable REJECT rather than a silent dead-letter.

## 9. Routing topology

```
System 1  →  (publishes bundle to GCS; offline otherwise)
System 2  →  Scored_Signal_Queue  →  System 3  →  AMS_Outbound_Queue  →  System 2  →  broker
                                                   AMS_Inbound_Queue   ←  fills
```

**This is the post-cutover topology.** Today System 1's producer still publishes to
`Scored_Signal_Queue`; after cutover that publisher becomes System 2. The links either side
are unchanged.

System 3 does not subscribe to Pub/Sub directly — a relay bridges Pub/Sub to its local
queue. Note that its queue builder returns one backend for all topics, so moving it to
Pub/Sub would also move its outbound leg out of System 2's reach.

**Exactly one producer may publish to `Scored_Signal_Queue` at a time.** Two producers
emitting different `signal_id`s for the same bar will both be approved —
`ams_decision_log.signal_id` being UNIQUE catches a replay, not a second publisher —
reported by System 3 on 2026-08-22; not independently verifiable from the System 1 repo.

## 10. When something fails

| symptom | do this |
|---|---|
| Signature absent or invalid | Refuse. Do not fall back to checksums alone |
| Any artifact checksum mismatch | Refuse the whole bundle, keep the previous one |
| `status` is not `published` | Refuse. Unknown is not permissive |
| Reference vector mismatch | **Refuse to run.** Report the differing field to System 1 |
| Candle fingerprint mismatch | Check the repaired-range caveat in §7 first, then raise |
| No signals arriving | Distinguish "no signals", "signals rejected", "consumer down" before escalating — they are three different faults and have looked identical before |

Never compensate for an absent or failed bundle by generating signals locally. An execution
engine that manufactures its own orders when upstream goes quiet defeats every safety
property in the three-system design. Staying idle and saying so loudly *is* the correct
behaviour.
