"""Synthetic signed public events, isolation, ordering and actual coordinator context."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.agent.context import assemble
from app.agent.coordinator import claim, fresh, run_activation
from app.agent.models import AgentEvent, AgentThread
from app.agent.tools.broker import BrokerContext, build_default_broker
from app.comments.codec import CommentEvent
from app.comments.models import PublicComment, PublicMedia, PublicThread
from app.comments.service import PublicRead, public_context
from app.demo.simulator import simulate_comment
from app.inbox.ingest import ingest_webhook
from app.inbox.models import InboundEvent
from app.inbox.processing import process_inbound_event
from app.integrations.instagram import webhook_format as wf
from app.integrations.instagram.models import SocialAccount
from app.integrations.llm.fake import FakeLLMProvider
from tests.integration.agent.test_coordinator import deps, result
from tests.integration.agent.test_dm import setup

pytestmark = pytest.mark.commits


def event(clock, **kw):
    return {
        "schema": "synthetic-comment-v1",
        "id": "root",
        "root_id": "root",
        "media_id": "post",
        "author_id": "public-person",
        "text": "Hello, what services do you offer?",
        "version": 1,
        "timestamp": clock.now().isoformat(),
        **kw,
    }


def process(factory, clock, world):
    ctx, account, _, _ = world
    with factory() as db:
        ids = list(db.scalars(select(InboundEvent.id).where(InboundEvent.status == "received")))
    for receipt in ids:
        with factory() as db:
            process_inbound_event(db, clock, ctx.workspace_id, receipt, debounce_seconds=0)


def deliver(factory, clock, world, **kw):
    ctx, _, _, settings = world
    outcome = simulate_comment(factory, clock, settings, ctx.workspace_id, event(clock, **kw))
    process(factory, clock, world)
    return outcome


def context(db, world):
    ctx, account, _, _ = world
    thread = db.scalar(
        select(AgentThread).where(
            AgentThread.surface == "comment", AgentThread.social_account_id == account
        )
    )
    assert thread is not None
    return BrokerContext(ctx, account, thread.id, "comment", "customer")


def test_signed_duplicate_and_coordinator_public_context(session_factory, clock):
    world = setup(session_factory, clock)
    assert (
        deliver(
            session_factory, clock, world, media_verified=True, media_caption="PUBLIC POST"
        ).received
        == 1
    )
    assert (
        deliver(
            session_factory, clock, world, media_verified=True, media_caption="PUBLIC POST"
        ).duplicates
        == 1
    )
    with session_factory() as db:
        ctx = context(db, world)
        assert (
            db.scalar(
                select(func.count())
                .select_from(AgentThread)
                .where(AgentThread.surface == "comment")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(AgentEvent)) == 1
        assert "PUBLIC POST" in assemble(db, clock, ctx).messages[0].content
        assert db.get(AgentThread, ctx.thread_id).customer_identity_id is None
    fake = FakeLLMProvider()
    fake.queue_step(
        result(
            "tool",
            tool_name="public.thread",
            tool_arguments={"limit": 2, "cursor": None},
            call_id="public",
        )
    )
    fake.queue_step(result())
    run_activation(
        deps(session_factory, clock, fake),
        world[0].workspace_id,
        ctx.thread_id,
        build_default_broker(),
    )
    assert len(fake.step_calls) == 2
    assert fake.step_calls[1].observations[0].result["data"]["media"]["caption"] == "PUBLIC POST"
    names = {t.name for t in fake.step_calls[0].tools}
    assert not names & {
        "thread.read",
        "memory.read",
        "memory.write",
        "owner.ask",
        "dm.send",
        "approval.request",
    }


def test_parent_order_versions_tombstones_and_unknown_author(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, id="child", parent_id="root", author_id=None)
    with session_factory() as db:
        parent = db.scalar(select(PublicComment).where(PublicComment.external_id == "root"))
        assert parent.state == "unknown"
    deliver(session_factory, clock, world)
    deliver(session_factory, clock, world, version=3, text="NEW")
    deliver(session_factory, clock, world, version=2, text="OLD")
    deliver(session_factory, clock, world, version=4, state="deleted")
    deliver(session_factory, clock, world, version=5, text="RESURRECT")
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(PublicThread)) == 1
        parent = db.scalar(select(PublicComment).where(PublicComment.external_id == "root"))
        child = db.scalar(select(PublicComment).where(PublicComment.external_id == "child"))
        assert child.parent_id == parent.id and child.author_external_id is None
        assert parent.state == "deleted" and parent.text is None and parent.provider_version == 4


def test_delete_before_create_is_terminal(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, state="deleted", version=3)
    deliver(session_factory, clock, world, version=1)
    with session_factory() as db:
        assert db.scalar(select(PublicComment.state)) == "deleted"
        assert db.scalar(select(func.count()).select_from(AgentThread)) == 0


def test_native_owner_identity_omission_and_conflict(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    deliver(session_factory, clock, world, id="owner", parent_id="root", author_id=world[2])
    deliver(session_factory, clock, world, id="owner", parent_id="root", author_id=None, version=2)
    deliver(
        session_factory, clock, world, id="owner", parent_id="root", author_id="imposter", version=3
    )
    with session_factory() as db:
        row = db.scalar(select(PublicComment).where(PublicComment.external_id == "owner"))
        assert row.is_owner and row.author_external_id == world[2] and row.provider_version == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(AgentEvent)
                .where(AgentEvent.kind == "customer_comment")
            )
            == 1
        )
        assert db.scalar(select(AgentThread.ownership_generation)) == 2
    other = setup(session_factory, clock)
    deliver(session_factory, clock, other, author_id=other[2])
    with session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AgentThread)
                .where(AgentThread.social_account_id == other[1])
            )
            == 0
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"media_id": "other-post"},
        {"root_id": "forged"},
        {"parent_id": "root"},
        {"id": "nested", "parent_id": "child"},
    ],
)
def test_conflicting_media_and_lineage_rejected(session_factory, clock, changes):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    deliver(session_factory, clock, world, version=2, **changes)
    with session_factory() as db:
        assert (
            db.scalar(
                select(PublicComment.provider_version).where(PublicComment.external_id == "root")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(AgentEvent)) == 1


@pytest.mark.parametrize("shape", [None, {}, 1, "bad"])
def test_signed_malformed_and_invalid_signature(session_factory, clock, shape):
    world = setup(session_factory, clock)
    payload = {"object": "instagram", "entry": [{"id": world[2], "synthetic_comments": shape}]}
    raw = wf.serialize(payload)
    with session_factory() as db:
        assert (
            ingest_webhook(db, clock, world[3], "mock", raw, {wf.SIGNATURE_HEADER: "bad"}).status
            == "invalid_signature"
        )
        signature = wf.sign(raw, world[3].mock_instagram_app_secret.get_secret_value())
        assert (
            ingest_webhook(
                db, clock, world[3], "mock", raw, {wf.SIGNATURE_HEADER: signature}
            ).received
            == 0
        )
        assert db.scalar(select(func.count()).select_from(InboundEvent)) == 0


def test_naive_timestamp_and_real_codec_disabled(clock):
    value = event(clock, timestamp="2026-01-01T12:00:00")
    with pytest.raises(ValidationError):
        CommentEvent.model_validate(value)
    payload = {"object": "instagram", "entry": [{"id": "a", "synthetic_comments": [event(clock)]}]}
    assert wf.WebhookCodec("secret").parse_webhook(payload) == []


def test_account_isolation_public_broker_and_stale_cursor(session_factory, clock):
    first, second = setup(session_factory, clock), setup(session_factory, clock)
    deliver(session_factory, clock, first, text="FIRST")
    deliver(session_factory, clock, second, text="SECOND")
    with session_factory() as db:
        ctx = context(db, first)
        data = public_context(db, clock, ctx, PublicRead())
        assert data["media"]["ownership_state"] == "unverified"
        assert data["media"]["caption"] == ""
        assert [r["text"] for r in data["comments"]] == ["FIRST"]
        broker = build_default_broker()
        for name in ("memory.read", "memory.write", "thread.read", "owner.ask"):
            assert (
                broker.dispatch(db, clock, ctx, name=name, version="v1", arguments={}).error
                == "TOOL_FORBIDDEN"
            )
    claimed = claim(deps(session_factory, clock), first[0].workspace_id, ctx.thread_id)
    assert claimed is not None
    deliver(session_factory, clock, first, version=2, text="EDIT")
    with session_factory() as db:
        assert fresh(db, deps(session_factory, clock), claimed) is None
        assert public_context(db, clock, ctx, PublicRead())["event_cursor"] == 2


def test_composite_fk_foreign_media(session_factory, clock):
    first, second = setup(session_factory, clock), setup(session_factory, clock)
    deliver(session_factory, clock, first)
    with session_factory() as db:
        media = db.scalar(select(PublicMedia))
        db.add(
            PublicThread(
                workspace_id=second[0].workspace_id,
                social_account_id=second[1],
                media_id=media.id,
                root_external_id="foreign",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_media_revision_fences_sibling_and_deletion_hides_all_bodies(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, media_verified=True, media_caption="OLD")
    deliver(session_factory, clock, world, id="sibling", root_id="sibling")
    with session_factory() as db:
        public = db.scalar(select(PublicThread).where(PublicThread.root_external_id == "root"))
        thread = db.scalar(select(AgentThread).where(AgentThread.public_thread_id == public.id))
        thread_id = thread.id
    runner = deps(session_factory, clock)
    captured = claim(runner, world[0].workspace_id, thread_id)
    deliver(
        session_factory,
        clock,
        world,
        id="sibling",
        root_id="sibling",
        version=2,
        media_version=2,
        media_verified=True,
        media_caption="NEW",
    )
    with session_factory() as db:
        assert fresh(db, runner, captured) is None
        db.commit()
    deliver(
        session_factory,
        clock,
        world,
        id="sibling",
        root_id="sibling",
        version=3,
        media_version=3,
        media_deleted=True,
    )
    with session_factory() as db:
        ctx = BrokerContext(world[0], world[1], thread_id, "comment", "customer")
        data = public_context(db, clock, ctx, PublicRead())
        assert data["comments"] == [] and data["media"]["caption"] == ""
        assert not db.scalars(select(PublicComment).where(PublicComment.text.is_not(None))).all()


def test_public_retention_and_disconnect_redact_sources(session_factory, clock):
    from datetime import timedelta

    from app.comments.models import SimPublicComment
    from app.comments.privacy import retention_batch
    from app.operations.accounts import disconnect

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, media_verified=True, media_caption="PUBLIC")
    with session_factory() as db:
        assert retention_batch(db, clock, clock.now() + timedelta(seconds=1), 1) == (2, 1)
        db.commit()
        row = db.scalar(select(PublicComment))
        assert row.text is None and row.author_external_id is None and row.state == "deleted"
        assert db.scalar(select(SimPublicComment.value)) is None
    other = setup(session_factory, clock)
    deliver(session_factory, clock, other, media_verified=True, media_caption="ERASE")
    with session_factory() as db:
        disconnect(db, clock, other[0], other[1], delete_conversation_data=True)
        assert (
            db.scalar(select(PublicMedia.caption).where(PublicMedia.social_account_id == other[1]))
            is None
        )
        assert (
            db.scalar(select(PublicComment.text).where(PublicComment.social_account_id == other[1]))
            is None
        )


def test_equal_revision_delete_wins_and_public_pagination(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    for index in range(4):
        deliver(session_factory, clock, world, id=f"child{index}", parent_id="root")
    with session_factory() as db:
        ctx = context(db, world)
        page = public_context(db, clock, ctx, PublicRead(limit=2))
        assert len(page["comments"]) == 2 and page["next_cursor"]
        following = public_context(
            db, clock, ctx, PublicRead(limit=8, cursor=uuid.UUID(page["next_cursor"]))
        )
        assert len(following["comments"]) == 3 and following["next_cursor"] is None
        assert not ({r["id"] for r in page["comments"]} & {r["id"] for r in following["comments"]})
    deliver(session_factory, clock, world, state="deleted")
    with session_factory() as db:
        assert (
            db.scalar(select(PublicComment.state).where(PublicComment.external_id == "root"))
            == "deleted"
        )


def test_current_public_source_pinned_beyond_first_page(session_factory, clock, monkeypatch):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, text="Merhaba")
    for index in range(10):
        deliver(
            session_factory, clock, world, id=f"reply-{index}", parent_id="root", text="Merhaba"
        )
    monkeypatch.setattr("app.comments.service.new_id", lambda: uuid.UUID(int=(1 << 128) - 1))
    deliver(
        session_factory,
        clock,
        world,
        id="current",
        parent_id="root",
        text="Hello, what services do you offer? CURRENT SOURCE",
    )
    with session_factory() as db:
        ctx = context(db, world)
        from app.identity.models import Workspace

        ws = db.get(Workspace, ctx.workspace.workspace_id)
        ws.default_locale, ws.reply_languages = "tr", ["en", "tr"]
        db.flush()
        value = assemble(db, clock, ctx)
        assert value.language == "en"
        assert "CURRENT SOURCE" in str(value.messages)
        assert len(public_context(db, clock, ctx, PublicRead())["comments"]) == 5
        assert not any(
            "CURRENT SOURCE" in r["text"]
            for r in public_context(db, clock, ctx, PublicRead())["comments"]
        )
        db.commit()
    fake = FakeLLMProvider()
    fake.queue_step(result())
    run_activation(
        deps(session_factory, clock, fake),
        world[0].workspace_id,
        ctx.thread_id,
        build_default_broker(),
    )
    assert "CURRENT SOURCE" in str(fake.step_calls[0].messages)
    assert '"reply_language": "en"' in str(fake.step_calls[0].messages)


def test_retention_rechecks_fresh_edit_after_account_lock(session_factory, clock, monkeypatch):
    from datetime import timedelta

    from app.comments import privacy

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    lock = privacy.scoped_account
    cutoff = clock.now() + timedelta(seconds=1)

    def edit_before_lock(db, workspace, account, **kw):
        with session_factory() as other:
            row = other.scalar(select(PublicComment))
            row.text = "FRESH"
            row.updated_at = cutoff + timedelta(seconds=1)
            other.commit()
        return lock(db, workspace, account, **kw)

    monkeypatch.setattr(privacy, "scoped_account", edit_before_lock)
    with session_factory() as db:
        assert privacy.retention_batch(db, clock, cutoff, 1) == (0, 1)
        assert db.scalar(select(PublicComment.text)) == "FRESH"


def test_deleted_source_and_media_caches_cannot_resurrect(session_factory, clock):
    from app.comments.models import SimPublicComment

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, state="deleted", version=2)
    deliver(session_factory, clock, world, version=3, text="RESURRECT")
    with session_factory() as db:
        assert not db.scalars(select(InboundEvent).where(InboundEvent.payload.is_not(None))).all()
        assert not db.scalars(
            select(SimPublicComment).where(SimPublicComment.value.is_not(None))
        ).all()
    deliver(session_factory, clock, world, id="sibling", root_id="sibling", text="BODY")
    deliver(session_factory, clock, world, version=4, media_deleted=True)
    deliver(session_factory, clock, world, id="late", root_id="late", text="LATE BODY")
    with session_factory() as db:
        assert not db.scalars(select(InboundEvent).where(InboundEvent.payload.is_not(None))).all()
        assert not db.scalars(
            select(SimPublicComment).where(SimPublicComment.value.is_not(None))
        ).all()
        assert not db.scalars(select(PublicComment).where(PublicComment.text.is_not(None))).all()


def test_caption_expiry_keeps_fresh_public_comments_visible(session_factory, clock):
    from datetime import timedelta

    from app.comments.privacy import retention_batch

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, media_verified=True, media_caption="OLD CAPTION")
    with session_factory() as db:
        media = db.scalar(select(PublicMedia))
        media.updated_at = clock.now() - timedelta(days=400)
        db.commit()
    deliver(session_factory, clock, world, id="fresh", parent_id="root", text="FRESH COMMENT")
    with session_factory() as db:
        assert retention_batch(db, clock, clock.now() - timedelta(days=365), 10) == (1, 1)
        data = public_context(db, clock, context(db, world), PublicRead())
        assert data["media"]["state"] == "visible" and data["media"]["caption"] == ""
        assert "FRESH COMMENT" in str(data["comments"])


def test_composite_parent_fk_rejects_other_media_same_account(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    deliver(session_factory, clock, world, id="second", root_id="second", media_id="other")
    with session_factory() as db:
        first = db.scalar(select(PublicComment).where(PublicComment.external_id == "root"))
        second = db.scalar(select(PublicComment).where(PublicComment.external_id == "second"))
        first.parent_id = second.id
        with pytest.raises(IntegrityError):
            db.flush()


def test_composite_media_fk_rejects_other_account_same_workspace(session_factory, clock):
    world = setup(session_factory, clock)
    deliver(session_factory, clock, world)
    with session_factory() as db:
        sibling = SocialAccount(
            workspace_id=world[0].workspace_id,
            provider_kind="mock",
            external_account_id=uuid.uuid4().hex,
            status="disconnected",
        )
        db.add(sibling)
        db.flush()
        media = db.scalar(select(PublicMedia))
        db.add(
            PublicThread(
                workspace_id=world[0].workspace_id,
                social_account_id=sibling.id,
                media_id=media.id,
                root_external_id="foreign",
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()


def test_restart_rereads_public_checkpoint_and_duplicate_wake_is_idle(
    session_factory, clock, monkeypatch
):
    from app.agent import coordinator

    world = setup(session_factory, clock)
    deliver(session_factory, clock, world, text="OLD PUBLIC BODY")
    with session_factory() as db:
        ctx = context(db, world)
    fake = FakeLLMProvider()
    fake.queue_step(
        result(
            "tool",
            tool_name="public.thread",
            tool_arguments={"limit": 2, "cursor": None},
            call_id="public",
        )
    )
    original = coordinator.claim
    calls = 0

    def claim_once(*args, **kw):
        nonlocal calls
        calls += 1
        return original(*args, **kw) if calls == 1 else None

    with monkeypatch.context() as patch:
        patch.setattr(coordinator, "claim", claim_once)
        run_activation(
            deps(session_factory, clock, fake),
            world[0].workspace_id,
            ctx.thread_id,
            build_default_broker(),
        )
    assert len(fake.step_calls) == 1
    deliver(session_factory, clock, world, version=2, text="NEW PUBLIC BODY")
    restarted = FakeLLMProvider()
    restarted.queue_step(result())
    runner = deps(session_factory, clock, restarted)
    run_activation(runner, world[0].workspace_id, ctx.thread_id, build_default_broker())
    assert restarted.step_calls[0].observations[0].name == "public.thread"
    assert "NEW PUBLIC BODY" in str(restarted.step_calls[0].observations)
    assert "OLD PUBLIC BODY" not in str(restarted.step_calls[0])
    run_activation(runner, world[0].workspace_id, ctx.thread_id, build_default_broker())
    assert len(restarted.step_calls) == 1


@pytest.mark.parametrize("tail", ["\U0001f642", '<\n"'])
def test_max_public_previews_fit_broker_and_actual_second_model_request(
    session_factory, clock, tail
):
    import json

    from app.agent.models import AgentSession

    world = setup(session_factory, clock)
    body = ("Hello " + tail * 2000)[:2000]
    caption = (tail * 2000)[:2000]
    author = "\U0001f642" * 200
    for index in range(8):
        deliver(
            session_factory,
            clock,
            world,
            id="root" if index == 0 else f"child-{index}",
            parent_id=None if index == 0 else "root",
            text=body,
            author_id=author,
            media_verified=True,
            media_caption=caption,
        )
    broker = build_default_broker()
    with session_factory() as db:
        ctx = context(db, world)
        tool = broker.dispatch(
            db,
            clock,
            ctx,
            name="public.thread",
            version="v1",
            arguments={"limit": 8, "cursor": None},
        )
        assert tool.ok and len(tool.data["comments"]) == 8
        assert len(json.dumps(tool.data, ensure_ascii=False).encode("utf-8")) < 16384
        assert len(tool.data["media"]["caption"].encode("utf-8")) <= 320
        assert all(len(item["text"].encode("utf-8")) <= 280 for item in tool.data["comments"])
        assert all(
            item["author_id"] is None and item["author_id_omitted"]
            for item in tool.data["comments"]
        )
        assert all(
            row.text == body and row.author_external_id == author
            for row in db.scalars(select(PublicComment))
        )
        assert db.scalar(select(PublicMedia.caption)) == caption
    fake = FakeLLMProvider()
    fake.queue_step(
        result(
            "tool",
            tool_name="public.thread",
            tool_arguments={"limit": 8, "cursor": None},
            call_id="maximum-public-read",
        )
    )
    fake.queue_step(result())
    run_activation(deps(session_factory, clock, fake), world[0].workspace_id, ctx.thread_id, broker)
    # Both actual requests passed the coordinator's 16,000-byte envelope guard,
    # including the second request with the maximum public read observation.
    assert len(fake.step_calls) == 2
    assert fake.step_calls[1].observations[0].result["ok"]
    with session_factory() as db:
        assert db.scalar(select(AgentSession.status)) == "completed"
