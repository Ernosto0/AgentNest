"""Router assembly. Routers stay thin and call services only."""

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.activity.router import router as activity_router
from app.api.deps import enforce_csrf, get_app_settings
from app.approvals.router import router as approvals_router
from app.commands.router import router as commands_router
from app.content.router import router as content_router
from app.core.config import Settings
from app.core.db import check_readiness
from app.core.i18n import SUPPORTED_LOCALES
from app.identity.router import auth_router, invites_router, workspaces_router
from app.inbox.router import router as inbox_router
from app.knowledge.router import router as knowledge_router
from app.notifications.router import router as notifications_router
from app.operations.accounts_router import router as social_accounts_router
from app.operations.router import router as operations_router
from app.operations.system_health_router import router as system_health_router
from app.policy.router import router as policy_router
from app.reporting.router import router as reports_router

health_router = APIRouter(tags=["health"])
# CSRF is enforced for every unsafe method under /api/v1 by default (see deps.enforce_csrf).
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(enforce_csrf)])


class MetaResponse(BaseModel):
    product_name: str
    demo_tools_enabled: bool
    llm_mode: str
    supported_locales: list[str]
    instagram_providers: list[Literal["mock", "meta"]]
    mock_requires_demo_workspace: bool


@health_router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up. Never touches the database."""
    return {"status": "ok"}


@health_router.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness: database reachable and migrations at head."""
    report = check_readiness()
    body = {
        "status": "ok" if report.ready else "unavailable",
        "checks": {"database": report.database, "migrations": report.migrations},
    }
    return JSONResponse(body, status_code=200 if report.ready else 503)


@api_router.get("/meta", response_model=MetaResponse, tags=["meta"])
def meta(settings: Settings = Depends(get_app_settings)) -> MetaResponse:
    """Public, non-secret configuration for the SPA."""
    return MetaResponse(
        product_name=settings.product_name,
        demo_tools_enabled=settings.demo_tools_enabled,
        llm_mode="fake" if settings.llm_provider == "fake" else "real",
        supported_locales=list(SUPPORTED_LOCALES),
        instagram_providers=[
            provider for provider in ("mock", "meta") if provider in settings.instagram_providers
        ],
        mock_requires_demo_workspace=settings.app_env == "production",
    )


api_router.include_router(auth_router)
api_router.include_router(workspaces_router)
api_router.include_router(invites_router)
api_router.include_router(knowledge_router)
api_router.include_router(approvals_router)
api_router.include_router(commands_router)
api_router.include_router(notifications_router)
api_router.include_router(social_accounts_router)
api_router.include_router(operations_router)
api_router.include_router(system_health_router)
api_router.include_router(policy_router)
api_router.include_router(inbox_router)
api_router.include_router(content_router)
api_router.include_router(reports_router)
api_router.include_router(activity_router)
