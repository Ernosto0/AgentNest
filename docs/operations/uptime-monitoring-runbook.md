# Uptime Monitoring Runbook (External `/readyz` and `/healthz` Checks)

- **Target Phase / Task:** Phase 8 Session 13 (`P8-07`, `ADR-018`, `ADR-025`)
- **Status:** Production Standard
- **Audience:** DevOps, Site Reliability Engineers, System Administrators

---

## 1. Overview & Health Probes Architecture

AgentNest provides two dedicated HTTP probes mounted at the root path of the API application:

| Endpoint | Probe Type | Purpose | Behavior & Dependencies | Expected Healthy Response | Unhealthy Status |
|---|---|---|---|---|---|
| `GET /healthz` | **Liveness** | Verifies process is alive and accepting connections | Never connects to the database or external services. Extremely fast (< 1 ms). | `200 OK`<br>`{"status": "ok"}` | Connection refused or process crash (502 / 504 from Caddy) |
| `GET /readyz` | **Readiness** | Verifies database connectivity and schema migrations | Executes `SELECT 1` on PostgreSQL and compares the active Alembic revision against the code's expected migration head (`check_readiness()`). | `200 OK`<br>`{"status": "ok", "checks": {"database": true, "migrations": true}}` | `503 Service Unavailable`<br>`{"status": "unavailable", "checks": {"database": false, ...}}` |

---

## 2. Probe Configuration Recommendations

### 2.1 Recommended Parameters

- **Target URL:** `https://<DOMAIN>/readyz`
- **HTTP Method:** `GET`
- **Expected Status Code:** `200 OK`
- **Expected Body Content:** `"status": "ok"`
- **Request Interval (Cadence):**
  - Production: Every **30 seconds** (or 60 seconds)
  - Staging / Dev: Every **60 seconds**
- **Timeout:** **5 seconds**
- **Failure Threshold:** **2 consecutive failures** before paging operators (prevents transient network flutters from waking on-call).
- **Recovery Threshold:** **2 consecutive successful probes** before closing the incident.
- **Request Headers:**
  - `User-Agent: AgentNest-Uptime-Monitor/1.0`
  - `Accept: application/json`

---

## 3. External Monitoring Provider Configurations

### 3.1 Uptime Kuma

```json
{
  "name": "AgentNest Production Readiness",
  "type": "http",
  "url": "https://agentnest.example.com/readyz",
  "interval": 30,
  "retryInterval": 15,
  "maxretries": 2,
  "timeout": 5,
  "accepted_statuscodes": ["200"],
  "keyword": "\"status\":\"ok\"",
  "method": "GET"
}
```

### 3.2 Better Stack (Better Uptime)

1. **Monitor Type:** URL / HTTP monitor
2. **URL:** `https://agentnest.example.com/readyz`
3. **Alerting rule:** Alert if status code is not `200` OR response body does not contain `"status": "ok"`.
4. **Check frequency:** 30 seconds.
5. **Request timeout:** 5 seconds.
6. **Grace period:** 1 minute (2 consecutive checks).

### 3.3 Datadog Synthetics (API HTTP Test)

```yaml
name: "AgentNest Production /readyz Check"
type: api
subtype: http
request:
  method: GET
  url: "https://agentnest.example.com/readyz"
  timeout: 5
assertions:
  - type: statusCode
    operator: is
    target: 200
  - type: header
    property: content-type
    operator: contains
    target: application/json
  - type: body
    operator: contains
    target: '"database": true'
locations:
  - aws:eu-central-1
  - aws:eu-west-1
options:
  tick_every: 30
  min_failure_duration: 60
  min_location_failed: 2
```

### 3.4 AWS Route 53 Health Check

- **Type:** HTTP / HTTPS
- **Domain Name:** `agentnest.example.com`
- **Port:** `443`
- **Path:** `/readyz`
- **Request Interval:** Standard (30 seconds)
- **Failure Threshold:** 2
- **String Matching:** Enabled; search string: `"status":"ok"`

---

## 4. Triage & Incident Remediation

When `/readyz` transitions to `503 Service Unavailable` or connection refused:

### Step 1: Inspect Response Payload
```bash
curl -i https://agentnest.example.com/readyz
```

- **If `database: false`:**
  - Check whether PostgreSQL container is running:
    ```bash
    docker compose -f compose.prod.yml ps postgres
    docker compose -f compose.prod.yml logs --tail 100 postgres
    ```
  - Verify PostgreSQL connection pool and disk space (`df -h`).
- **If `migrations: false` (Database reachable, migrations pending):**
  - Indicates the application was restarted with newer code before `alembic upgrade head` completed, or a migration failed.
  - Inspect current database revision:
    ```bash
    docker compose -f compose.prod.yml run --rm api uv run alembic current
    ```
  - Apply pending migrations manually:
    ```bash
    docker compose -f compose.prod.yml run --rm api uv run alembic upgrade head
    ```

### Step 2: Check Caddy / Reverse Proxy
- If curl returns `502 Bad Gateway`:
  - The API container is restarting or down.
  - Check container status:
    ```bash
    docker compose -f compose.prod.yml ps api
    docker compose -f compose.prod.yml logs --tail 200 api
    ```

---

## 5. Security & Privacy Considerations

- `/readyz` and `/healthz` are intentionally **unauthenticated** so third-party uptime monitors can probe them without credentials.
- The readiness report returns only boolean check states (`{"database": true, "migrations": true}`); it **never** exposes database credentials, hostnames, connection strings, table counts, or customer data (`INV-08`, `INV-18`).
- Public proxy configuration in `Caddyfile` permits `/healthz` and `/readyz` without CSRF or session cookies.
