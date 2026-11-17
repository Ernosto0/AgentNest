"""Website source for candidate-only knowledge imports."""

import unicodedata
from datetime import timedelta
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AgentRun
from app.audit import service as audit
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.context import ActorRef, WorkspaceContext
from app.core.errors import AppError, RetryableError
from app.identity import service as identity_service
from app.identity.models import Workspace
from app.identity.permissions import has_permission
from app.integrations.web.html_text import PageLink, chunk_text, extract_page
from app.integrations.web.registry import get_page_fetcher
from app.integrations.web.safe_fetch import FetchedPage
from app.integrations.web.urls import FetchRefused, parse_site_url
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

SOURCE = "website"
_KEYWORDS = (
    ("fiyat", "ucret", "paket", "tarife", "uyelik", "price", "pricing", "rates"),
    ("iletisim", "contact", "ulasim", "adres", "address", "bize-ulasin"),
    ("hakkimizda", "hakkinda", "about", "kurumsal", "hours", "saatler", "calisma-saatleri"),
)
_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".zip",
    ".mp4",
    ".css",
    ".js",
    ".ico",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
)


def _same_host(host: str) -> str:
    return host.lower().removeprefix("www.")


def select_pages(links: list[PageLink], home: FetchedPage) -> list[str]:
    ranked: list[tuple[str, tuple[int, ...]]] = []
    seen = {parse_site_url(home.url).url}
    for link in links:
        try:
            parsed = parse_site_url(link.url)
        except FetchRefused:
            continue
        if parsed.url in seen or _same_host(parsed.host) != _same_host(home.final_host):
            continue
        seen.add(parsed.url)
        if urlsplit(parsed.url).path.lower().endswith(_EXTENSIONS):
            continue
        text = unquote(urlsplit(parsed.url).path) + " " + link.anchor
        text = (
            unicodedata.normalize("NFKD", text.lower().replace("ı", "i"))
            .encode("ascii", "ignore")
            .decode()
        )
        scores = tuple(sum(word in text for word in words) for words in _KEYWORDS)
        if any(scores):
            ranked.append((parsed.url, scores))
    chosen: list[str] = []
    for category in range(3):
        available = [
            (url, scores) for url, scores in ranked if url not in chosen and scores[category]
        ]
        if available:
            chosen.append(max(available, key=lambda item: item[1][category])[0])
    for url, _ in sorted(ranked, key=lambda item: sum(item[1]), reverse=True):
        if len(chosen) >= 3:
            break
        if url not in chosen:
            chosen.append(url)
    return chosen


def _failure(exc: FetchRefused) -> Exception:
    if exc.reason in (
        "blocked_address",
        "host",
        "ip_literal",
        "port",
        "scheme",
        "userinfo",
        "redirects",
        "invalid_url",
    ):
        return ImportFailed("WEBSITE_BLOCKED")
    if exc.reason in ("content_type", "encoding"):
        return ImportFailed("WEBSITE_NOT_HTML")
    if exc.reason == "too_large":
        return ImportFailed("WEBSITE_TOO_LARGE")
    return (
        RetryableError("WEBSITE_UNREACHABLE")
        if exc.retryable
        else ImportFailed("WEBSITE_UNREACHABLE")
    )


def gather_website(inp: GatherInput) -> GatherResult:
    fetcher = get_page_fetcher(get_settings())
    records: list[dict[str, Any]] = []
    pages: list[FetchedPage] = []
    skipped = 0

    def fetch(url: str, page_kind: str) -> FetchedPage:
        host = None
        try:
            host = parse_site_url(url).host
            page = fetcher.fetch(url)
        except FetchRefused as exc:
            failure = _failure(exc)
            records.append(
                {
                    "host": exc.host or host,
                    "final_host": None,
                    "outcome": "blocked"
                    if isinstance(failure, ImportFailed) and failure.error_code == "WEBSITE_BLOCKED"
                    else "failed",
                    "reason": exc.reason,
                    "status": None,
                    "bytes": 0,
                    "redirects": 0,
                    "page": page_kind,
                }
            )
            raise
        records.append(
            {
                "host": host,
                "final_host": page.final_host,
                "outcome": "ok",
                "reason": None,
                "status": page.status,
                "bytes": len(page.body),
                "redirects": page.redirects,
                "page": page_kind,
            }
        )
        return page

    try:
        try:
            home = fetch(inp.snapshot["website_url"], "home")
        except FetchRefused as exc:
            raise _failure(exc) from None
        pages.append(home)
        home_text = extract_page(home.body, home.content_type, home.url)
        for url in select_pages(home_text.links, home):
            try:
                pages.append(fetch(url, "subpage"))
            except FetchRefused:
                skipped += 1
        segments: list[ImportSegment] = []
        for page in pages:
            text = extract_page(page.body, page.content_type, page.url).text
            for index, chunk in enumerate(chunk_text(text, 700)):
                if (
                    index == 0
                    or any(c.isdigit() for c in chunk)
                    or any(s in chunk for s in ("@", "tel:", "mailto:"))
                ):
                    segments.append(ImportSegment("website_page", chunk, url=page.url))
        return GatherResult(
            segments[:40],
            {
                "website_host": home.final_host,
                "pages_fetched": len(pages),
                "pages_skipped": skipped,
            },
            fetcher.simulated,
        )
    finally:
        if inp.run_id is not None and records:
            with inp.session_factory() as session:
                workspace = session.get(Workspace, inp.workspace_id)
                if workspace is not None:
                    ctx = identity_service.workspace_context(
                        workspace, ActorRef.system("import.website"), None
                    )
                    for record in records:
                        audit.record(
                            session,
                            ctx,
                            "knowledge.website_fetched",
                            "agent_run",
                            inp.run_id,
                            record,
                            clock=inp.clock,
                            is_simulated=fetcher.simulated,
                        )
                    session.commit()


