"""Keys derived from a content item. The canonical approval payload joins them in P5-04."""

import uuid


def publish_job_key(content_id: uuid.UUID, version: int) -> str:
    """Dedup key of the ``publish_content`` job (and, with the same shape, of the operation)
    for one version of an item (workflows.md section E step 4)."""
    return f"publish:{content_id}:v{version}"
