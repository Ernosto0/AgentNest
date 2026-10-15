"""Router assembly. Routers stay thin and call services only."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import enforce_csrf, get_app_settings
from app.core.config import Settings
from app.core.db import check_readiness
from app.core.i18n import SUPPORTED_LOCALES
from app.identity.router import auth_router, workspaces_router
from app.knowledge.router import router as knowledge_router

health_router = APIRouter(tags=["health"])
# CSRF is enforced for every unsafe method under /api/v1 by default (see deps.enforce_csrf).
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(enforce_csrf)])


class MetaResponse(BaseModel):
    product_name: str
    demo_tools_enabled: bool
    llm_mode: str
    supported_locales: list[str]


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
        llm_mode="fake",  # the LLM provider setting arrives in Phase 3
        supported_locales=list(SUPPORTED_LOCALES),
    )


api_router.include_router(auth_router)
api_router.include_router(workspaces_router)
api_router.include_router(knowledge_router)
