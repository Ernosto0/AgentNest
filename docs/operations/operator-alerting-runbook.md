# Operator Alerting and Incident Runbook

- **Target Phase / Task:** Phase 8 Session 13 (`P8-07`, `ADR-018`, `ADR-025 §4.3`)
- **Status:** Production Standard
- **Audience:** Operators, SREs, System Administrators, On-Call Engineers

---

## 1. Overview & Alerting Architecture

AgentNest evaluates 8 canonical operational conditions designed to catch silent failures, data synchronization stalls, capability degradations, and security anomalies before they cause business disruption.

Alert evaluations run via two independent, decoupled mechanisms:
1. **Background Worker Periodic Job:** `enqueue_operator_alert_evaluation` runs every 5 minutes and claims `evaluate_operator_alerts`.
2. **Independent Administrative CLI:** `python scripts/evaluate_alerts.py` runs out-of-band directly against PostgreSQL, ensuring that worker crashes or dead queues do not blind the operator.

Durable state tracking in table `operator_alert_states` prevents notification storms through exponential/fixed cooldown windows, tracks notification counts, and automatically emits **recovery notices** (`firing -> resolved`) when problems clear.

---

## 2. Canonical Alert Catalog & Incident Playbooks

| ID | Alert Key Pattern | Category | Severity | Threshold / Condition | Cooldown | Primary Remediation Action |
|---|---|---|---|---|---|---|
| **A1** | `dead_job:<job_type>` | `jobs` | **CRITICAL** | Any background job transitions to `status = 'dead'`. | 1 hour | Inspect `Job.last_error_code`, verify external dependencies, and retry job via CLI or admin script. |
| **A2** | `backup:stale_or_failed` | `backup` | **CRITICAL** | `last_backup_status == 'failed'` or > 26 hours since last verified backup snapshot. | 6 hours | Check host cron, inspect `.backup-status.json`, verify disk space and S3 credentials; trigger manual backup drill. |
| **A3** | `webhook:signature_failure_burst` | `security` | **WARNING** | ≥ 10 `webhook.signature_invalid` audit events in 1 hour. | 1 hour | Check if `META_APP_SECRET` was rotated in Meta App Dashboard, or inspect client IPs for spoofing/replay attacks. |
| **A4** | `account_needs_reauth:<id>` | `accounts` | **WARNING** | Social account remains in `needs_reauth` for > 24 hours. | 24 hours | Notify business owner to reconnect account via OAuth in Settings (`user-journeys.md §1`). |
| **A5** | `agent_health:dead_job:<type>`<br>`agent_health:stuck_session:<id>` | `agent` | **CRITICAL** (dead)<br>**WARNING** (stuck) | Dead `agent_wake`/`agent_recover` job, or `agent_sessions` stuck in `active`/`in_progress` > 30 minutes. | 1 hour | Inspect `agent_sessions.goal_key`, investigate tool timeouts, and run `reconcile_stuck_operations` or agent recovery. |
| **A6** | `unresolved_operation:<id>` | `operations` | **WARNING** | Operation remains in `outcome_unknown` > 30 minutes without automated reconciliation. | 2 hours | Check Meta API status, verify `provider_ref`, and execute manual reconciliation CLI if provider confirmed. |
| **A7** | `capability_loss:<id>` | `accounts` | **WARNING** | Connected account receives `CAPABILITY_MISSING` (e.g. Instagram permissions revoked). | 6 hours | Ask workspace owner to reconnect Instagram account and approve all requested page permissions. |
| **A8** | `ai_budget_exhausted:workspace:<id>`<br>`circuit_open:account:<id>` | `agent` / `accounts` | **WARNING** | AI runs exceeded daily budget quota, or circuit breaker opened (`degraded` status with `degraded_until`). | 6 hours | Verify LLM quota/pricing tiers, inspect sudden message spikes, or increase workspace daily limit if legitimate. |

---

## 3. Incident Playbooks & Remediation Steps

### Playbook A1: Dead Background Jobs (`dead_job:<job_type>`)
- **Severity:** `CRITICAL`
- **Symptom:** Worker exhausted all retry attempts (`max_attempts`) and marked the job `dead`.
- **Diagnosis:**
  ```sql
  SELECT id, job_type, attempts, last_error_code, last_error_detail, run_at
  FROM jobs
  WHERE status = 'dead' ORDER BY run_at DESC LIMIT 10;
  ```
- **Remediation:**
  1. If `last_error_code == 'PROVIDER_UNAVAILABLE'`, verify network egress to Meta/OpenAI.
  2. If the failure was transient and resolved, reset the job to `queued`:
     ```sql
     UPDATE jobs SET status = 'queued', attempts = 0, last_error_code = NULL, run_at = now()
     WHERE id = '<job_id>';
     ```

---

### Playbook A2: Backup Stale or Failed (`backup:stale_or_failed`)
- **Severity:** `CRITICAL`
- **Symptom:** No backup has succeeded in > 26 hours, violating RPO requirements.
- **Diagnosis:**
  ```bash
  cat .backup-status.json
  # Or inspect audit log:
  docker compose -f compose.prod.yml run --rm api uv run python -c \
    "from app.operations.system_health import backup_health; print(backup_health())"
  ```
