"""API entry point: ``uvicorn app.main:create_app --factory``."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.middleware import RequestIdMiddleware
from app.api.router import api_router, health_router
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.knowledge.templates import validate_templates


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = get_logger(__name__)
    log.info("startup", **settings.public_dict())
    validate_templates()  # a broken fact template fails the start, not a checklist screen

    in_production = settings.app_env == "production"
    app = FastAPI(
        title=settings.product_name,
        version="0.1.0",
        # /openapi.json is served in development and test only (api-design.md §3).
        openapi_url=None if in_production else "/openapi.json",
        docs_url=None if in_production else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.clock = clock or SystemClock()

    if not in_production:  # CORS is disabled in production (same origin)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.frontend_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestIdMiddleware)  # outermost: wraps every response

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    return app
