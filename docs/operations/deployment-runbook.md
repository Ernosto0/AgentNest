# Production & Staging Deployment, Migration & Rollback Runbook

**Purpose:** Step-by-step operator runbook for bootstrapping a fresh Linux VPS, configuring GitHub Container Registry (GHCR) and verified SSH deployment, enforcing backward-compatible database migrations with separated credentials, executing application rollbacks safely, and running an optional staging environment (`P8-01`, `P8-12`; [deployment.md](../architecture/deployment.md), [ADR-017](../architecture/decisions/ADR-017-configuration-and-secrets.md), [ADR-025](../architecture/decisions/ADR-025-phase-8-hardening-contracts.md)).

---

## 1. Fresh VPS Bootstrap (Ubuntu 24.04 LTS)

### 1.1 Create Dedicated Non-Root Deploy User & SSH Access

Run as `root` on a fresh VPS (minimum 2 vCPU / 4 GB RAM for pilots):

```bash
# 1. Update packages and install Docker Engine + Compose v2 plugin + Python 3
apt-get update && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg ufw python3

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2. Create non-root deploy user and grant docker access
adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy

# 3. Install dedicated deploy SSH public key
install -d -m 0700 -o deploy -g deploy /home/deploy/.ssh
cat <<'EOF' > /home/deploy/.ssh/authorized_keys
ssh-ed25519 AAAA... agentnest-github-actions-deploy
EOF
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 0600 /home/deploy/.ssh/authorized_keys

# 4. Create application deployment directory
install -d -m 0750 -o deploy -g deploy /opt/agentnest
install -d -m 0750 -o deploy -g deploy /opt/agentnest/scripts
```

### 1.2 Configure Host Firewall (`ufw`)

Only SSH (`22/tcp`) and HTTP/HTTPS (`80/tcp`, `443/tcp`, `443/udp` for HTTP/3) are exposed. PostgreSQL (`5432`) and FastAPI (`8000`) stay on internal Docker bridge networks (`compose.prod.yml`):

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
ufw status verbose
```

### 1.3 Create & Lock Down `/opt/agentnest/.env` (`0600` Permissions)

On the server as `deploy`, create `/opt/agentnest/.env` from `.env.example` and lock permissions to `0600` (`INV-10`, `ADR-017`):

```bash
umask 0077
touch /opt/agentnest/.env
chown deploy:deploy /opt/agentnest/.env
chmod 0600 /opt/agentnest/.env
```

Generate production secrets using a local or one-off container command:

```bash
docker run --rm ghcr.io/<owner>/agentnest-backend:<tag> python -m app.cli generate-key --kind secret
docker run --rm ghcr.io/<owner>/agentnest-backend:<tag> python -m app.cli generate-key --kind token-encryption --key-id k1
```

Required production `.env` settings (validated before every deploy by `python -m app.cli check-config --production`):

- `APP_ENV=production`
- `APP_DOMAIN=app.example.com`
- `APP_BASE_URL=https://app.example.com`
- `FRONTEND_ORIGIN=https://app.example.com`
- `SECRET_KEY=<>=32-byte random secret>`
- `COOKIE_SECURE=true`
- `DEMO_TOOLS_ENABLED=false`
- `DATABASE_URL=postgresql+psycopg://agentnest_app:<app_password>@postgres:5432/agentnest`
- `MIGRATION_DATABASE_URL=postgresql+psycopg://agentnest_migrator:<migrator_password>@postgres:5432/agentnest`
- `LLM_PROVIDER=openai` and `OPENAI_API_KEY=sk-...`
- `INSTAGRAM_ENABLED_PROVIDERS=meta` (with `META_APP_ID`, `META_APP_SECRET`, `META_WEBHOOK_VERIFY_TOKEN`, `META_OAUTH_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEYS`, `TOKEN_ENCRYPTION_ACTIVE_KEY_ID`, and `MEDIA_STORAGE_BACKEND=s3` + `S3_*` credentials)

