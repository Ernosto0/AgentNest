"""Pick the storage backend from configuration (integrations.md §1)."""

from app.core.clock import Clock
from app.core.config import Settings
from app.integrations.storage.base import MediaStorage, MediaStorageUnavailable
from app.integrations.storage.local import LocalMediaStorage


def get_media_storage(settings: Settings, clock: Clock) -> MediaStorage:
    if settings.media_storage_backend == "local":
        return LocalMediaStorage(settings.media_root, clock)
    raise MediaStorageUnavailable(
        f"MEDIA_STORAGE_BACKEND={settings.media_storage_backend!r} (S3 arrives in Phase 7)"
    )
