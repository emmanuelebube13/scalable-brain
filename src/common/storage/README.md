# Object Storage — Upload Guide (FND-001)

How to upload artifacts to the object store (Google Cloud Storage in production,
local filesystem in dev) **and put them in a folder**.

> **TL;DR** — Always go through `build_storage()`, never a vendor SDK. A "folder" is
> just a `/`-separated prefix in the object **key**. To upload into
> `models/gatekeeper/2026-06-26/`, you pass that path as part of the key:
> `storage.put_object("models/gatekeeper/2026-06-26/champion_model.pkl", local_path)`.

---

## 1. The one rule: folders are key prefixes

GCS has **no real directories**. The bucket is a flat key→bytes map. What looks like a
folder in the console is just the text before the last `/` in an object's key.

```
key = "models/gatekeeper/2026-06-26T14-00Z-a1b2c3d4/champion_model.pkl"
       └──────────────── "folder" (prefix) ───────────────┘ └── filename ──┘
```

- You **never** "create a folder" first. Uploading an object with a `/` in its key
  makes the folder appear automatically.
- An empty folder cannot exist — a folder exists only as long as ≥1 object has that prefix.

## 2. Canonical bucket layout (use these prefixes)

Defined in `docs/implementation-roadmap/00-foundational-and-cross-cutting/tasks/01-provision-object-storage.md`:

```
scalable-brain-artifacts/
  models/<model_id>/<version>/        # the model bundle (immutable, versioned)
    champion_model.pkl
    champion_preprocessor.pkl
    champion_manifest.json            # features, thresholds, sha256
  models/latest.json                  # pointer → current version (mutable, written LAST)
  configs/layer2_strategies/<version>/
  configs/runtime/<system>/<version>/
  performance/daily/<YYYY-MM-DD>/
  performance/reports/<run_id>/
```

`<version>` convention: `2026-06-26T14-00Z-<sha256[:8]>` (timestamp + short hash) so every
version is unique and sortable.

## 3. Upload from Python (the supported way)

`build_storage()` reads `STORAGE_PROVIDER` from `.env` and returns the right backend
(`gcs` in production, `local` in dev). **Your code is identical either way.**

```python
from dotenv import load_dotenv
from src.common.storage import build_storage

load_dotenv()                       # picks up STORAGE_PROVIDER, GCS_BUCKET, creds
storage = build_storage()

# Upload ONE file into a folder — the folder is the prefix in the key:
storage.put_object(
    "models/gatekeeper/2026-06-26T14-00Z-a1b2c3d4/champion_model.pkl",  # key (with folder)
    "models/champion_model.pkl",                                         # local file to upload
    encrypt=True,
)
```

### Upload a whole bundle into one folder

```python
import os

version = "2026-06-26T14-00Z-a1b2c3d4"
prefix = f"models/gatekeeper/{version}"          # the destination "folder"
local_dir = "models"

for filename in ("champion_model.pkl", "champion_preprocessor.pkl", "champion_manifest.json"):
    storage.put_object(
        f"{prefix}/{filename}",                  # key = folder + "/" + filename
        os.path.join(local_dir, filename),
        encrypt=True,
    )
```

### Correct publish ordering (MODEL-007 contract)

Do **not** flip `latest.json` until every file is uploaded and SHA256-verified —
otherwise a consumer could read a pointer to a half-uploaded bundle.

```python
# 1. upload every artifact into the version folder
for filename in bundle_files:
    storage.put_object(f"{prefix}/{filename}", local_path(filename))

# 2. round-trip verify each one against the local hash BEFORE advancing the pointer
for filename in bundle_files:
    if storage.sha256(f"{prefix}/{filename}") != local_sha256(filename):
        storage.delete_prefix(prefix)            # abort: remove the bad partial version
        raise RuntimeError("integrity check failed; pointer NOT advanced")

# 3. flip the pointer LAST (atomic)
storage.atomic_pointer_update("models/latest.json", {
    "model_id": "gatekeeper",
    "version": version,
    "sha256": local_sha256("champion_manifest.json"),
    "published_at": "2026-06-26T14:00:00Z",
})
```

## 4. The API surface (`StorageBackend`)

| Method | Purpose |
|--------|---------|
| `put_object(key, local_path, *, encrypt=True)` | Upload a file. **Immutable** — re-uploading the same key raises `FileExistsError`. The folder is the prefix in `key`. |
| `get_object(key, local_path)` | Download an object to a local file. |
| `head(key)` | Metadata: `{size, sha256, encrypted, ...}`. |
| `exists(key)` | `True`/`False`. |
| `list(prefix)` | List object keys under a folder/prefix. |
| `sha256(key)` | SHA256 of the **stored** bytes (round-trip integrity check). |
| `atomic_pointer_update(key, payload)` | Overwrite a JSON pointer (e.g. `latest.json`) atomically. The **only** mutable write. |
| `delete_prefix(prefix)` | Delete every object under a folder/prefix (cleanup). |

### Download / list a folder

```python
for key in storage.list("models/gatekeeper/2026-06-26T14-00Z-a1b2c3d4"):
    print(key)
    storage.get_object(key, f"/tmp/pull/{key.split('/')[-1]}")
```

## 5. Important gotchas

- **Immutability:** `put_object` refuses to overwrite an existing key (`FileExistsError`).
  To replace a bundle, write a **new version folder** — never reuse a version path.
- **Only `atomic_pointer_update` overwrites.** Pointers (`latest.json`) are the one thing
  meant to change in place.
- **Leading slashes:** don't start a key with `/` — use `models/...`, not `/models/...`.
- **Encryption:** on GCS every object is encrypted at rest by default, so
  `head()["encrypted"]` is `True`. On the local dev backend it's `False` (honest, not faked).
- **Switching backends is config-only:** set `STORAGE_PROVIDER=local` to write to
  `model-artifacts/` on disk, or `STORAGE_PROVIDER=gcs` + `GCS_BUCKET` for the cloud. No code change.

## 6. Manual upload (console / CLI) — for one-off files

You normally upload from code, but for ad-hoc files:

**Console:** Cloud Storage → Buckets → `scalable-brain-artifacts` → open/create the folder
path → **Upload files**. Typing a folder name in "Create folder" just sets a prefix.

**gcloud CLI** (if installed) — the destination path is the folder:
```bash
gcloud storage cp ./champion_model.pkl \
  gs://scalable-brain-artifacts/models/gatekeeper/2026-06-26T14-00Z-a1b2c3d4/champion_model.pkl
```
> Prefer the Python `build_storage()` path for anything automated — it enforces
> immutability, SHA256 verification, and the `latest.json` protocol that manual uploads skip.

## 7. Configuration reference (`.env`)

```
STORAGE_PROVIDER=gcs                 # gcs | local
GCS_BUCKET=scalable-brain-artifacts
GOOGLE_APPLICATION_CREDENTIALS=/home/emmanuel/Documents/Scalable_Brain/scalable-brain/secrets/system1-rw.json
# dev fallback:
# STORAGE_PROVIDER=local
# STORAGE_LOCAL_ROOT=model-artifacts
```