> **Important (`chmod 600` enforcement):** `scripts/deploy.sh` and `scripts/deploy.py` inspect `.env` permissions during preflight on POSIX hosts and refuse to run if group or world permission bits (`0077`) are set.

### 1.4 Configure GitHub Environment Secrets & Verified Host Identity

Capture the VPS SSH host key from a trusted machine:

```bash
ssh-keyscan -p 22 -t ed25519 <vps-ip-or-hostname>
```

Verify the fingerprint on the VPS (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`), then configure the following in GitHub (`Settings -> Environments -> production` and optional `staging`):

| Name | Kind | Description |
|---|---|---|
| `DEPLOY_SSH_HOST` | Secret | VPS hostname or IP address |
| `DEPLOY_SSH_USER` | Secret | Non-root SSH user (`deploy`) |
| `DEPLOY_SSH_PRIVATE_KEY` | Secret | Ed25519 private key matching `/home/deploy/.ssh/authorized_keys` |
| `DEPLOY_SSH_KNOWN_HOSTS` | Secret | Verified `ssh-keyscan -t ed25519` line(s); enforced with `StrictHostKeyChecking=yes` |
| `GHCR_READ_TOKEN` | Secret | Optional PAT (`read:packages`) if `GITHUB_TOKEN` lacks package pull scope on the server |
| `DEPLOY_SSH_PORT` | Variable | Optional SSH port (defaults to `22`) |
| `DEPLOY_PATH` | Variable | Optional target directory (defaults to `/opt/agentnest`) |

---

## 2. Separated Migration and Runtime Database Credentials (`ADR-025` §1.1)

Production separates DDL/schema migration authority from runtime request and job execution:

| Variable | Database Role | Used By | Privileges |
|---|---|---|---|
| `MIGRATION_DATABASE_URL` | `agentnest_migrator` | One-off `migrate` service (`alembic upgrade head`) | Schema and table owner, RLS policy creator, `SECURITY DEFINER` bootstrap function owner |
| `DATABASE_URL` | `agentnest_app` / `agentnest_worker` | `api` and `worker` containers | `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`; DML only (`REVOKE UPDATE, DELETE` on `audit_logs` and `fact_versions`) |

**Container boundary enforcement (`compose.prod.yml`):**
- The `migrate` service (`profiles: ["migrate", "ops"]`) reads `MIGRATION_DATABASE_URL` from `.env` (falling back to `DATABASE_URL` only in local/single-role setups).
- The `api` and `worker` services explicitly set `MIGRATION_DATABASE_URL: ""` in their container `environment:` block so long-running runtime containers never hold the migration role's credentials in memory or `/proc/1/environ`.
- Verify separation at any time with:
  ```bash
  docker compose -f compose.prod.yml --env-file .env --profile ops run --rm --no-deps migrate \
    python -m app.cli check-config --production --require-separated-migration-credentials
  ```

---

## 3. Backward-Compatible Migrations & Failed-Migration Response

### 3.1 Expand -> Migrate -> Contract Discipline

Because `migrate` (`alembic upgrade head`) runs **before** `api` and `worker` are restarted (`deployment.md` §2), every production migration must remain backward-compatible with the currently running application version:

1. **Expand (Release N):**
   - Add new tables, nullable columns, or column defaults that old code can ignore safely.
   - Never drop, rename, or tighten the type/nullability of a column that Release N-1 still reads or writes.
2. **Migrate & Switch (Release N / N+1):**
   - Backfill existing rows idempotently and deploy application code that writes/reads the new schema.
3. **Contract (Release N+1 or later):**
   - Only after Release N is live and stable (and no rollback to Release N-1 is needed), remove obsolete columns or add strict `NOT NULL` constraints in a later migration.

### 3.2 Safe Operator Response to a Failed Migration

Alembic runs migrations inside a PostgreSQL transaction (`migrations/env.py`). If `docker compose --profile migrate run --rm migrate` fails during deployment:

1. **Automatic halt before rollout:** `scripts/deploy.sh` records `status: "migration_failed"` in `.deploy-state`, prints diagnostic logs, and **exits non-zero without restarting `api`, `worker`, or `caddy`**.
2. **Inspect current DB revision vs image head:**
   ```bash
   python3 scripts/deploy.py status
   docker compose -f compose.prod.yml --env-file .env --profile ops run --rm migrate \
     python -m app.cli migration-status
   ```
3. **If `current_revision` is unchanged (`current_revision == previous_db_revision`):**
   - PostgreSQL rolled back the failed DDL transaction cleanly. The previous `api` and `worker` containers are still running on the matching schema. Fix the migration in code and tag a new release.
4. **If a non-transactional migration partially applied or `current_revision` advanced:**
   - **Do NOT run `alembic downgrade` blindly on production data**, and **do NOT force an image-only rollback** (which `scripts/rollback.sh` will refuse with exit code `3`).
   - Either deploy a tested forward-fix migration or restore the database from the pre-deploy encrypted backup (Session 04).

---

## 4. Deployment Workflow & Commands

### 4.1 Automated Tag-Triggered Deployment (`.github/workflows/deploy.yml`)

Pushing a version tag (`v*`) triggers `.github/workflows/deploy.yml`:

```bash
git tag v0.8.0
git push origin v0.8.0
```

You can also trigger a deployment manually via GitHub Actions (`Actions -> Deploy -> Run workflow`), selecting:
- `environment`: `production` or `staging`
- `image_tag`: explicit tag (e.g. `v0.8.0` or `sha-641b1f5...`)
- `skip_build`: `true` to deploy an already-published GHCR image tag without rebuilding

### 4.2 Manual / SSH Deployment on the VPS

From `/opt/agentnest` as `deploy`:

```bash
./scripts/deploy.sh \
  --image-tag v0.8.0 \
  --env-file .env \
  --project-name agentnest
```

What `scripts/deploy.sh` (`scripts/deploy.py deploy`) does in order:
1. Acquires an exclusive non-blocking lock on `.deploy.lock` (`exit code 2` if another deploy or rollback is active).
2. Verifies `.env` exists and has `0600` permissions, validates `compose.prod.yml`, pulls images for `--image-tag`, and runs `python -m app.cli check-config --production` inside the target image.
3. Records pre-deploy state (`active_image_tag`, `previous_db_revision`, `candidate_image_tag`, `target_head_revision`) in `.deploy-state`.
4. Runs `docker compose -f compose.prod.yml --env-file .env --profile migrate run --rm migrate` (`alembic upgrade head`).
5. Runs `docker compose -f compose.prod.yml --env-file .env up -d --remove-orphans api worker caddy`.
6. Polls `http://127.0.0.1:${HTTP_PORT:-80}/readyz` until HTTP `200` (`{"status": "ok", "checks": {"database": true, "migrations": true}}`) and verifies `api`, `worker`, and `caddy` containers are running.
7. Updates `.deploy-state` to `status: "succeeded"` and `active_image_tag: <tag>`. If any step fails, emits redacted `docker compose ps -a` and container log tails (`api`, `worker`, `caddy`) and exits non-zero.

---

## 5. Application Rollback vs. Database Restoration

### 5.1 Decision Matrix

| Scenario | Database Revision State | Safe Action | Command |
|---|---|---|---|
| Bad application release, config regression, or failed `/readyz` with **no new migration applied** | `current_revision == target_rollback_head` | **Application Image Rollback** | `./scripts/rollback.sh` (or `./scripts/rollback.sh --to-tag <prev_tag>`) |
| Failed migration that rolled back cleanly in PostgreSQL | `current_revision == previous_db_revision` | **Keep current containers running** (or `./scripts/rollback.sh` if containers were touched) | `./scripts/rollback.sh` |
| Forward migration (`0031+`) was already committed to the database | `current_revision != target_rollback_head` | **Image-only rollback is BLOCKED (`exit code 3`)** | Deploy a forward-fix release **or** execute a full Database Backup Restore (Session 04) |

### 5.2 Executing an Application Rollback

From `/opt/agentnest` as `deploy`:

```bash
# Roll back to previous_image_tag recorded in .deploy-state:
./scripts/rollback.sh --env-file .env --project-name agentnest

# Or specify an explicit target image tag:
./scripts/rollback.sh --to-tag v0.7.9 --env-file .env --project-name agentnest
```

`scripts/rollback.sh` (`scripts/deploy.py rollback`):
1. Acquires `.deploy.lock`.
2. Runs preflight on the target rollback image and queries `python -m app.cli migration-status` to compare the database's live `current_revision` against the rollback image's `head_revision` and `known_revisions`.
3. **Blocks rollback (`exit code 3`)** if `current_revision != target_head_revision`, preventing an old image from running against a newer schema or failing `/readyz`.
4. Recreates `api`, `worker`, and `caddy` with the rollback image tag, polls `/readyz` until green, and records `status: "rolled_back"` in `.deploy-state`.

---

## 6. Worker Lease Drain & Uncertain-Operation Preservation (`INV-05`, `INV-07`)

During every deployment or rollback restart:

1. **Graceful lease drain (`INV-07`):**
   - `compose.prod.yml` configures `worker` with `init: true` and `stop_grace_period: 35s`, which exceeds `SHUTDOWN_GRACE_SECONDS = 30.0` in `backend/app/jobs/worker.py`.
   - On `SIGTERM`, the worker sets its stop event, stops claiming new jobs from `jobs`, and waits up to 30 seconds for active worker threads to finish and commit `mark_succeeded`.
2. **Lease recovery for long-running jobs (`INV-07`):**
   - Any job that does not complete within the 30-second drain window remains `status = 'running'` in PostgreSQL until its `locked_until` (`JOB_LEASE_SECONDS`, default `120s`) expires, after which the new worker reclaims it safely (`FOR UPDATE SKIP LOCKED`) with idempotent handlers (`INV-06`).
3. **Uncertain external operations (`INV-05`):**
   - Every outbound DM send or content publish writes a committed `operations` row (`status = 'in_progress'`) **before** calling the external provider (`INV-15`).
   - If a worker is killed mid-call during a deploy or crash, the operation is **never** retried blindly. The periodic `reconcile_stuck_operations` job transitions any `in_progress` operation older than `STUCK_AFTER` (`15m`) to `outcome_unknown` and enqueues `reconcile_send` or `reconcile_publish` to verify delivery via echo webhooks or provider lookup before concluding.

---

## 7. Optional Staging Environment (`P8-12`)

Staging uses the **exact same** `compose.prod.yml`, `Caddyfile`, `.github/workflows/deploy.yml`, `scripts/deploy.sh`, and `scripts/rollback.sh` parameterized via environment variables:

```bash
# On a separate staging VM or isolated side-by-side directory:
# 1. Create .env.staging with chmod 600 (distinct DB credentials, APP_DOMAIN=staging.example.com,
#    test Meta app credentials, and optional HTTP_PORT=8080 / HTTPS_PORT=8443 if side-by-side)
chown deploy:deploy /opt/agentnest/.env.staging
chmod 0600 /opt/agentnest/.env.staging

# 2. Deploy staging stack
./scripts/deploy.sh \
  --image-tag v0.8.0-rc1 \
  --env-file .env.staging \
  --project-name agentnest-staging

# 3. Inspect staging state (.deploy-state.agentnest-staging)
python3 scripts/deploy.py status --project-name agentnest-staging --env-file .env.staging

# 4. Roll back staging stack if needed
./scripts/rollback.sh \
  --env-file .env.staging \
  --project-name agentnest-staging
```
