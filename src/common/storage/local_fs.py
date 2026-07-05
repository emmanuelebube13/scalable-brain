"""LocalFSBackend — local-filesystem StorageBackend (FND-001 default).

Reproduces production semantics: immutable versioned objects, atomic pointer update
(write-temp + os.replace), SHA256 round-trip, encryption-intent flag (local has no SSE,
so head().encrypted is False — honest, not faked).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from typing import Iterable, List

from .base import StorageBackend


class LocalFSBackend(StorageBackend):
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key: str) -> str:
        return os.path.join(self.root, key)

    def put_object(self, key: str, local_path: str, *, encrypt: bool = True) -> None:
        dst = self._path(key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        # Immutable versions: never overwrite an existing object silently.
        if os.path.exists(dst):
            raise FileExistsError(f"Object already exists (immutable): {key}")
        shutil.copy2(local_path, dst)
        # Record encryption intent (local has no SSE) alongside the object.
        with open(dst + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump({"encrypt_intent": bool(encrypt), "encrypted": False}, fh)

    def get_object(self, key: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        shutil.copy2(self._path(key), local_path)

    def head(self, key: str) -> dict:
        p = self._path(key)
        if not os.path.exists(p):
            raise FileNotFoundError(key)
        meta = {}
        if os.path.exists(p + ".meta.json"):
            with open(p + ".meta.json", encoding="utf-8") as fh:
                meta = json.load(fh)
        return {
            "size": os.path.getsize(p),
            "sha256": self.sha256(key),
            "encrypted": bool(meta.get("encrypted", False)),
            "encrypt_intent": bool(meta.get("encrypt_intent", False)),
        }

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def list(self, prefix: str) -> Iterable[str]:
        base = self._path(prefix)
        out: List[str] = []
        if os.path.isdir(base):
            for dirpath, _, files in os.walk(base):
                for f in files:
                    if f.endswith(".meta.json"):
                        continue
                    full = os.path.join(dirpath, f)
                    out.append(os.path.relpath(full, self.root))
        return sorted(out)

    def sha256(self, key: str) -> str:
        h = hashlib.sha256()
        with open(self._path(key), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def atomic_pointer_update(self, pointer_key: str, payload: dict) -> None:
        dst = self._path(pointer_key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)  # atomic on POSIX

    def delete_prefix(self, prefix: str) -> None:
        base = self._path(prefix)
        if os.path.isdir(base):
            shutil.rmtree(base)
        elif os.path.exists(base):
            os.remove(base)
