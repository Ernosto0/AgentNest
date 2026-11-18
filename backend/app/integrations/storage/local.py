"""Local filesystem backend (development, demo, mock provider).

``public_fetch_url`` returns ``localmedia:{key}?exp=<unix seconds>``, an opaque reference that
only the mock provider understands (plan.md G3): the mock reads the JPEG back through this
storage. The Meta adapter refuses the local backend, because Meta needs a public URL.
"""

import io
import os
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, cast

from app.core.clock import Clock
from app.integrations.storage.base import StorageObjectNotFound, validate_key

LOCAL_URL_SCHEME = "localmedia:"


class _BoundedReader(io.RawIOBase):
    """Read at most ``remaining`` bytes from an underlying seekable stream."""

    def __init__(self, stream: BinaryIO, remaining: int) -> None:
        self._stream = stream
        self._remaining = remaining

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("read of closed stream")
        if self._remaining <= 0 or size == 0:
            return b""
        to_read = self._remaining if size < 0 else min(size, self._remaining)
        data = self._stream.read(to_read)
        self._remaining -= len(data)
        return data

    def close(self) -> None:
        if not self.closed:
            try:
                self._stream.close()
            finally:
                super().close()


class LocalMediaStorage:
    backend = "local"

    def __init__(self, root: Path, clock: Clock) -> None:
        self._root = root.resolve()
        self._clock = clock

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self._root / key).resolve()
        # Defence in depth: the key regex already excludes ``..`` and absolute paths.
        if not path.is_relative_to(self._root):
            raise ValueError("storage key escapes the storage root")
        return path

    def put(self, key: str, data: BinaryIO, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as out:
                shutil.copyfileobj(data, out)
            Path(tmp_name).replace(path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def open(self, key: str) -> BinaryIO:
        try:
            return self._path(key).open("rb")
        except FileNotFoundError as exc:
            raise StorageObjectNotFound(key) from exc

    def open_range(self, key: str, start: int, length: int) -> BinaryIO:
        if start < 0 or length <= 0:
            raise ValueError("range start must be >= 0 and length must be > 0")
        stream = self.open(key)
        try:
            stream.seek(start)
        except BaseException:
            stream.close()
            raise
        return cast(BinaryIO, _BoundedReader(stream, length))

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def public_fetch_url(self, key: str, ttl_s: int) -> str:
        validate_key(key)
        expires = self._clock.now() + timedelta(seconds=ttl_s)
        return f"{LOCAL_URL_SCHEME}{key}?exp={int(expires.timestamp())}"


def parse_local_url(url: str) -> tuple[str, int]:
    """Split a ``localmedia:`` reference into ``(key, expires_unix)``. Used by the mock."""
    if not url.startswith(LOCAL_URL_SCHEME) or "?exp=" not in url:
        raise ValueError("not a localmedia URL")
    key, _, exp = url[len(LOCAL_URL_SCHEME) :].partition("?exp=")
    return validate_key(key), int(exp)
