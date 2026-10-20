"""What ``load_handlers`` registers for content (the API and the worker both call it)."""

from app.approvals import callbacks
from app.jobs.registry import get_handler


def test_content_item_is_an_approval_subject() -> None:
    handler = callbacks.get("content_item")
    assert handler is not None
    assert handler.current_version.__module__ == "app.content.subject"
    assert handler.on_decided.__module__ == "app.content.subject"


def test_publish_content_can_be_enqueued() -> None:
    handler = get_handler("publish_content")
    assert handler is not None
    assert handler.max_attempts == 5
    # P5-06 replaces the placeholder with the executor; this test then moves with it.
    assert handler.func.__module__ == "app.operations.jobs"
