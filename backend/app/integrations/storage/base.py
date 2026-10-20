"""The ``MediaStorage`` interface and the storage key rules (ADR-015).

A key is ``{workspace_id}/{yyyy}/{mm}/{media_id}.{ext}`` and is built only from IDs and the
upload instant, never from a file name. Every backend validates a key against ``KEY_RE``
before touching storage, so a crafted key cannot escape the storage root.
"""

import re
import uuid
from datetime import datetime
from typing import BinaryIO, Protocol

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
KEY_RE = re.compile(rf"^{_UUID}/[0-9]{{4}}/(?:0[1-9]|1[0-2])/{_UUID}\.(?:jpg|png)$")
KEY_EXTENSIONS = frozenset({"jpg", "png"})


class InvalidStorageKey(ValueError):
    """The key does not match ``KEY_RE`` (possible path traversal)."""


class StorageObjectNotFound(FileNotFoundError):
    """No object is stored under the key."""


class MediaStorageUnavailable(RuntimeError):
    """The configured backend is unknown or not built yet."""


def build_key(workspace_id: uuid.UUID, media_id: uuid.UUID, now: datetime, ext: str = "jpg") -> str:
    """The key of a new object. ``now`` is the (UTC) upload instant from the injected clock."""
    if ext not in KEY_EXTENSIONS:
        raise InvalidStorageKey(f"unsupported extension: {ext!r}")
    return f"{workspace_id}/{now:%Y}/{now:%m}/{media_id}.{ext}"


def validate_key(key: str) -> str:
    """Return ``key`` unchanged, or raise ``InvalidStorageKey``."""
    if not isinstance(key, str) or KEY_RE.fullmatch(key) is None:
        raise InvalidStorageKey("invalid storage key")
    return key


class MediaStorage(Protocol):
    backend: str

    def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        """Store the object, replacing any existing one atomically."""
        ...

    def open(self, key: str) -> BinaryIO:
        """Open the object for reading (binary). Raises ``StorageObjectNotFound``."""
        ...

    def delete(self, key: str) -> None:
        """Delete the object. Deleting a missing object is not an error."""
        ...

    def public_fetch_url(self, key: str, ttl_s: int) -> str:
        """A URL from which the publishing provider can fetch the object for ``ttl_s`` seconds."""
        ...
