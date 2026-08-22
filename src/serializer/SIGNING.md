# Model-Set Manifest Signing

`publish_model_set.py` signs the top-level manifest (`latest.json`) so a consumer can
detect tampering or corruption between System 1 publishing it and System 2 reading it.
This document is the contract a verifier needs: algorithm, canonicalization, key
location, and a copy-pasteable verification snippet.

## Algorithm

- **RSA-PSS** signature, over SHA256.
- **MGF1** mask generation function, also SHA256.
- **Salt length**: `PSS.MAX_LENGTH` (the maximum permitted by the key size).
- The private key is `secrets/manifest_signing_key.pem` (PKCS8, unencrypted). It never
  leaves Computer 1 and is git-ignored — only the public key is published.

Signing fails **closed**: if the private key file exists but signing raises for any
reason (unreadable, wrong key type, corrupt PEM, etc.), `publish()` aborts with
`ModelSetRefused` before the live pointer is flipped. A manifest is never published
unsigned by accident. (If no key is configured at all, the module logs a warning and
publishes unsigned — that is a deployment-configuration state, not a signing failure.)

## Canonicalization

The bytes that are signed — and that a verifier must reproduce exactly — are:

```python
import json
manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
```

`manifest` is the parsed JSON object exactly as downloaded from `latest.json`. Do not
re-serialize with different `indent`, key order, or separators — `sort_keys=True` is
what makes this reproducible; anything else will not match the signature.

## Where the artifacts live

| Object | Bucket key |
|--------|-----------|
| Manifest | `latest.json` |
| Detached signature (base64-encoded RSA-PSS signature bytes) | `latest.json.sig` |
| Public key (PEM, SubjectPublicKeyInfo) | `system1_manifest_signing_key.pub` (bucket root) |

The public key is re-uploaded on every publish, so it always matches whatever key is
currently signing. It is overwritten in place (not versioned) — if you need to pin to a
specific key for an audit, capture it alongside the manifest at that time.

## Verification snippet

```python
import base64
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

with open("system1_manifest_signing_key.pub", "rb") as fh:
    public_key = serialization.load_pem_public_key(fh.read())

with open("latest.json", encoding="utf-8") as fh:
    manifest = json.load(fh)

with open("latest.json.sig", encoding="utf-8") as fh:
    signature = base64.b64decode(fh.read().strip())

manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")

try:
    public_key.verify(
        signature,
        manifest_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    print("signature OK")
except Exception:
    print("signature INVALID — reject this manifest")
    raise
```

`public_key.verify(...)` raises `cryptography.exceptions.InvalidSignature` (a subclass
of `Exception`) if the signature does not match; it returns `None` on success. Treat any
exception here — not just `InvalidSignature` — as "reject": a malformed manifest or
missing `.sig` object should fail closed the same way a bad signature does.
