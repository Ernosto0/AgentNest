"""A fresh worker sees child/parent ids and published effects committed before a crash."""

import pytest

from app.operations import publish
from tests.helpers.publishing import Crash
from tests.integration.content.test_publish_crash_commits import fresh_state, pub, sweep

__all__ = ["pub"]
pytestmark = [pytest.mark.commits, pytest.mark.invariant("INV-06")]


@pytest.mark.parametrize("after", [1, 2, 3, 4, "publish"])
def test_carousel_crash_survives_real_commits(pub, session_factory, monkeypatch, after):
    item = pub.carousel()
    if after == "publish":
        original_finish = publish._finish

        def die(*_):
            raise Crash()

        monkeypatch.setattr(publish, "_finish", die)
    else:
        original = pub.provider.get_container_status
        reads = 0

        def status(*args):
            nonlocal reads
            reads += 1
            if reads == after:
                raise Crash()
            return original(*args)

        monkeypatch.setattr(pub.provider, "get_container_status", status)
    with pytest.raises(Crash):
        pub.execute(item)
    _, op, containers, posts = fresh_state(session_factory, item.id)
    assert op.status == "in_progress"
    stored = {c.container_id for c in containers}
    assert len(op.provider_ref.get("children", [])) == min(
        3, after if isinstance(after, int) else 3
    )
    assert len(posts) == (1 if after == "publish" else 0)
    if after == "publish":
        monkeypatch.setattr(publish, "_finish", original_finish)
    pub.clock.advance(minutes=16)
    sweep(pub)
    pub.clock.advance(minutes=1)
    assert pub.reconcile(pub.operation(item)).kind == "published"
    row, op, containers, posts = fresh_state(session_factory, item.id)
    assert row.status == "published" and op.status == "succeeded"
    assert len(posts) == 1 and len(containers) == 4
    assert stored <= {c.container_id for c in containers}
    # Before/after T3 crashes both settle against the stored parent; no second publish.
    assert pub.calls.count("publish_container") == 1
