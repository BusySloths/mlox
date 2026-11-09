"""Common binary object-storage client contract."""
from abc import ABC, abstractmethod


class AbstractObjectStorageClient(ABC):
    """Operations on existing buckets; provider errors propagate to the caller."""

    @abstractmethod
    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        """Return object keys in a bucket whose names start with prefix."""

    @abstractmethod
    def read_bytes(self, bucket: str, key: str) -> bytes:
        """Read an object in full, raising if it does not exist."""

    @abstractmethod
    def write_bytes(self, bucket: str, key: str, data: bytes) -> None:
        """Create or replace an object with binary data."""
