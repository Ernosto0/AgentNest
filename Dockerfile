# syntax=docker/dockerfile:1
# Multi-stage production Dockerfile for AgentNest (P8-01 / ADR-017 / deployment.md §2).
#
# Targets:
#   - frontend-builder : Builds static SPA assets (npm ci && npm run build -> /app/frontend/dist).
#   - caddy            : Production Caddy reverse proxy + baked-in static SPA assets (/srv/app).
#   - backend-builder  : Installs frozen Python production dependencies via uv (--frozen --no-dev).
#   - backend (default): Non-root runtime image shared by API, worker, migrations, and CLI.

# --- Stage 1: Frontend static build ----------------------------------------------------------
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json frontend/vite.config.ts ./
COPY frontend/src ./src

# Only VITE_API_BASE_URL is accepted at build time (empty = same origin; ADR-017 / INV-10).
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# --- Stage 2: Caddy reverse proxy + static SPA -----------------------------------------------
FROM caddy:2.8-alpine AS caddy

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend-builder /app/frontend/dist /srv/app

EXPOSE 80 443 443/udp

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["wget", "--no-verbose", "--tries=1", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]

# --- Stage 3: Backend frozen dependency builder ----------------------------------------------
FROM python:3.12-slim-bookworm AS backend-builder

COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# --- Stage 4: Non-root backend runtime (API, worker, migrations, CLI) ------------------------
FROM python:3.12-slim-bookworm AS backend

RUN groupadd --system --gid 10001 agentnest \
    && useradd --system --uid 10001 --gid 10001 --home-dir /app --no-create-home --shell /usr/sbin/nologin agentnest \
    && mkdir -p /app/backend/var/media /app/frontend/dist \
    && chown -R agentnest:agentnest /app

WORKDIR /app/backend

COPY --from=backend-builder --chown=agentnest:agentnest /app/backend/.venv /app/backend/.venv
COPY --chown=agentnest:agentnest backend/alembic.ini backend/pyproject.toml /app/backend/
COPY --chown=agentnest:agentnest backend/migrations /app/backend/migrations
COPY --chown=agentnest:agentnest backend/app /app/backend/app
COPY --from=frontend-builder --chown=agentnest:agentnest /app/frontend/dist /app/frontend/dist

ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONPATH="/app/backend" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER agentnest:agentnest

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