@job_handler(
    "import_website",
    ImportRunPayload,
    max_attempts=2,
    timeout=180,
    on_dead=imports.fail_run_if_open,
    backoff=(10, 60),
)
def import_website(job: JobContext) -> None:
    imports.run_import(job, source_type=SOURCE, gather=gather_website)


def request_website_import(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    *,
    url: str,
    client_request_id: str,
) -> AgentRun:
    request_id = client_request_id.strip()
    if not request_id or len(request_id) > extraction.MAX_REQUEST_ID_CHARS:
        raise extraction._validation("client_request_id", "invalid")
    if session.get(Workspace, ctx.workspace_id, with_for_update=True) is None:
        raise AppError("NOT_FOUND")
    existing = imports.find_request(session, ctx.workspace_id, SOURCE, request_id)
    if existing is not None:
        return existing
    try:
        parsed = parse_site_url(url)
    except FetchRefused:
        raise extraction._validation("url", "invalid_url") from None
    existing = imports.find_in_progress(session, ctx.workspace_id, SOURCE, clock.now())
    if existing is not None:
        return existing
    count = (
        session.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(
                AgentRun.workspace_id == ctx.workspace_id,
                AgentRun.task == "extract_fact_candidates",
                AgentRun.input_snapshot["source"].astext == SOURCE,
                AgentRun.created_at >= clock.now() - timedelta(hours=24),
            )
        )
        or 0
    )
    if count >= settings.website_import_max_per_workspace_per_day:
        raise AppError("RATE_LIMITED", headers={"Retry-After": "3600"}, retry_after=3600)
    run = imports.create_import_run(
        session,
        clock,
        ctx,
        source_type=SOURCE,
        snapshot_extra={"website_url": parsed.url, "trigger": "manual"},
        client_request_id=request_id,
    )
    audit.record(
        session,
        ctx,
        "knowledge.import_requested",
        "agent_run",
        run.id,
        {"source": SOURCE, "trigger": "manual", "host": parsed.host},
        correlation_id=run.correlation_id,
        clock=clock,
        is_simulated=get_page_fetcher(settings).simulated,
    )
    queue.enqueue(
        session,
        "import_website",
        ImportRunPayload(run_id=run.id),
        dedup_key=f"import_website:{run.id}",
        workspace_id=ctx.workspace_id,
        correlation_id=run.correlation_id,
        clock=clock,
    )
    return run


def start_manual_website_import(
    session: Session,
    clock: Clock,
    ctx: WorkspaceContext,
    settings: Settings,
    *,
    url: str,
    client_request_id: str,
) -> AgentRun:
    if (
        not has_permission(ctx.role, "knowledge.edit")
        or ctx.actor.type != "user"
        or not ctx.actor.id
    ):
        raise AppError("FORBIDDEN", permission="knowledge.edit")
    run = request_website_import(
        session, clock, ctx, settings, url=url, client_request_id=client_request_id
    )
    session.commit()
    return run


def website_prefill(session: Session, ctx: WorkspaceContext) -> str | None:
    for source, key in ((SOURCE, "website_url"), ("instagram_profile", "profile_website")):
        value = session.scalar(
            select(AgentRun.input_snapshot[key].astext)
            .where(
                AgentRun.workspace_id == ctx.workspace_id,
                AgentRun.task == "extract_fact_candidates",
                AgentRun.input_snapshot["source"].astext == source,
                AgentRun.input_snapshot[key].astext.is_not(None),
            )
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(1)
        )
        if value:
            return str(value)
    return None
