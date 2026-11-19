"""Offline unit tests for Session 02 notification channel preferences.

Verifies:
- Explicit per-workspace/per-user channel preference contract.
- Fallback for existing links without unsolicited new subscriptions.
- Preference setting (enable/disable, app-only selection, validation rules).
- Truthful channel delivery status: unconfigured, unlinked, disabled, delivery_failure, connected.
- Auto-enabling on link redemption and auto-disabling on unlinking.
- Preference filtering in dispatch_telegram and dispatch_whatsapp.
- Rechecking preferences in deliver_channel_notification worker job.
- Router availability and preferences handlers.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.api.v1.channels_router import (
    get_channel_availability,
)
from app.api.v1.channels_router import (
    update_channel_preferences as router_update_channel_preferences,
)
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError
from app.identity.channels import (
    ChannelLinkService,
    get_channel_delivery_status,
    get_channel_preferences,
    is_channel_enabled,
    set_channel_preferences,
)
from app.identity.models import (
    CHANNEL_TYPES,
    ChannelLink,
    ChannelPreference,
    User,
    Workspace,
    WorkspaceMember,
)
from app.identity.schemas import (
    ChannelPreferencesIn,
)
from app.notifications.catalog import TELEGRAM_TYPES, WHATSAPP_TYPES
from app.notifications.jobs import deliver_channel_notification
from app.notifications.models import Notification, NotificationDelivery
from app.notifications.telegram_dispatch import dispatch_telegram
from app.notifications.whatsapp_dispatch import dispatch_whatsapp

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


class InMemoryStoreSession:
    """In-memory session double for offline testing of identity channel preferences."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[type[Any], Any], Any] = {}
        self.items: dict[type[Any], list[Any]] = {}
        self.added: list[Any] = []
        self.commits: int = 0
        self.flushes: int = 0
        self.in_tx: bool = True
        self.info: dict[str, Any] = {}

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return MagicMock()

    def put(self, obj: Any, key: Any | None = None) -> Any:
        k = key if key is not None else getattr(obj, "id", None)
        self.by_key[(type(obj), k)] = obj
        type_list = self.items.setdefault(type(obj), [])
        if obj not in type_list:
            type_list.append(obj)
        return obj

    def get(self, model: type[Any], ident: Any, **_: Any) -> Any:
        return self.by_key.get((model, ident))

    def scalar(self, stmt: Any) -> Any:
        sql = str(stmt)
        sql_lower = sql.lower()
        # Handle count statements
        if "count(" in sql_lower:
            for model, item_list in self.items.items():
                tbl = getattr(model, "__tablename__", "")
                if tbl and f"from {tbl}" in sql_lower:
                    return len(item_list)
            return 0

        # Handle queries returning an attribute or entity
        for model, item_list in self.items.items():
            tbl = getattr(model, "__tablename__", "")
            if tbl and f"from {tbl}" in sql_lower:
                if not item_list:
                    return None
                # If querying ChannelPreference
                if model is ChannelPreference:
                    if sql.strip().startswith("SELECT channel_preferences.enabled"):
                        return item_list[-1].enabled
                    return item_list[-1]
                # If querying ChannelLink
                if model is ChannelLink:
                    for item in reversed(item_list):
                        if getattr(item, "status", None) == "active":
                            if sql.strip().startswith("SELECT channel_links.id"):
                                return item.id
                            return item
                    return None
                # If querying NotificationDelivery
                if model is NotificationDelivery:
                    # Return latest
                    return item_list[-1] if item_list else None
                return item_list[-1]
        return None

    def scalars(self, stmt: Any) -> Any:
        sql = str(stmt)
        for model, item_list in self.items.items():
            tbl = getattr(model, "__tablename__", "")
            if tbl and f"FROM {tbl}" in sql:
                active_items = [i for i in item_list if getattr(i, "status", "active") == "active"]
                mock_result = MagicMock()
                mock_result.all.return_value = active_items
                return mock_result
        mock_result = MagicMock()
        mock_result.all.return_value = []
        return mock_result

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            with contextlib.suppress(Exception):
                obj.id = uuid.uuid4()
        self.added.append(obj)
        self.put(obj)

    def flush(self) -> None:
        self.flushes += 1

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def __enter__(self) -> InMemoryStoreSession:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    @contextlib.contextmanager
    def begin_nested(self) -> Any:
        yield self

    def get_bind(self) -> Any:
        bind = MagicMock()
        bind.dialect.name = "sqlite"
        return bind


