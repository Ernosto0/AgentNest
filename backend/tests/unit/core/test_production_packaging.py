"""Phase 8 Session 02: production Dockerfile, Compose, Caddyfile, and .dockerignore contracts."""

from pathlib import Path

import yaml

from app.jobs.worker import SHUTDOWN_GRACE_SECONDS

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_dockerignore_excludes_secrets_and_local_artifacts() -> None:
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    lines = {
        line.strip()
        for line in dockerignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    required_patterns = {
        ".git",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        ".venv/",
        "backend/.venv/",
        "node_modules/",
        "frontend/node_modules/",
        "frontend/dist/",
        "var/",
        "backend/var/",
        "backend/tests/",
    }
    missing = required_patterns - lines
    assert not missing, f"Missing required .dockerignore exclusions: {sorted(missing)}"
    assert "!.env" not in lines and "!.env.production" not in lines


def test_dockerfile_defines_multistage_nonroot_build_with_frozen_deps() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    # Multi-stage targets
    assert "FROM node:22-alpine AS frontend-builder" in dockerfile
    assert "FROM caddy:2.8-alpine AS caddy" in dockerfile
    assert "FROM python:3.12-slim-bookworm AS backend-builder" in dockerfile
    assert "FROM python:3.12-slim-bookworm AS backend" in dockerfile

    # Frozen lockfile installs
    assert "RUN npm ci" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile

    # Only VITE_API_BASE_URL is exposed to the frontend build stage (ADR-017 / INV-10)
    arg_lines = [
        line.strip() for line in dockerfile.splitlines() if line.strip().startswith("ARG ")
    ]
    assert arg_lines == ['ARG VITE_API_BASE_URL=""']

    # Non-root execution in final backend runtime stage
    assert "groupadd --system --gid 10001 agentnest" in dockerfile
    assert "useradd --system --uid 10001 --gid 10001" in dockerfile
    assert "USER agentnest:agentnest" in dockerfile
    assert 'CMD ["uvicorn", "app.main:create_app", "--factory"' in dockerfile


def test_compose_prod_defines_hardened_services_volumes_and_grace_periods() -> None:
    compose_raw = (REPO_ROOT / "compose.prod.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_raw)

    assert compose["name"] == "${COMPOSE_PROJECT_NAME:-agentnest}"
    services = compose["services"]
    assert set(services) == {"postgres", "migrate", "backup", "api", "worker", "caddy"}

    # Non-root user and privilege restrictions on backend services
    for svc_name in ("api", "worker", "migrate", "backup"):
        svc = services[svc_name]
        assert svc["user"] == "10001:10001"
        assert "no-new-privileges:true" in svc["security_opt"]
        assert svc["logging"]["driver"] == "json-file"

    # Worker stop_grace_period must exceed SHUTDOWN_GRACE_SECONDS (30s) so leases drain (INV-07)
    worker_grace = services["worker"]["stop_grace_period"]
    assert worker_grace.endswith("s")
    assert int(worker_grace[:-1]) > int(SHUTDOWN_GRACE_SECONDS)

    # Postgres and API are never published directly on host ports; only Caddy publishes 80/443
    assert "ports" not in services["postgres"]
    assert "ports" not in services["api"]
    assert "ports" not in services["worker"]
    assert len(services["caddy"]["ports"]) == 3

    # Persistent volumes exist for database, media, and Caddy ACME state
    assert {"postgres_data", "media_data", "caddy_data", "caddy_config"} <= set(compose["volumes"])
    assert {"edge", "backend"} <= set(compose["networks"])


def test_caddyfile_routes_and_security_headers() -> None:
    caddyfile = (REPO_ROOT / "Caddyfile").read_text(encoding="utf-8")

    # Parameterized domain and TLS directive for production, staging (P8-12), and local rehearsal
    assert "{$APP_DOMAIN::80}" in caddyfile
    assert "{$CADDY_TLS_CONFIG:}" in caddyfile

    # Backend routes preserved without path stripping
    assert (
        "@backend path /api /api/* /webhooks /webhooks/* /oauth /oauth/* /healthz /readyz"
        in caddyfile
    )
    assert "reverse_proxy {$API_UPSTREAM:api:8000}" in caddyfile

    # SPA fallback for deep links
    assert "try_files {path} /index.html" in caddyfile
    assert "file_server" in caddyfile

    # Security headers and strict CSP without unsafe-eval or unsafe-inline
    assert 'Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"' in caddyfile
    assert 'X-Content-Type-Options "nosniff"' in caddyfile
    assert 'X-Frame-Options "DENY"' in caddyfile
    assert 'Referrer-Policy "strict-origin-when-cross-origin"' in caddyfile
    assert "Permissions-Policy" in caddyfile
    assert "Content-Security-Policy" in caddyfile
    assert "default-src 'self'" in caddyfile
    assert "script-src 'self'" in caddyfile
    assert "style-src 'self'" in caddyfile
    assert "img-src 'self' blob: data:" in caddyfile
    assert "connect-src 'self'" in caddyfile
    assert "frame-ancestors 'none'" in caddyfile
    assert "unsafe-eval" not in caddyfile
    assert "unsafe-inline" not in caddyfile