- **Remediation:**
  1. Trigger manual backup execution:
     ```bash
     ./scripts/backup.sh --output-dir /var/backups/agentnest
     ```
  2. If S3 upload failed, verify `BACKUP_S3_ACCESS_KEY_ID` and `BACKUP_S3_SECRET_ACCESS_KEY`.
  3. Ensure disk partition has sufficient space (`df -h /var/backups`).

---

### Playbook A3: Webhook Signature Failure Burst (`webhook:signature_failure_burst`)
- **Severity:** `WARNING`
- **Symptom:** ≥ 10 forged or invalid HMAC signatures received within 60 minutes.
- **Diagnosis:**
  ```sql
  SELECT occurred_at, metadata
  FROM audit_logs
  WHERE action = 'webhook.signature_invalid'
    AND occurred_at >= now() - interval '1 hour'
  ORDER BY occurred_at DESC;
  ```
- **Remediation:**
  1. Verify if `META_APP_SECRET` in `.env` matches the Meta Developer App Dashboard.
  2. Check web server logs (`docker compose logs caddy`) to identify attacking IP addresses and configure rate limiting or IP banning if malicious.

---

### Playbook A4: Connected Account Stuck in Needs Reauth (`account_needs_reauth:<id>`)
- **Severity:** `WARNING`
- **Symptom:** Token expired or was invalidated, and the owner has not reconnected after 24 hours.
- **Remediation:**
  1. System sends automated dashboard notifications to workspace managers.
  2. Contact the business owner to log in and re-authorize via `GET /oauth/instagram/authorize`.

---

### Playbook A5: Agent Dead Job or Stuck Session (`agent_health:*`)
- **Severity:** `CRITICAL` (dead job) / `WARNING` (stuck session)
- **Symptom:** Agent session in `active` state with no updates for > 30 minutes.
- **Diagnosis:**
  ```sql
  SELECT id, thread_id, status, goal_key, updated_at
  FROM agent_sessions
  WHERE status IN ('active', 'in_progress') AND updated_at < now() - interval '30 minutes';
  ```
- **Remediation:**
  1. Inspect the last agent step:
     ```sql
     SELECT id, session_id, step_kind, outcome_code, created_at
     FROM agent_steps WHERE session_id = '<session_id>' ORDER BY created_at DESC LIMIT 5;
     ```
  2. If the session hung during LLM inference or an external tool call, mark it cancelled or trigger reconciliation.

---

### Playbook A6: Unresolved Operation (`unresolved_operation:<id>`)
- **Severity:** `WARNING`
- **Symptom:** An outbound send or publish operation entered `outcome_unknown` and was not auto-reconciled after 30 minutes.
- **Remediation:**
  1. Never retry blind sending (`INV-05`).
  2. Check Instagram directly or inspect the provider's API for the presence of `text_sha256` or `idempotency_key`.
  3. Reconcile explicitly to `succeeded` or `failed`.

---

### Playbook A7: Capability Loss (`capability_loss:<id>`)
- **Severity:** `WARNING`
- **Symptom:** Account connected but received `CAPABILITY_MISSING`.
- **Remediation:**
  1. Account owner removed Instagram messaging or comment permissions in the Meta Accounts Center.
  2. Request the owner reconnect the account and check all permission grant boxes.

---

### Playbook A8: AI Budget Exhaustion / Circuit Breaker (`ai_budget_exhausted:*`)
- **Severity:** `WARNING`
- **Symptom:** Daily AI quota exhausted or transient API failure threshold reached.
- **Remediation:**
  1. If circuit breaker opened (`degraded` status), the account will auto-recover when `degraded_until` passes.
  2. If `daily_budget_exhausted`, review whether the tenant needs a higher quota tier or if an inbound spam loop triggered excessive turns.

---

## 4. Operator CLI & Manual Evaluation

Operators can execute the alert evaluation engine directly from the host terminal:

```bash
# Basic evaluation (updates DB state and prints human-readable summary)
python scripts/evaluate_alerts.py

# Verbose output with detailed candidate metadata
python scripts/evaluate_alerts.py --verbose

# JSON output for ingestion by monitoring daemons / Zabbix / Datadog
python scripts/evaluate_alerts.py --json

# Override alert notification email for one-off testing
python scripts/evaluate_alerts.py --email oncall@example.com
```

---

## 5. Alert Delivery Failure Handling

If transactional email delivery fails (e.g. SMTP down or misconfigured):
1. The error is caught and logged as `operator_alert_delivery_failed`.
2. An immutable audit log entry is written: `security.alert_delivery_failed` (`metadata: {"alert_key": "...", "error": "..."}`).
3. The alert state in `operator_alert_states` is **still persisted** with `status = 'firing'`.
4. Subsequent evaluations or CLI inspections (`python scripts/evaluate_alerts.py`) continue to surface the active alert.
