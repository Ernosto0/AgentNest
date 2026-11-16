"""Web Push subscriptions (F-01, data-model.md §3.8): store, list and revoke a user's devices.

A subscription is what the browser's push service gave a user's device: an ``endpoint`` URL plus
two message-encryption keys. Only the keys are secret: they are stored as AES-GCM ciphertext (the
token key ring, bound by AAD to the workspace, the row and the key's name) and are never returned.
Nothing here sends a push; the owner channel (Session 04) reads these rows.

Every lookup is workspace-scoped and a user sees only their own devices, so a foreign or someone
else's id is a 404 (INV-01). ``subscribe`` is idempotent per (workspace, user, endpoint).
"""

import base64
import binascii
import hashlib
import ipaddress
import re
import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import service as audit_service
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.core.security import TokenCryptoError, TokenKeyRing
from app.notifications.models import PushSubscription

MAX_ENDPOINT_CHARS = 2048
MAX_LABEL_CHARS = 60
MAX_ACTIVE_PER_USER = 10  # per workspace; the oldest is revoked past this
P256DH_BYTES = 65  # uncompressed P-256 point
AUTH_BYTES = 16


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def _b64url_len(value: str) -> int | None:
    try:
        return len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (binascii.Error, ValueError):
        return None


def validate_endpoint(endpoint: str) -> bool:
    """Only an ``https`` URL on a public-looking host (port 443, no credentials, no IP literal).

    The server will later POST to this URL, so a user-supplied address must not be able to point
    at the internal network. This is the cheap static check; the sender re-checks at send time.
    """
    if not endpoint or len(endpoint) > MAX_ENDPOINT_CHARS or endpoint != endpoint.strip():
        return False
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.fragment:
        return False
    if port not in (None, 443) or "." not in host or host.endswith((".local", ".internal")):
        return False
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return True  # a name, not an address
    return False


def validate_keys(p256dh: str, auth: str) -> bool:
    return _b64url_len(p256dh) == P256DH_BYTES and _b64url_len(auth) == AUTH_BYTES


