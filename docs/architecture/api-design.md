# API Design

**Purpose:** HTTP API conventions and endpoint groups, with request and response shapes where they matter for correctness. FastAPI generates the full OpenAPI schema from code. This document defines the contract that the code must satisfy and the phase that introduces each group.

## 1. Conventions

| Topic | Rule |
|---|---|
| Base path | `/api/v1`. Workspace-scoped resources live under `/api/v1/workspaces/{workspace_id}/…`. Public integration endpoints are under `/webhooks/…` and `/oauth/…` (no `/api/v1` prefix). |
| Format | JSON, UTF-8. Field names in `snake_case`. |
| Auth | Session cookie `agentnest_session` (HttpOnly, Secure in prod, SameSite=Lax). State-changing requests (POST/PUT/PATCH/DELETE) require the header `X-CSRF-Token` equal to the session's CSRF token (from `GET /auth/me`). |
| Tenancy | `require_membership(workspace_id, permission)` on every workspace route. A resource from another workspace → **404** (not 403). Missing permission within one's own workspace → 403 `FORBIDDEN`. |
| Errors | RFC 9457 `application/problem+json`: `{"type": "about:blank", "title": "...", "status": 409, "code": "APPROVAL_STALE", "params": {...}, "detail": "<localised fallback>", "request_id": "..."}`. Validation errors: 422 `VALIDATION_FAILED` with `errors: [{field, code, params}]`. The catalog is in [observability.md §4](observability.md). |
| Pagination | Cursor-based: `?limit=20&cursor=<opaque>`; response `{"items": [...], "next_cursor": "..."|null}`. Default limit 20, max 100. |
| Time | Instants as ISO 8601 UTC (`2026-10-15T16:00:00Z`). Every resource with time semantics also includes display helpers computed server-side where ambiguity matters (e.g., `scheduled_local: {date, time, timezone}`). |
| Money | Never as floats. Fact values as typed JSON ([business-knowledge.md §2](business-knowledge.md)) plus a `display` string rendered in the user's UI locale. |
| Async operations | `202 Accepted` + the resource (with `status`). The client polls `GET` on the resource. Terminal and waiting states are documented per resource ([state-machines.md](state-machines.md)). |
| Client retries | Creation endpoints that the user may resubmit (commands, extraction, manual replies, content generation) accept `client_request_id` (UUID). Uniqueness per user returns the existing resource on resubmission. |
| Optimistic concurrency | Mutable resources expose `version`. PATCH/submit requests send `expected_version`; a mismatch → 409 `VERSION_CONFLICT`. |
| Simulation | Every resource that can be simulated has `is_simulated: bool`. |
| Secrets | Response models are explicit allow-lists. No model ever includes token, hash or secret fields ([INV-10](../invariants.md)). |

## 2. Endpoint groups

Permissions refer to the matrix in [security-and-privacy.md §3](security-and-privacy.md).

### 2.1 Health and meta (Phase 1)
| Method & path | Notes |
|---|---|
| `GET /healthz` | Liveness (no DB). |
| `GET /readyz` | DB reachable, migrations at head. |
| `GET /api/v1/meta` | Public non-secret config for the SPA: `{product_name, demo_tools_enabled, llm_mode: "fake"|"real" (from `LLM_PROVIDER`), supported_locales}`. |

### 2.2 Auth and identity (Phase 1; invites Phase 6)
| Method & path | Request → Response |
|---|---|
| `POST /api/v1/auth/login` | `{email, password}` → 204 + session cookie. 401 `INVALID_CREDENTIALS` (generic). |
| `POST /api/v1/auth/logout` | → 204. |
| `GET /api/v1/auth/me` | → `{user: {id, email, display_name, ui_locale}, csrf_token, memberships: [{workspace_id, workspace_name, role, is_demo}]}` |
| `PATCH /api/v1/auth/me` | `{display_name?, ui_locale?}` |
| `GET /api/v1/workspaces` | memberships list |
| `POST /api/v1/workspaces` | `{name, business_category, market, default_locale, timezone, currency}` → workspace |
| `GET/PATCH /api/v1/workspaces/{ws}` | settings (`workspace.manage` for PATCH). `settings.automation_reviewed_at` is read-only: the server stamps it when the owner saves the automation policies (`PUT /automation-policies`) |
| `GET /api/v1/workspaces/{ws}/members` | |
| `PATCH/DELETE /api/v1/workspaces/{ws}/members/{user_id}` | role change, removal (`members.manage`). The last owner cannot be removed. |
| `POST /api/v1/workspaces/{ws}/invites` | `{role}` → `{invite_url, expires_at}` (Phase 6) |
| `POST /api/v1/invites/accept` | `{token, display_name, password}` or the authenticated user → membership |

