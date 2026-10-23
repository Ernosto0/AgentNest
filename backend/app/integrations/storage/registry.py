"""Pick the storage backend from configuration (integrations.md §1)."""

from app.core.clock import Clock
from app.core.config import Settings
from app.integrations.storage.base import MediaStorage
from app.integrations.storage.local import LocalMediaStorage
from app.integrations.storage.s3 import S3MediaStorage


def get_media_storage(settings: Settings, clock: Clock) -> MediaStorage:
    if settings.media_storage_backend == "local":
        return LocalMediaStorage(settings.media_root, clock)
    return S3MediaStorage(
        bucket=settings.s3_bucket,
        endpoint_url=settings.s3_endpoint_url,
        region=settings.s3_region,
        access_key_id=settings.s3_access_key_id.get_secret_value(),
        secret_access_key=settings.s3_secret_access_key.get_secret_value(),
    )