def device_label(user_agent: str | None, label: str | None = None) -> str:
    """A short, human label ("Chrome on Android"); the raw user agent is never stored."""
    if label and label.strip():
        return re.sub(r"\s+", " ", label.strip())[:MAX_LABEL_CHARS]
    ua = user_agent or ""
    os_name = next(
        (
            name
            for needle, name in (
                ("Android", "Android"),
                ("iPhone", "iPhone"),
                ("iPad", "iPad"),
                ("Windows", "Windows"),
                ("Mac OS X", "Mac"),
                ("CrOS", "ChromeOS"),
                ("Linux", "Linux"),
            )
            if needle in ua
        ),
        "",
    )
    browser = next(
        (
            name
            for needle, name in (
                ("Edg/", "Edge"),
                ("OPR/", "Opera"),
                ("SamsungBrowser", "Samsung Internet"),
                ("Firefox/", "Firefox"),
                ("FxiOS", "Firefox"),
                ("CriOS", "Chrome"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            )
            if needle in ua
        ),
        "",
    )
    if browser and os_name:
        return f"{browser} on {os_name}"
    return browser or os_name or "Browser"


def _ring(settings: Settings) -> TokenKeyRing:
    return TokenKeyRing(
        settings.token_encryption_keys.get_secret_value(), settings.token_encryption_active_key_id
    )


def _aad(workspace_id: uuid.UUID, subscription_id: uuid.UUID, part: str) -> bytes:
    """Ties each ciphertext to its tenant, its row and its role, so a copied blob does not open."""
    return f"push:{part}:{workspace_id}:{subscription_id}".encode()


def decrypt_keys(settings: Settings, subscription: PushSubscription) -> tuple[str, str]:
    """``(p256dh, auth)`` for the sender (Session 04). Never put them in a response, job or log."""
    ring = _ring(settings)
    wid, sid = subscription.workspace_id, subscription.id
    return (
        ring.decrypt(
            subscription.p256dh_ciphertext, subscription.key_id, aad=_aad(wid, sid, "p256dh")
        ),
        ring.decrypt(subscription.auth_ciphertext, subscription.key_id, aad=_aad(wid, sid, "auth")),
    )


def subscribe(
    session: Session,
    clock: Clock,
    settings: Settings,
    ctx: WorkspaceContext,
    user_id: uuid.UUID,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
    label: str | None,
) -> tuple[PushSubscription, bool]:
    """Store (or refresh) this device for the user. Returns ``(row, created)``.

    A push that cannot be sent is useless, so with VAPID or the key ring missing this is a
    ``WEB_PUSH_NOT_CONFIGURED`` conflict. The same endpoint arriving from another user of this
    workspace (a shared phone or computer) revokes the previous owner's row: a push must never
    reach whoever is now signed in on a device that was set up for someone else.
    """
    if not settings.web_push_enabled or not settings.token_encryption_keys.get_secret_value():
        raise AppError("WEB_PUSH_NOT_CONFIGURED")
    if not validate_endpoint(endpoint) or not validate_keys(p256dh, auth):
        raise AppError("VALIDATION_FAILED")
    now = clock.now()
    digest = endpoint_hash(endpoint)

    for other in session.scalars(
        select(PushSubscription).where(
            PushSubscription.workspace_id == ctx.workspace_id,
            PushSubscription.endpoint_hash == digest,
            PushSubscription.user_id != user_id,
            PushSubscription.revoked_at.is_(None),
        )
    ):
        other.revoked_at = now

    row = session.scalar(
        select(PushSubscription)
        .where(
            PushSubscription.workspace_id == ctx.workspace_id,
            PushSubscription.user_id == user_id,
            PushSubscription.endpoint_hash == digest,
        )
        .with_for_update()
    )
    created = row is None
    if row is None:
        row = PushSubscription(
            id=uuid.uuid4(),
            workspace_id=ctx.workspace_id,
            user_id=user_id,
            endpoint=endpoint,
            endpoint_hash=digest,
            p256dh_ciphertext=b"",
            auth_ciphertext=b"",
            key_id="",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    elif row.revoked_at is not None:
        row.revoked_at = None
        created = True  # a revived device counts as a new subscription for the audit trail
    ring = _ring(settings)
    try:
        row.p256dh_ciphertext, row.key_id = ring.encrypt(
            p256dh, aad=_aad(ctx.workspace_id, row.id, "p256dh")
        )
        row.auth_ciphertext, _ = ring.encrypt(auth, aad=_aad(ctx.workspace_id, row.id, "auth"))
    except TokenCryptoError:
        raise AppError("WEB_PUSH_NOT_CONFIGURED") from None
    row.device_label = device_label(user_agent, label)
    row.updated_at = now
    session.flush()

    # Keep the list bounded: the oldest devices beyond the cap are revoked.
    active = list(
        session.scalars(
            select(PushSubscription)
            .where(
                PushSubscription.workspace_id == ctx.workspace_id,
                PushSubscription.user_id == user_id,
                PushSubscription.revoked_at.is_(None),
            )
            .order_by(PushSubscription.updated_at.desc(), PushSubscription.created_at.desc())
        )
    )
    for stale in active[MAX_ACTIVE_PER_USER:]:
        stale.revoked_at = now

    if created:
        audit_service.record(
            session,
            ctx,
            "push_subscription.created",
            "push_subscription",
            row.id,
            {"user_id": str(user_id)},
            clock=clock,
        )
    session.commit()
    return row, created


def list_devices(
    session: Session, ctx: WorkspaceContext, user_id: uuid.UUID
) -> list[PushSubscription]:
    """The user's own active devices, newest first."""
    return list(
        session.scalars(
            select(PushSubscription)
            .where(
                PushSubscription.workspace_id == ctx.workspace_id,
                PushSubscription.user_id == user_id,
                PushSubscription.revoked_at.is_(None),
            )
            .order_by(PushSubscription.created_at.desc(), PushSubscription.id)
        )
    )


def unsubscribe(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
) -> None:
    """Revoke one of the user's own devices. Someone else's, a foreign or a gone id is a 404."""
    row = session.scalar(
        select(PushSubscription)
        .where(
            PushSubscription.workspace_id == ctx.workspace_id,
            PushSubscription.id == subscription_id,
            PushSubscription.user_id == user_id,
            PushSubscription.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if row is None:
        raise AppError("NOT_FOUND")
    row.revoked_at = clock.now()
    row.updated_at = clock.now()
    audit_service.record(
        session,
        ctx,
        "push_subscription.revoked",
        "push_subscription",
        row.id,
        {"user_id": str(user_id)},
        clock=clock,
    )
    session.commit()