def make_context(ws_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=ws_id,
        actor=ActorRef.user(user_id),
        role="owner",
        timezone="Europe/Istanbul",
        locale="tr",
        is_demo=False,
    )


# --- 1. Preference Fallback and Default Behavior ---


def test_is_channel_enabled_with_explicit_preference() -> None:
    session = InMemoryStoreSession()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # When explicit preference row exists (enabled=True)
    pref_true = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        enabled=True,
    )
    session.put(pref_true)
    assert is_channel_enabled(session, ws_id, user_id, "telegram") is True

    # When explicit preference row exists (enabled=False)
    session.items[ChannelPreference].clear()
    pref_false = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        enabled=False,
    )
    session.put(pref_false)
    assert is_channel_enabled(session, ws_id, user_id, "telegram") is False


def test_is_channel_enabled_fallback_to_active_link() -> None:
    session = InMemoryStoreSession()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # No preference row: with active link -> True
    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        channel_user_id="tg_123",
        channel_chat_id="tg_123",
        status="active",
        linked_at=NOW,
    )
    session.put(link)
    assert is_channel_enabled(session, ws_id, user_id, "telegram") is True

    # No preference row: with unlinked link -> False
    link.status = "unlinked"
    assert is_channel_enabled(session, ws_id, user_id, "telegram") is False

    # No link at all -> False
    session.items[ChannelLink].clear()
    session.by_key.clear()
    assert is_channel_enabled(session, ws_id, user_id, "telegram") is False


# --- 2. Getting and Setting Channel Preferences ---


def test_get_channel_preferences() -> None:
    session = InMemoryStoreSession()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    prefs = get_channel_preferences(session, ws_id, user_id)
    assert set(prefs.keys()) == set(CHANNEL_TYPES)
    assert prefs["telegram"] is False
    assert prefs["whatsapp"] is False


def test_set_channel_preferences_validation() -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)

    with pytest.raises(AppError) as exc:
        set_channel_preferences(session, clock, ctx, user_id, {"unsupported_ch": True})  # type: ignore[dict-item]
    assert exc.value.code == "VALIDATION_FAILED"


def test_set_channel_preferences_insert_and_update() -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)

    # Insert new preference
    res = set_channel_preferences(session, clock, ctx, user_id, {"telegram": True})
    assert res["telegram"] is True
    assert session.flushes >= 1
    assert any(isinstance(a, ChannelPreference) and a.enabled for a in session.added)

    # Update existing preference
    clock.advance(seconds=10)
    res2 = set_channel_preferences(session, clock, ctx, user_id, {"telegram": False})
    assert res2["telegram"] is False


# --- 3. Truthful Channel Delivery Status ---


