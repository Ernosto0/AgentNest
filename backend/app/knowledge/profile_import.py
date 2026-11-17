"""Instagram source for the shared candidate import pipeline (F-09)."""

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import get_settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError, RetryableError
from app.core.logging import get_logger
from app.identity.permissions import has_permission
from app.integrations.instagram import queries
from app.integrations.instagram.errors import (
    ProviderAuthError,
    ProviderInvalidRequest,
    ProviderOutcomeUnknown,
    ProviderPermissionError,
    ProviderRateLimited,
    ProviderTransientError,
)
from app.integrations.instagram.models import SocialAccount
from app.integrations.instagram.registry import account_ref, get_provider
from app.jobs import queue
from app.jobs.registry import JobContext, job_handler
from app.knowledge import extraction, imports
from app.knowledge.imports import (
    GatherInput,
    GatherResult,
    ImportFailed,
    ImportRunPayload,
    ImportSegment,
)

SOURCE = "instagram_profile"


def gather_instagram_profile(inp: GatherInput) -> GatherResult:
    settings = get_settings()
    with inp.session_factory() as session:
        account = queries.get_account_in_workspace(
            session, inp.workspace_id, uuid.UUID(inp.snapshot["social_account_id"])
        )
        if account is None or account.status == "disconnected":
            raise ImportFailed("CONFLICT_STATE")
        if account.status == "needs_reauth":
            raise ImportFailed("ACCOUNT_NEEDS_REAUTH")
        if account.provider_kind not in settings.instagram_providers:
            raise ImportFailed("PROVIDER_UNAVAILABLE")
        if (
            account.provider_kind == "meta"
            and "instagram_business_basic" not in account.granted_scopes
        ):
            raise ImportFailed("CAPABILITY_MISSING")
        ref = account_ref(account, settings)
        provider = get_provider(
            account.provider_kind,
            settings=settings,
            session_factory=inp.session_factory,
            clock=inp.clock,
        )
        simulated = account.is_simulated
    notes: dict[str, object] = {}
    try:
        profile = provider.get_profile_details(ref)
        try:
            captions = provider.list_recent_captions(ref, imports.PROFILE_IMPORT_CAPTIONS)
        except (ProviderInvalidRequest, ProviderPermissionError):
            captions = []
            notes["captions_unavailable"] = True
    except ProviderAuthError:
        raise ImportFailed("ACCOUNT_NEEDS_REAUTH") from None
    except ProviderPermissionError:
        raise ImportFailed("CAPABILITY_MISSING") from None
    except ProviderInvalidRequest:
        raise ImportFailed("PROVIDER_REJECTED") from None
    except (ProviderTransientError, ProviderRateLimited, ProviderOutcomeUnknown) as exc:
        raise RetryableError(
            exc.code,
            retry_after_seconds=exc.retry_after_s if isinstance(exc, ProviderRateLimited) else None,
        ) from None
    if (
        profile.website
        and len(profile.website) <= 300
        and profile.website.startswith(("https://", "http://"))
    ):
        notes["profile_website"] = profile.website
    segments = [ImportSegment("bio", profile.biography)] if profile.biography else []
    segments.extend(
        ImportSegment("caption", c.caption, c.posted_at, c.permalink)
        for c in captions
        if c.caption and c.caption.strip()
    )
    return GatherResult(segments, notes, simulated)


@job_handler(
    "import_instagram_profile",
    ImportRunPayload,
    max_attempts=2,
    timeout=150,
    on_dead=imports.fail_run_if_open,
    backoff=(10, 60),
)
def import_instagram_profile(job: JobContext) -> None:
    imports.run_import(job, source_type=SOURCE, gather=gather_instagram_profile)


def request_instagram_import(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    account: SocialAccount,
    *,
    trigger: Literal["first_connection", "manual"],
    client_request_id: str | None = None,
) -> AgentRun:
    """Queue in the caller's transaction. Serialize requests on the workspace's account."""
    locked = queries.get_account_in_workspace(session, ctx.workspace_id, account.id, lock=True)
    if locked is None:
        raise AppError("NOT_FOUND")
    if trigger == "first_connection":
        client_request_id = f"first_connection:{account.id}"
    else:
        client_request_id = (client_request_id or "").strip()
        if not client_request_id or len(client_request_id) > extraction.MAX_REQUEST_ID_CHARS:
            raise extraction._validation("client_request_id", "invalid")
    existing = imports.find_request(session, ctx.workspace_id, SOURCE, client_request_id)
    if existing is not None:
        return existing
    if trigger == "manual":
        existing = imports.find_in_progress(session, ctx.workspace_id, SOURCE, clock.now())
        if existing is not None:
            return existing
    run = imports.create_import_run(
        session,
        clock,
        ctx,
        source_type=SOURCE,
        snapshot_extra={"social_account_id": str(account.id), "trigger": trigger},
        client_request_id=client_request_id,
    )
    audit.record(
        session,
        ctx,
        "knowledge.import_requested",
        "agent_run",
        run.id,
        {"source": SOURCE, "trigger": trigger},
        correlation_id=run.correlation_id,
        clock=clock,
        is_simulated=account.is_simulated,
    )
    queue.enqueue(
        session,
        "import_instagram_profile",
        ImportRunPayload(run_id=run.id),
        dedup_key=f"import_instagram_profile:{run.id}",
        workspace_id=ctx.workspace_id,
        correlation_id=run.correlation_id,
        clock=clock,
    )
    return run


def first_connection_import(
    session: Session, clock: Clock, ctx: WorkspaceContext, account: SocialAccount
) -> None:
    """An optional import failure must never roll back account connection."""
    try:
        with session.begin_nested():
            request_instagram_import(session, clock, ctx, account, trigger="first_connection")
    except Exception:
        # Deliberately exclude exception details: upstream content and secrets are untrusted.
        get_logger(__name__).warning("knowledge_import_trigger_failed", source=SOURCE)


def start_manual_instagram_import(
    session: Session, clock: Clock, ctx: WorkspaceContext, *, client_request_id: str
) -> AgentRun:
    if (
        not has_permission(ctx.role, "knowledge.edit")
        or ctx.actor.type != "user"
        or not ctx.actor.id
    ):
        raise AppError("FORBIDDEN", permission="knowledge.edit")
    account = queries.get_active_for_workspace(session, ctx.workspace_id)
    if account is None:
        raise AppError("CONFLICT_STATE", entity="social_account", reason="no_connected_account")
    if account.status not in ("connected", "degraded"):
        raise AppError(
            "CONFLICT_STATE",
            entity="social_account",
            status=account.status,
            reason="account_not_ready",
        )
    run = request_instagram_import(
        session, clock, ctx, account, trigger="manual", client_request_id=client_request_id
    )
    session.commit()
    return run
