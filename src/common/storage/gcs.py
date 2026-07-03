"""GCSBackend — Google Cloud Storage adapter (FND-001).

Attaches by config only: set ``STORAGE_PROVIDER=gcs`` + ``GCS_BUCKET`` and provide
credentials via ``GOOGLE_APPLICATION_CREDENTIALS`` (service-account JSON). The
MODEL-007/009 publish path is identical to local — only this backend object differs.

Production semantics preserved from ``LocalFSBackend``:
  * Immutable versioned objects — ``put_object`` refuses to overwrite an existing key
    (enforced atomically via the ``if_generation_match=0`` precondition).
  * Atomic pointer — ``atomic_pointer_update`` is a single-object overwrite (the only
    mutable key); the "upload everything, flip pointer last" ordering lives in MODEL-007.
  * SHA256 round-trip — ``sha256`` re-reads the *stored* bytes and hashes them, so a
    consumer can verify integrity independently of GCS's own CRC32C/MD5.
  * Encryption at rest — GCS encrypts by default (Google-managed keys; CMEK optional),
    so ``head().encrypted`` is True (honest, not faked).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from typing import Iterable, List

from .base import StorageBackend

try:  # google-cloud-storage is only required when STORAGE_PROVIDER=gcs
    from google.cloud import storage  # type: ignore
    from google.api_core import exceptions as gcs_exceptions  # type: ignore
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "GCSBackend requires 'google-cloud-storage'. Add it to requirements.txt "
        "and `pip install google-cloud-storage`."
    ) from exc

_CHUNK = 1 << 20  # 1 MiB


class GCSBackend(StorageBackend):
    def __init__(self, bucket: str):
        if not bucket:
            raise ValueError("GCS_BUCKET is required when STORAGE_PROVIDER=gcs")
        self.bucket_name = bucket
        # Credentials resolved from GOOGLE_APPLICATION_CREDENTIALS (or ADC).
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket)

    def put_object(self, key: str, local_path: str, *, encrypt: bool = True) -> None:
        blob = self._bucket.blob(key)
        try:
            # if_generation_match=0 → upload only if the object does not yet exist,
            # making versioned bundle objects immutable (matches LocalFS behaviour).
            blob.upload_from_filename(local_path, if_generation_match=0)
        except gcs_exceptions.PreconditionFailed as exc:
            raise FileExistsError(f"Object already exists (immutable): {key}") from exc

    def get_object(self, key: str, local_path: str) -> None:
        dst_dir = os.path.dirname(os.path.abspath(local_path))
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)
        blob = self._require_blob(key)
        blob.download_to_filename(local_path)

    def head(self, key: str) -> dict:
        blob = self._require_blob(key)
        return {
            "size": blob.size,
            "sha256": self.sha256(key),
            "encrypted": True,  # GCS is encrypted at rest by default
            "crc32c": blob.crc32c,
            "md5": blob.md5_hash,
            "generation": blob.generation,
        }

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()

    def list(self, prefix: str) -> Iterable[str]:
        out: List[str] = [b.name for b in self._client.list_blobs(self.bucket_name, prefix=prefix)]
        return sorted(out)

    def sha256(self, key: str) -> str:
        """Stream the stored object and hash its bytes (round-trip verification)."""
        blob = self._require_blob(key)
        h = hashlib.sha256()
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            blob.download_to_file(tmp)
            tmp.seek(0)
            for chunk in iter(lambda: tmp.read(_CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()

    def atomic_pointer_update(self, pointer_key: str, payload: dict) -> None:
        """Overwrite the pointer object (e.g. latest.json) in a single upload.

        GCS object uploads are atomic — a reader sees either the old or the new
        object, never a partial one — so this is the cloud analogue of the local
        write-temp + os.replace.
        """
        blob = self._bucket.blob(pointer_key)
        blob.upload_from_string(
            json.dumps(payload, indent=2, sort_keys=True),
            content_type="application/json",
        )

    def delete_prefix(self, prefix: str) -> None:
        for blob in self._client.list_blobs(self.bucket_name, prefix=prefix):
            blob.delete()

    def _require_blob(self, key: str):
        blob = self._bucket.blob(key)
        try:
            blob.reload()  # populates metadata; raises NotFound if absent
        except gcs_exceptions.NotFound as exc:
            raise FileNotFoundError(key) from exc
        return blob