def test_get_channel_delivery_status_truthful_states() -> None:
    session = InMemoryStoreSession()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # 1. Unconfigured state
    unconfigured_settings = Settings(
        telegram_bot_token=None,
        telegram_bot_username=None,
    )
    status_unconfigured = get_channel_delivery_status(
        session, unconfigured_settings, ws_id, user_id, "telegram"
    )
    assert status_unconfigured["status"] == "unconfigured"
    assert status_unconfigured["configured"] is False

    # 2. Unlinked state (configured, but no active link)
    configured_settings = Settings(
        telegram_bot_token="secret_token",  # type: ignore[arg-type]
        telegram_bot_username="test_bot",
    )
    status_unlinked = get_channel_delivery_status(
        session, configured_settings, ws_id, user_id, "telegram"
    )
    assert status_unlinked["status"] == "unlinked"
    assert status_unlinked["linked"] is False

    # 3. Disabled state (linked, but preference disabled)
    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        channel_user_id="tg_123",
        channel_chat_id="tg_123",
        status="active",
        linked_at=NOW,
    )
    session.put(link)
    pref_disabled = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        enabled=False,
    )
    session.put(pref_disabled)
    status_disabled = get_channel_delivery_status(
        session, configured_settings, ws_id, user_id, "telegram"
    )
    assert status_disabled["status"] == "disabled"
    assert status_disabled["enabled"] is False
    assert status_disabled["linked"] is True

    # 4. Delivery failure state (linked, enabled, but latest delivery failed)
    pref_disabled.enabled = True
    delivery_failed = NotificationDelivery(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        recipient_user_id=user_id,
        notification_id=uuid.uuid4(),
        channel="telegram",
        status="failed",
        last_error="ambiguous_transport_timeout",
    )
    session.put(delivery_failed)
    status_failure = get_channel_delivery_status(
        session, configured_settings, ws_id, user_id, "telegram"
    )
    assert status_failure["status"] == "delivery_failure"
    assert status_failure["last_error"] == "ambiguous_transport_timeout"

    # 5. Connected state (linked, enabled, latest delivery succeeded)
    delivery_failed.status = "delivered"
    status_connected = get_channel_delivery_status(
        session, configured_settings, ws_id, user_id, "telegram"
    )
    assert status_connected["status"] == "connected"
    assert status_connected["enabled"] is True


# --- 4. Unlinking Disables Preference ---


def test_unlink_by_user_disables_preference() -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)

    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        channel_user_id="tg_123",
        channel_chat_id="tg_123",
        status="active",
        linked_at=NOW,
    )
    pref = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        enabled=True,
    )
    session.put(link)
    session.put(pref)

    ChannelLinkService.unlink_by_user(session, clock, ctx, link.id)
    assert link.status == "unlinked"
    assert pref.enabled is False


# --- 5. Dispatch Functions Recheck Channel Preference ---


def test_dispatch_telegram_skips_when_preference_disabled() -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)

    user = User(
        id=user_id,
        email="owner@example.com",
        password_hash="***",
        display_name="Owner",
        is_active=True,
    )
    member = WorkspaceMember(workspace_id=ws_id, user_id=user_id, role="owner")
    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        channel_user_id="tg_123",
        channel_chat_id="tg_123",
        status="active",
        linked_at=NOW,
    )
    pref = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        enabled=False,  # explicitly disabled
    )
    session.put(user)
    session.put(member)
    session.put(link)
    session.put(pref)

    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        recipient_user_id=user_id,
        type=list(TELEGRAM_TYPES)[0],
        severity="critical",
        params={},
        is_simulated=False,
    )

    result = dispatch_telegram(session, clock, ctx, notif)
    assert result is None  # Skipped because disabled by preference


def test_dispatch_whatsapp_skips_when_preference_disabled(monkeypatch: Any) -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)

    mock_settings = Settings(
        whatsapp_access_token="test_token",  # type: ignore[arg-type]
        whatsapp_app_secret="test_secret",  # type: ignore[arg-type]
        whatsapp_phone_number_id="12345",
        whatsapp_display_phone_number="905551112233",
    )
    monkeypatch.setattr("app.notifications.whatsapp_dispatch.get_settings", lambda: mock_settings)

    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="whatsapp",
        channel_user_id="905551112233",
        channel_chat_id="905551112233",
        status="active",
        linked_at=NOW,
    )
    pref = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="whatsapp",
        enabled=False,
    )
    session.put(link)
    session.put(pref)

    notif = Notification(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        recipient_user_id=user_id,
        type=list(WHATSAPP_TYPES)[0],
        severity="critical",
        params={},
        is_simulated=False,
    )

    result = dispatch_whatsapp(session, clock, ctx, notif)
    assert result is None


