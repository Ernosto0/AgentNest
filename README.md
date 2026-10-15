# AgentNest

AgentNest (working name) is an Instagram operations assistant for small businesses. It keeps verified business knowledge, drafts grounded replies to customer DMs, prepares and schedules content behind explicit approvals, and reports honestly on what happened. Turkish-first, mobile-first, and fully demonstrable locally on simulated integrations (no credentials needed).

The specification lives in [docs/](docs/README.md). Coding agents: read [CLAUDE.md](CLAUDE.md) first.

## Quickstart

Prerequisites: Git, Docker Desktop, [uv](https://docs.astral.sh/uv/), Node.js LTS (>= 20).

```bash
cp .env.example .env                      # PowerShell: Copy-Item .env.example .env
docker compose up -d postgres             # Postgres 16 on localhost:5433

cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed --reset     # demo users and workspaces

cd ../frontend
npm ci
```

Run (separate terminals):

```bash
cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000
cd backend && uv run python -m app.worker
cd frontend && npm run dev                # http://localhost:5173
```

Log in as `owner@demo.local` with the value of `DEMO_PASSWORD`. Full instructions: [docs/operations/local-development.md](docs/operations/local-development.md).
