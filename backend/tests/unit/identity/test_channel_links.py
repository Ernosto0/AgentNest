"""Unit tests for owner channel identity linking (P9-01 / ADR-012, Phase 9 Session 01).

Covers:
- Cryptographically secure 8-character code generation, hashing, and 15-minute expiry.
- Throttling to 3 active codes per user.
- Code redemption, case/whitespace normalization, and replay prevention.
- Single-use and expiration enforcement.
- Automatic unlinking of superseded active links for the same channel identity.
- User-initiated unlinking from web settings (with ownership and role-based permissions).
- Bot-initiated unlinking via /unlink.
- Channel user resolution to User, Workspace, and ChannelLink.
- Comprehensive audit event recording.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import list_entries
from app.core.clock import FrozenClock
from app.core.context import ActorRef, WorkspaceContext
from app.core.db import clear_tenant_context, set_tenant_context
from app.core.errors import AppError
from app.identity.channels import (
    generate_link_code,
    hash_link_code,
    redeem_link_code,
    resolve_channel_user,
    unlink_by_channel,
    unlink_by_user,
)
from app.identity.models import ChannelLinkCode
from tests.factories import workspace_with_members


@pytest.fixture
def test_clock() -> FrozenClock:
    return FrozenClock()


def test_generate_link_code_success(db_session: Session, test_clock: FrozenClock) -> None:
    ws, users = workspace_with_members(db_session, name="Owner Channel WS")
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)

    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, expires_at = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    assert len(code) == 8
    assert code.isalnum()
    assert code.isupper()
    assert expires_at == test_clock.now() + timedelta(minutes=15)

    # Verify code record in DB
    code_rec = db_session.scalar(
        select(ChannelLinkCode).where(
            ChannelLinkCode.workspace_id == ws.id,
            ChannelLinkCode.user_id == owner.id,
            ChannelLinkCode.channel == "telegram",
        )
    )
    assert code_rec is not None
    assert code_rec.code_hash == hash_link_code(code)
    assert code_rec.used_at is None
    assert code_rec.expires_at == expires_at

    # Verify audit log
    entries = list_entries(db_session, workspace_id=ws.id, action="channel_link.code_generated")
    assert len(entries) == 1
    assert entries[0].metadata_["channel"] == "telegram"
    assert entries[0].metadata_["actor_user_id"] == str(owner.id)


def test_generate_link_code_rejects_unsupported_channel(
    db_session: Session, test_clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session)
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(users["owner"].id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    with pytest.raises(AppError) as exc_info:
        generate_link_code(db_session, test_clock, ctx, channel="whatsapp")
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_generate_link_code_throttling_at_limit(
    db_session: Session, test_clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    # Generate 3 valid active codes
    for _ in range(3):
        generate_link_code(db_session, test_clock, ctx, channel="telegram")

    # 4th attempt must be throttled
    with pytest.raises(AppError) as exc_info:
        generate_link_code(db_session, test_clock, ctx, channel="telegram")
    assert exc_info.value.code == "TOO_MANY_ACTIVE_CODES"

    # Advance clock past expiry (15 mins) -> previous codes become inactive
    test_clock.advance(seconds=15 * 60 + 1)

    # Now generating a new code succeeds
    code4, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")
    assert len(code4) == 8


def test_redeem_link_code_success(db_session: Session, test_clock: FrozenClock) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    # Redeem from external channel
    clear_tenant_context(db_session)
    link = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_123456",
        channel_chat_id="chat_123456",
        raw_code=code,
        channel_username="owner_telegram",
    )

    assert link.workspace_id == ws.id
    assert link.user_id == owner.id
    assert link.channel == "telegram"
    assert link.channel_user_id == "tg_123456"
    assert link.channel_chat_id == "chat_123456"
    assert link.channel_username == "owner_telegram"
    assert link.status == "active"
    assert link.linked_at == test_clock.now()

    # Code record is marked used
    code_rec = db_session.scalar(
        select(ChannelLinkCode).where(ChannelLinkCode.code_hash == hash_link_code(code))
    )
    assert code_rec is not None
    assert code_rec.used_at == test_clock.now()

    # Verify audit log
    entries = list_entries(db_session, workspace_id=ws.id, action="channel_link.created")
    assert len(entries) == 1
    assert entries[0].metadata_["channel_user_id"] == "tg_123456"


def test_redeem_link_code_case_and_whitespace_insensitivity(
    db_session: Session, test_clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session)
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(users["owner"].id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    clear_tenant_context(db_session)
    link = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_case_test",
        channel_chat_id="chat_case_test",
        raw_code=f"  {code.lower()}  ",
    )
    assert link.status == "active"


def test_redeem_link_code_invalid(db_session: Session, test_clock: FrozenClock) -> None:
    clear_tenant_context(db_session)
    with pytest.raises(AppError) as exc_info:
        redeem_link_code(
            db_session,
            test_clock,
            channel="telegram",
            channel_user_id="tg_invalid",
            channel_chat_id="chat_invalid",
            raw_code="INVALID1",
        )
    assert exc_info.value.code == "LINK_CODE_INVALID"


def test_redeem_link_code_expired(db_session: Session, test_clock: FrozenClock) -> None:
    ws, users = workspace_with_members(db_session)
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(users["owner"].id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    # Advance clock past 15 min expiry
    test_clock.advance(seconds=15 * 60 + 5)

    clear_tenant_context(db_session)
    with pytest.raises(AppError) as exc_info:
        redeem_link_code(
            db_session,
            test_clock,
            channel="telegram",
            channel_user_id="tg_exp",
            channel_chat_id="chat_exp",
            raw_code=code,
        )
    assert exc_info.value.code == "LINK_CODE_EXPIRED"


def test_redeem_link_code_replay_rejected(db_session: Session, test_clock: FrozenClock) -> None:
    ws, users = workspace_with_members(db_session)
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(users["owner"].id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    clear_tenant_context(db_session)
    # First redemption succeeds
    redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_replay",
        channel_chat_id="chat_replay",
        raw_code=code,
    )

    # Second redemption must be rejected with LINK_CODE_USED
    with pytest.raises(AppError) as exc_info:
        redeem_link_code(
            db_session,
            test_clock,
            channel="telegram",
            channel_user_id="tg_replay",
            channel_chat_id="chat_replay",
            raw_code=code,
        )
    assert exc_info.value.code == "LINK_CODE_USED"


def test_redeem_link_code_unlinks_previous_channel_identity(
    db_session: Session, test_clock: FrozenClock
) -> None:
    ws1, users1 = workspace_with_members(db_session, name="Workspace 1")
    ws2, users2 = workspace_with_members(db_session, name="Workspace 2")

    # User 1 links Telegram identity "tg_unique_person"
    set_tenant_context(db_session, ws1.id)
    ctx1 = WorkspaceContext(
        workspace_id=ws1.id,
        actor=ActorRef.user(users1["owner"].id),
        role="owner",
        timezone=ws1.timezone,
        locale="tr",
        is_demo=False,
    )
    code1, _ = generate_link_code(db_session, test_clock, ctx1, channel="telegram")

    clear_tenant_context(db_session)
    link1 = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_unique_person",
        channel_chat_id="chat_1",
        raw_code=code1,
    )
    assert link1.status == "active"

    # User 2 in Workspace 2 links the SAME Telegram identity "tg_unique_person"
    set_tenant_context(db_session, ws2.id)
    ctx2 = WorkspaceContext(
        workspace_id=ws2.id,
        actor=ActorRef.user(users2["owner"].id),
        role="owner",
        timezone=ws2.timezone,
        locale="tr",
        is_demo=False,
    )
    code2, _ = generate_link_code(db_session, test_clock, ctx2, channel="telegram")

    clear_tenant_context(db_session)
    test_clock.advance(seconds=60)
    link2 = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_unique_person",
        channel_chat_id="chat_2",
        raw_code=code2,
    )
    assert link2.status == "active"
    assert link2.workspace_id == ws2.id

    # Verify link1 in ws1 is unlinked
    set_tenant_context(db_session, ws1.id)
    db_session.refresh(link1)
    assert link1.status == "unlinked"
    assert link1.unlinked_at is not None

    # Verify unlinked audit log in ws1
    unlinked_entries = list_entries(db_session, workspace_id=ws1.id, action="channel_link.unlinked")
    assert len(unlinked_entries) == 1
    assert unlinked_entries[0].metadata_["initiated_by"] == "bot"


def test_redeem_link_code_unlinks_previous_user_channel_in_same_workspace(
    db_session: Session, test_clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]

    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )

    code1, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")
    clear_tenant_context(db_session)
    link1 = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_phone_old",
        channel_chat_id="chat_phone_old",
        raw_code=code1,
    )
    assert link1.status == "active"

    # Same user generates code 2 and links from a different telegram account
    set_tenant_context(db_session, ws.id)
    code2, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")
    clear_tenant_context(db_session)
    test_clock.advance(seconds=120)
    link2 = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_phone_new",
        channel_chat_id="chat_phone_new",
        raw_code=code2,
    )

    assert link2.status == "active"
    set_tenant_context(db_session, ws.id)
    db_session.refresh(link1)
    assert link1.status == "unlinked"
    assert link1.unlinked_at is not None


def test_unlink_by_user_success_and_permissions(
    db_session: Session, test_clock: FrozenClock
) -> None:
    ws, users = workspace_with_members(db_session, roles=("owner", "staff"))
    owner = users["owner"]
    staff = users["staff"]

    set_tenant_context(db_session, ws.id)
    owner_ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    code, _ = generate_link_code(db_session, test_clock, owner_ctx, channel="telegram")

    clear_tenant_context(db_session)
    link = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_unlink_test",
        channel_chat_id="chat_unlink_test",
        raw_code=code,
    )

    set_tenant_context(db_session, ws.id)

    # 1. Staff cannot unlink owner's channel link
    staff_ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(staff.id),
        role="staff",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    with pytest.raises(AppError) as exc_info:
        unlink_by_user(db_session, test_clock, staff_ctx, link.id)
    assert exc_info.value.code == "FORBIDDEN"

    # 2. Owner can unlink their own link
    unlink_by_user(db_session, test_clock, owner_ctx, link.id)
    db_session.refresh(link)
    assert link.status == "unlinked"
    assert link.unlinked_at == test_clock.now()

    # Verify audit log
    entries = list_entries(db_session, workspace_id=ws.id, action="channel_link.unlinked")
    assert len(entries) == 1
    assert entries[0].metadata_["initiated_by"] == "web"

    # 3. Second unlink raises CHANNEL_LINK_NOT_FOUND
    with pytest.raises(AppError) as exc_not_found:
        unlink_by_user(db_session, test_clock, owner_ctx, link.id)
    assert exc_not_found.value.code == "CHANNEL_LINK_NOT_FOUND"


def test_unlink_by_channel(db_session: Session, test_clock: FrozenClock) -> None:
    ws, users = workspace_with_members(db_session)
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(users["owner"].id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    code, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    clear_tenant_context(db_session)
    link = redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_bot_unlink",
        channel_chat_id="chat_bot_unlink",
        raw_code=code,
    )

    # Bot receives /unlink
    unlink_by_channel(db_session, test_clock, channel="telegram", channel_user_id="tg_bot_unlink")

    set_tenant_context(db_session, ws.id)
    db_session.refresh(link)
    assert link.status == "unlinked"

    # Subsequent /unlink is safe no-op
    unlink_by_channel(db_session, test_clock, channel="telegram", channel_user_id="tg_bot_unlink")


def test_resolve_channel_user(db_session: Session, test_clock: FrozenClock) -> None:
    ws, users = workspace_with_members(db_session)
    owner = users["owner"]
    set_tenant_context(db_session, ws.id)
    ctx = WorkspaceContext(
        workspace_id=ws.id,
        actor=ActorRef.user(owner.id),
        role="owner",
        timezone=ws.timezone,
        locale="tr",
        is_demo=False,
    )
    code, _ = generate_link_code(db_session, test_clock, ctx, channel="telegram")

    clear_tenant_context(db_session)
    redeem_link_code(
        db_session,
        test_clock,
        channel="telegram",
        channel_user_id="tg_resolver",
        channel_chat_id="chat_resolver",
        raw_code=code,
    )

    # Resolution succeeds for active link
    resolved = resolve_channel_user(db_session, channel="telegram", channel_user_id="tg_resolver")
    assert resolved is not None
    user, resolved_ws, link = resolved
    assert user.id == owner.id
    assert resolved_ws.id == ws.id
    assert link.status == "active"

    # Resolution returns None for unknown channel user
    assert (
        resolve_channel_user(db_session, channel="telegram", channel_user_id="tg_unknown") is None
    )

    # Unlink and verify resolution returns None
    unlink_by_channel(db_session, test_clock, channel="telegram", channel_user_id="tg_resolver")
    assert (
        resolve_channel_user(db_session, channel="telegram", channel_user_id="tg_resolver") is None
    )
