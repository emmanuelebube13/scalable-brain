"""StorageBackend interface (FND-001). See STORAGE_AND_QUEUE_ABSTRACTION.md §1."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class StorageBackend(ABC):
    @abstractmethod
    def put_object(self, key: str, local_path: str, *, encrypt: bool = True) -> None: ...

    @abstractmethod
    def get_object(self, key: str, local_path: str) -> None: ...

    @abstractmethod
    def head(self, key: str) -> dict:
        """{size, sha256, encrypted: bool, ...}."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def list(self, prefix: str) -> Iterable[str]: ...

    @abstractmethod
    def sha256(self, key: str) -> str:
        """Hash of the stored object (round-trip verification)."""

    @abstractmethod
    def atomic_pointer_update(self, pointer_key: str, payload: dict) -> None:
        """Write a pointer (e.g. latest.json) atomically (write-temp + rename)."""

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None:
        """Remove all objects under a prefix (cleanup partial/old versions)."""
