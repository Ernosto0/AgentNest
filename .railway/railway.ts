import {
  defineRailway,
  github,
  postgres,
  service,
} from "railway/iac";

const db = postgres("Postgres");

const api = service("api", {
  source: github("Ernosto0/AgentNest", { branch: "main" }),
  dockerfilePath: "Dockerfile",
  preDeploy: "alembic upgrade head",
  start: "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 2",
  healthcheck: "/readyz",
  env: {
    DATABASE_URL: db.env.DATABASE_URL,
    APP_ENV: "production",
    APP_BASE_URL: "https://web-production-b2f30.up.railway.app",
    FRONTEND_ORIGIN: "https://web-production-b2f30.up.railway.app",
    META_OAUTH_REDIRECT_URI: "https://web-production-b2f30.up.railway.app/oauth/instagram/callback",
    COOKIE_SECURE: "true",
    DEMO_TOOLS_ENABLED: "false",
    LOG_FORMAT: "json",
    LOG_LEVEL: "INFO",
    TRUSTED_PROXY_CIDRS: "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
  },
});

const worker = service("worker", {
  source: github("Ernosto0/AgentNest", { branch: "main" }),
  dockerfilePath: "Dockerfile",
  start: "python -m app.worker",
  env: {
    DATABASE_URL: db.env.DATABASE_URL,
    APP_ENV: "production",
    APP_BASE_URL: "https://web-production-b2f30.up.railway.app",
    FRONTEND_ORIGIN: "https://web-production-b2f30.up.railway.app",
    COOKIE_SECURE: "true",
    DEMO_TOOLS_ENABLED: "false",
    LOG_FORMAT: "json",
    LOG_LEVEL: "INFO",
  },
});

const web = service("web", {
  source: github("Ernosto0/AgentNest", { branch: "main" }),
  dockerfilePath: "Dockerfile.web",
  healthcheck: "/healthz",
  domains: ["web-production-b2f30.up.railway.app"],
  env: {
    API_UPSTREAM: "api.railway.internal:8000",
    APP_DOMAIN: ":80",
  },
});

export default defineRailway({
  services: [db, api, worker, web],
});