# --- 6. Worker Rechecks Channel Preference for Queued Delivery ---


def test_deliver_channel_notification_rechecks_preference_on_worker() -> None:
    session = InMemoryStoreSession()
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    delivery_id = uuid.uuid4()
    notif_id = uuid.uuid4()

    workspace = Workspace(
        id=ws_id,
        name="Test WS",
        slug="test-ws",
        business_category="retail",
        market="tr",
        default_locale="tr",
        timezone="Europe/Istanbul",
        currency="TRY",
    )
    user = User(
        id=user_id,
        email="owner@example.com",
        password_hash="***",
        display_name="Owner",
        is_active=True,
    )
    member = WorkspaceMember(workspace_id=ws_id, user_id=user_id, role="owner")
    link = ChannelLink(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        channel_user_id="tg_123",
        channel_chat_id="tg_123",
        status="active",
        linked_at=NOW,
    )
    notif = Notification(
        id=notif_id,
        workspace_id=ws_id,
        recipient_user_id=user_id,
        type="approval.requested",
        severity="critical",
        params={},
        is_simulated=False,
    )
    delivery = NotificationDelivery(
        id=delivery_id,
        workspace_id=ws_id,
        notification_id=notif_id,
        recipient_user_id=user_id,
        channel="telegram",
        channel_link_id=link.id,
        status="pending",
        attempt_count=0,
    )
    # Channel was disabled AFTER notification was queued
    pref = ChannelPreference(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        user_id=user_id,
        channel="telegram",
        enabled=False,
    )
    session.put(workspace)
    session.put(user)
    session.put(member)
    session.put(link)
    session.put(notif)
    session.put(delivery)
    session.put(pref)

    from app.notifications.delivery_ledger import DeliverChannelNotificationPayload

    job_ctx = MagicMock()
    job_ctx.session_factory.return_value = session
    job_ctx.workspace_id = ws_id
    job_ctx.clock = FrozenClock(NOW)
    job_ctx.payload = DeliverChannelNotificationPayload(delivery_id=delivery_id)

    deliver_channel_notification(job_ctx)

    assert delivery.status == "failed"
    assert delivery.last_error == "channel_disabled_by_preference"
    assert session.commits >= 1


# --- 7. Channels Router Preference Endpoints ---


def test_router_availability_reports_truthfully() -> None:
    settings = Settings(
        telegram_bot_token="test_token",  # type: ignore[arg-type]
        telegram_bot_username="test_bot",
        whatsapp_access_token=None,
    )
    ctx = make_context(uuid.uuid4(), uuid.uuid4())
    availability = get_channel_availability(ctx=ctx, settings=settings)
    assert availability.telegram is True
    assert availability.whatsapp is False


def test_router_update_preferences_app_only_conflict() -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)
    settings = Settings()

    # Conflicting app_only=True and telegram=True
    with pytest.raises(AppError) as exc:
        router_update_channel_preferences(
            body=ChannelPreferencesIn(app_only=True, telegram=True),
            ctx=ctx,
            db=session,  # type: ignore[arg-type]
            clock=clock,
            settings=settings,
        )
    assert exc.value.code == "VALIDATION_FAILED"
    assert exc.value.params.get("reason") == "app_only_conflict"


def test_router_update_preferences_app_only_success() -> None:
    session = InMemoryStoreSession()
    clock = FrozenClock(NOW)
    ws_id = uuid.uuid4()
    user_id = uuid.uuid4()
    ctx = make_context(ws_id, user_id)
    settings = Settings()

    res = router_update_channel_preferences(
        body=ChannelPreferencesIn(app_only=True),
        ctx=ctx,
        db=session,  # type: ignore[arg-type]
        clock=clock,
        settings=settings,
    )
    assert res.app_only is True
    assert res.telegram is False
    assert res.whatsapp is False