### 2.3 Knowledge (Phase 2; extraction Phase 3; approved answers Phase 4)
| Method & path | Request → Response |
|---|---|
| `GET /…/facts?category=&status=` | `{items: [{kind: "fact", id, key, category, label, value_type, value, display, status, state, criticality, current_version, valid_from, valid_until, last_verified_at, last_verified_by_name, source_type, usable, open_candidates_count}], next_cursor}`. `display` is rendered in the **user's UI locale** (not the workspace locale). `state` is the owner-facing label: `verified`, `unverified`, `contested`, `expired`, `not_started` or `archived`. `source_type` is the source of the current version (so verified facts can show where they came from). Read: any member |
| `GET /…/facts/template` | `[{identifier, key \| pattern, category, label, description, value_types, criticality, required_for, required_group, required_when, allowed_values, status, fact_ids}]` for the workspace's category template; `status` is `missing`, `present` (pattern items) or the state of the fact. Drives the checklist. Read: any member |
| `POST /…/facts` | `{key, value, value_type?, label?, criticality?, valid_from?, valid_until?, reason?}` → **201** fact (verified, for `knowledge.verify`) or **202** `{kind: "candidate", …}` (staff). The key must be a template key, a pattern key (`service.<slug>`; `label` required) or `custom.<slug>` (`value_type` and `label` required). Staff may only propose fixed template keys and cannot set a validity window (403). A live fact for the key → 409 `CONFLICT_STATE` |
| `PATCH /…/facts/{id}` | `{expected_version, value?, valid_from?, valid_until?, reason?}` → fact (200) or candidate (202, staff). A null `valid_from`/`valid_until` clears the window; omitting it leaves it unchanged. Staff cannot touch the window (403). Stale version → 409 `FACT_VERSION_CONFLICT` |
| `POST /…/facts/{id}/verify` | `{expected_version}` (`knowledge.verify`; an already verified fact → 409 `CONFLICT_STATE`) |
| `POST /…/facts/{id}/archive` / `restore` | `{expected_version, reason?}` (`knowledge.verify`). Restore returns the fact as `unverified`; it needs a free key |
| `GET /…/facts/{id}/versions` | version history, newest first: `{version, value, display, status, valid_from, valid_until, source_type, source_ref, actor_type, actor_name, reason, change_kind, created_at}` |
| `GET /…/fact-candidates?status=pending` | candidates with `relation`, `source_excerpt`, `fact_label`, `proposed_display`, `current_display`, `proposed_by_name` |
| `POST /…/fact-candidates/{id}/accept` / `reject` | `knowledge.verify`. Accept → fact (200); reject → candidate. A candidate that is no longer pending → 409 `CONFLICT_STATE` |
| `POST /…/knowledge/extractions` | `{text (≤ 8000 chars), client_request_id}` → 202 `{run_id, status, candidates_created, error_code, injection_suspected}` (`knowledge.edit`; idempotent per user and `client_request_id`). The text is stored only in the run's redacted input snapshot, never in the job payload |
| `GET /…/knowledge/extractions/{run_id}` | same shape. `status` is `queued`, `running`, `succeeded` or `failed`; `candidates_created` counts candidates that need a decision (equal values are not counted). Items whose excerpt is not verbatim, or that sit in an instruction-like line, are dropped, so the count can be 0 |
| `GET /…/readiness` | `{level: not_ready \| ready_for_drafts \| ready, requirements: [{code, required_for: drafts \| ready, satisfied, status, link: {target: knowledge \| integrations \| automation, category, key}, missing_keys}]}`. The `link` is structured so the API stays free of frontend routes. `status` is `ok`, `missing`, `not_connected` (no usable account) or `not_reviewed`. Codes: `business_name`, `contact`, `location`, `hours`, `booking_instructions`, `price_policy`, `services`, `account_connected`, `automation_reviewed`. Read: any member |
| `GET/POST/PATCH /…/approved-answers` | CRUD |
| `POST /…/approved-answers/from-message/{message_id}` | create from a sent reply |
| `GET/PUT /…/automation-policies` | `{items: [{action_class, mode: auto \| approval \| off}], readiness_level, auto_allowed, reviewed_at}`. GET: any member. PUT (`automation.manage`) takes `{items: [...]}` (classes not listed keep their mode; unlisted classes default to `approval`). Saving is the owner's review: the server stamps `automation_reviewed_at` once, from its clock, and audits `policy.updated` and `policy.reviewed`. `auto` is refused with `422 READINESS_NOT_READY` unless everything for `ready` except the review itself is in place |

### 2.4 Commands (Phase 3)
| Method & path | Request → Response |
|---|---|
| `POST /…/commands` | `{text, client_request_id}` → 202 `Command` |
| `GET /…/commands/{id}` | `Command` |
| `POST /…/commands/{id}/clarification` | `{option_id}` → 202 `Command` |
| `POST /…/commands/{id}/cancel` | |
| `GET /…/commands?limit=` | recent commands of the current user |

`Command = {id, status, raw_text, command_type, result: {message_key, params, links[]}|null, clarification: {question_key, params, options: [{id, label}]}|null, approval: ApprovalSummary|null, error_code, created_at, expires_at, completed_at}`

Commands are private to the member who typed them (another member's id → 404). `POST /…/commands` validates `text` (1–1000 characters after trimming) and `client_request_id` (non-empty, ≤ 100) with 422 `VALIDATION_FAILED`, and is idempotent per user and `client_request_id`. A clarification answer continues deterministically from the stored question (no new model call); an `option_id` that was not offered → 422. `cancel` is allowed from `needs_clarification` and `awaiting_confirmation` only (else 409 `CONFLICT_STATE`). Reads expire waiting commands lazily. `result.links` are structured (`{target: knowledge|approvals|content|inbox|integrations|automation|members, category?, key?}`), and results are keys plus pre-formatted params: the client renders the sentence.

### 2.5 Approvals (Phase 3)
| Method & path | Request → Response |
|---|---|
| `GET /…/approvals?status=pending&action=` | `{items: ApprovalSummary[], next_cursor}` (`approvals.view`). Expires due approvals first, so a stale `pending` is never shown. `ApprovalSummary` has the same fields as the detail below |
| `GET /…/approvals/{id}` | `{id, kind, action, status, summary, payload_hash, subject: {type, id, version, status, link: {target, id}}, expires_at, execute_before, required_permission, can_decide, is_simulated, created_at, decided_at, cancel_reason}`. `can_decide` is true for holders of `required_permission` and, for a `confirmation`, for its requester |
| `POST /…/approvals/{id}/decision` | `{decision: "approve"|"reject", payload_hash (64 hex), note?}` → the updated approval (its `subject.status` shows the outcome). Any member reaches the route; permission is per approval (403 otherwise). 409 codes `APPROVAL_ALREADY_DECIDED`, `APPROVAL_EXPIRED` (also for an approval that expired earlier), `APPROVAL_STALE` (hash or subject version differs). No other word decides anything: `ok`, `evet`, `tamam` are 422. The subject's callback runs in the same transaction; if it fails, nothing is saved |

### 2.6 Inbox (Phase 4)
| Method & path | Request → Response |
|---|---|
| `GET /…/conversations?attention=needs_approval|needs_human|failed|any&cursor=` | `[{id, customer_label, last_message_preview, last_message_at, attention, handling_mode, window_ends_at, is_simulated}]`. `customer_label` is the handle if known, else "Müşteri #4821". |
| `GET /…/conversations/{id}` | `{conversation, messages: [...], open_draft: ReplyDraft|null, recent_drafts: [...]}` |
| `POST /…/conversations/{id}/takeover` / `release` | |
| `POST /…/conversations/{id}/suggest-reply` | enqueue `draft_reply` on demand (202) |
| `POST /…/conversations/{id}/replies` | `{text, client_request_id, from_draft_id?}` → owner reply draft (queued) + claim warnings |
| `PATCH /…/reply-drafts/{id}` | `{text, expected_version}` → re-validated draft (new approval if needed) |
| `POST /…/reply-drafts/{id}/cancel` | queued → cancelled |

`ReplyDraft = {id, status, source, language, intent, text, suggestion_text, rendered_facts: [{fact_id, key, label, display, version, span:[start,end]}], validation: {passed, issues: [{code, span, text}]}, decision, decision_reasons[], approval_id, version, failure_code, is_simulated}`

### 2.7 Content and media (Phase 5)
| Method & path | Request → Response |
|---|---|
| `POST /…/media` | multipart `file` → `MediaAsset {id, status, width, height, mime_type, rejection_code}` |
| `GET /…/media/{id}/content` | authenticated binary stream (never a bucket URL) |
| `GET /…/content-items?status=&cursor=` | list |
| `POST /…/content-items` | `{content_type, title, caption?, overlay_text_suggestions?, media_asset_id?}` → draft |
| `POST /…/content-items/generate` | `{content_type, objective, notes?, client_request_id}` → 202 draft (status `draft`, `generation: running`) |
| `GET /…/content-items/{id}` | `{…, version, status, validation, schedule_local, approval, operation: {status, attempts, next_attempt_at, last_error_code}, is_simulated}` |
| `PATCH /…/content-items/{id}` | payload edits with `expected_version` |
| `POST /…/content-items/{id}/validate` | dry-run validation report |
| `POST /…/content-items/{id}/submit` | `{schedule: {local_date, local_time} | "now", self_approve, expected_version}` → item (`scheduled` or `pending_approval`); 422 `CONTENT_VALIDATION_FAILED` |
| `POST /…/content-items/{id}/cancel` | |
| `POST /…/content-items/{id}/reapprove` | for `on_hold`: new approval for the same version and a future schedule |

### 2.8 Reports, activity, notifications, health (Phase 6; notifications basic Phase 3)
| Method & path | Notes |
|---|---|
| `GET /…/reports/daily?date=YYYY-MM-DD` | computed or stored report with `metrics`, `summary` (localised), links |
| `POST /…/reports/daily/generate` | `{date}` regenerate |
| `GET /…/activity?type=&cursor=` | audit feed rendered for owners |
| `GET /…/notifications?unread=true` | `{items: [{id, type, severity, params, subject_type, subject_id, is_simulated, read_at, created_at}], unread_count, next_cursor}`: the caller's own notifications only |
| `POST /…/notifications/{id}/read` / `POST /…/notifications/read-all` | read → the notification (someone else's → 404); read-all → 204 |
| `GET /…/system-health` | accounts, failed operations (24 h), dead jobs, signature failures, LLM failure rate (owner/manager) |
| `GET /…/operations/{id}` | operation detail for failure explanations |

### 2.9 Integrations (mock Phase 4; Meta Phase 7)
| Method & path | Notes |
|---|---|
| `GET /…/social-accounts` | `[{id, platform, provider_kind, username, status, capabilities, connection_expires_at, last_error_code, is_simulated}]` (no token fields; the expiry is named `connection_expires_at` so the response-schema secret scan stays strict) |
| `POST /…/social-accounts/mock` | connect a simulated account (only if `mock` is enabled and allowed for the workspace) |
| `POST /…/social-accounts/instagram/connect` | → `{authorize_url}` (Phase 7) |
| `GET /oauth/instagram/callback` | OAuth redirect target (Phase 7) |
| `POST /…/social-accounts/{id}/disconnect` | |
| `GET /webhooks/instagram` | Meta verification handshake |
| `POST /webhooks/instagram` | signed Meta webhooks (Phase 7) |
| `POST /webhooks/instagram/mock` | signed simulated webhooks (Phase 4; mounted only when `mock` is enabled) |
| `POST /webhooks/meta/deauthorize`, `POST /webhooks/meta/data-deletion` | Phase 8 |
| `GET /api/v1/data-deletion-status/{code}` | public status page data (Phase 8) |
| `POST /webhooks/telegram` | Phase 9 |
| `POST /…/channel-links/code` | one-time linking code (Phase 9) |

### 2.10 Dev and demo (mounted only when `DEMO_TOOLS_ENABLED=true`; [INV-20](../invariants.md))
| Method & path | Notes |
|---|---|
| `POST /api/v1/dev/workspaces/{ws}/simulate/customer-message` | `{customer_alias, text}` or `{script_id}` |
| `POST /api/v1/dev/workspaces/{ws}/simulate/owner-native-reply` | `{conversation_id, text}` |
| `GET/POST/DELETE /api/v1/dev/workspaces/{ws}/failure-rules` | manage `sim_failure_rules` |
| `POST /api/v1/dev/jobs/run-due` | run due jobs now (uses the system clock) |
| `GET /api/v1/dev/jobs?status=` | inspect jobs |
| `POST /api/v1/dev/workspaces/{ws}/reset` | reset a demo workspace (`is_demo` only) |
| `GET /api/v1/dev/scripts` | scripted customer messages |

## 3. OpenAPI and client generation
- `GET /openapi.json` is served in development and test. The backend command `uv run python -m app.cli export-openapi -o ../frontend/openapi.json` exports it (deterministic, UTF-8, LF; `-o` is used instead of a shell redirect because Windows PowerShell 5.1 redirects write UTF-16; without `-o` the JSON goes to stdout), and `npm run gen:api` produces `src/api/schema.d.ts`.
- CI regenerates both and fails if the committed files differ.
