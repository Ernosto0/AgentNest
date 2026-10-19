# Observability

**Purpose:** How we know what the system did and why: structured logs, correlation IDs, the error code catalog, the audit action catalog, user-visible status, system health and development metrics. Decision record: [ADR-018](decisions/ADR-018-observability-and-evaluation.md).

## 1. Identifiers

| ID | Created | Propagated to |
|---|---|---|
| `request_id` | per HTTP request (or taken from `X-Request-ID`) | logs, error responses |
| `correlation_id` | at the origin of a flow: webhook ingest, command submit, content generate/submit, scheduler tick | jobs, agent_runs, operations, approvals (via subject), audit_logs, inbound_events, notifications (params) |
| `job_id` | enqueue | logs |
| `operation_id` | operations ledger | logs, audit, UI detail |
| `agent_run_id` | AI runner | drafts, commands, content, audit |

**Trace a flow from the DB** (works after logs rotate):
```sql
SELECT occurred_at, action, resource_type, resource_id, metadata
FROM audit_logs WHERE correlation_id = :cid ORDER BY occurred_at;
-- plus jobs/operations/agent_runs WHERE correlation_id = :cid
```
The dev panel exposes "Trace" for any draft, content item or command. It shows the joined timeline.

## 2. Logs

- structlog. JSON in production, coloured console in development. One event per line.
- Standard fields: `ts`, `level`, `event`, `logger`, `env`, plus bound context IDs (§1), `workspace_id`, `user_id` (never email), `duration_ms` where relevant.
- **Never logged:** tokens, secrets, cookies, authorization headers, passwords, OAuth codes, message or caption text, pasted text, customer handles. (A redaction processor is a safety net, not the primary control.) The processor masks the value of any key containing `token` (but not the plural `tokens`, which is a usage counter), `secret`, `password`, `passwd`, `authorization`, `cookie` or `api_key`, and of the exact key `code` (so `error_code` stays readable); it recurses into dicts and lists, masks `Bearer …`/`Basic …` values, and leaves booleans and nulls alone (`cookie_secure=true` is a flag, not a secret).
- Logs are written to **stderr**.
- The request log line (`request`) carries `request_id`, `method`, `path` (without the query string), `status`, `duration_ms` and, when known, `user_id` and `workspace_id`.
- Levels: `INFO` for state transitions and external call outcomes; `WARNING` for retries, degraded accounts and validation failures of AI output; `ERROR` for dead jobs, unexpected exceptions and signature-failure bursts.
- Every external call logs: `provider`, `method`, `operation_id`, `outcome` (ok / error code), `duration_ms`, `http_status` (when meaningful).

## 3. User-visible status (owner-facing)

Rule: owners see **domain states and error codes rendered as plain language**, never stack traces or raw provider messages ([INV-18](../invariants.md)). Mapping of states to badges: [user-journeys.md §1](../product/user-journeys.md).

## 4. Error code catalog

Defined in `app/core/errors.py` (single source). Each code has: HTTP status (if API-facing), `retryable`, i18n keys `errors.<CODE>.what` and `errors.<CODE>.next` in tr and en. A lint test fails if a code lacks translations.

| Code | HTTP | Retryable | Meaning (what / next step for the user) |
|---|---|---|---|
| `AUTH_REQUIRED` | 401 | — | Not signed in / sign in |
| `INVALID_CREDENTIALS` | 401 | — | Email or password wrong / try again |
| `CSRF_FAILED` | 403 | — | Session check failed / reload the page |
| `FORBIDDEN` | 403 | — | Your role cannot do this / ask the owner |
| `NOT_FOUND` | 404 | — | Not found |
| `VALIDATION_FAILED` | 422 | — | Some fields are invalid / fix the highlighted fields |
| `VERSION_CONFLICT` / `FACT_VERSION_CONFLICT` | 409 | — | Someone changed this meanwhile / reload and retry |
| `CONFLICT_STATE` | 409 | — | This action is not possible in the current state |
| `APPROVAL_ALREADY_DECIDED` | 409 | — | Already approved or rejected |
| `APPROVAL_EXPIRED` | 409 | — | The approval expired / request a new draft or schedule |
| `APPROVAL_STALE` | 409 | — | Content changed after you opened it / review the new version |
| `FACT_NOT_USABLE` | — | — | Needed information is missing or unverified / verify it in Business knowledge |
| `FACT_CHANGED_MEANWHILE` | — | — | The fact changed before confirmation, so nothing was overwritten / check the current value and repeat the command. Recorded as the command's `error_code`; never an HTTP error, because the decision itself succeeded |
| `GROUNDING_FAILED` | — | — | The draft contained values not matching verified facts / edit or write the reply |
| `CONTENT_VALIDATION_FAILED` | 422 | — | Content cannot be submitted (list of issues) |
| `CONTENT_MEDIA_REQUIRED` | 422 | — | An image is required |
| `MEDIA_INVALID` | 422 | — | The file is not a supported image / upload a JPEG or PNG |
| `MEDIA_TOO_LARGE` | 413 | — | The file exceeds 8 MB |
| `MESSAGING_WINDOW_CLOSED` | — | no | Instagram allows replies only within 24 h / reply in the Instagram app |
| `ACCOUNT_NOT_CONNECTED` | — | no | No Instagram account connected / connect in Settings |
| `ACCOUNT_NEEDS_REAUTH` | — | no | Instagram connection must be renewed / press Reconnect |
| `ACCOUNT_MISMATCH` | 400 | — | A different Instagram account was authorised / sign in with the original account |
| `CAPABILITY_MISSING` | — | no | Permission for this action was not granted / reconnect and allow it |
| `PROVIDER_UNAVAILABLE` | — | yes | Instagram is not reachable / we will retry automatically |
| `PROVIDER_RATE_LIMITED` | — | yes | Instagram asked us to slow down / we will retry automatically |
| `PROVIDER_REJECTED` | — | no | Instagram rejected the request (detail) |
| `MEDIA_REJECTED` | — | no | Instagram could not process the image / try another image |
| `PUBLISH_DEADLINE_PASSED` | — | no | It could not be published in time / reschedule |
| `PUBLISH_QUOTA_EXHAUSTED` | — | yes | Daily publishing limit reached / it will retry later |
| `OUTCOME_UNKNOWN` | — | reconcile | Checking whether it was sent or published |
| `OUTCOME_UNCONFIRMED` | — | no | We could not confirm sending / check Instagram before resending |
| `LLM_UNAVAILABLE` | — | yes (job) | AI is temporarily unavailable / write the reply yourself or retry |
| `LLM_OUTPUT_INVALID` | — | no | The AI produced an unusable result / try rephrasing |
| `LLM_BUDGET_EXCEEDED` | — | no | Daily AI limit reached / continue manually |
| `LLM_REFUSED` | — | no | The AI declined this request / handle manually |
| `REFERENCE_NOT_FOUND` | — | — | Could not find the item you mentioned |
| `COMMAND_UNSUPPORTED` | — | — | This is not something I can do yet (examples) |
| `LANGUAGE_UNSUPPORTED` | — | — | Customer language not supported for drafts / reply manually |
| `INJECTION_SUSPECTED` | — | — | Message looks like it tries to manipulate the assistant / review carefully |
| `JOB_PAYLOAD_INVALID` | — | no | Internal error (dev) |
| `INTERNAL_ERROR` | 500 | — | Something went wrong / try again; reference `request_id` |

### 4.1 Reason codes
Reason codes are not errors. They explain *why* something was decided or changed, and appear as chips and explanations in the UI. They live in the same module with i18n keys `reasons.<CODE>`.

| Group | Codes |
|---|---|
| Reply policy ([workflows.md §C.1](workflows.md)) | `ACCOUNT_NOT_CONNECTED`, `CAPABILITY_MISSING`, `MESSAGING_WINDOW_CLOSED`, `HUMAN_TAKEOVER`, `LANGUAGE_UNSUPPORTED`, `INTENT_COMPLAINT`, `INTENT_REFUND_REQUEST`, `INTENT_DISCOUNT_REQUEST`, `INTENT_SENSITIVE`, `INTENT_UNSUPPORTED`, `FLAG_COMPLAINT`, `FLAG_REFUND`, `FLAG_DISCOUNT`, `FLAG_LEGAL`, `FLAG_HEALTH_SAFETY`, `FLAG_ABUSIVE`, `FLAG_PERSONAL_DATA`, `ESCALATION_KEYWORD`, `MODEL_REQUESTED_HUMAN`, `FACT_NOT_USABLE`, `GROUNDING_FAILED`, `LLM_UNAVAILABLE`, `LLM_BUDGET_EXCEEDED`, `LLM_OUTPUT_INVALID`, `ATTACHMENT_ONLY`, `INJECTION_SUSPECTED`, `AUTOMATION_OFF`, `POLICY_REQUIRES_APPROVAL`, `READINESS_NOT_READY`, `AUTO_RATE_GUARD`, `POLICY_AUTO` |
| Content hold (`content_items.hold_reason`) | `FACT_CHANGED`, `ACCOUNT_UNAVAILABLE`, `APPROVAL_EXPIRED` |
| Approval cancellation (`approvals.cancel_reason`) | `SUBJECT_EDITED`, `SUPERSEDED`, `FACT_CHANGED`, `WITHDRAWN`, `SUBJECT_CANCELLED` |
| Draft supersession | `NEW_INBOUND`, `OWNER_REPLIED_NATIVELY`, `OWNER_REPLIED`, `FACT_CHANGED`, `REGENERATED` |
| Inbound event ignore (`inbound_events.ignore_reason`) | `UNKNOWN_ACCOUNT`, `ACCOUNT_DISCONNECTED`, `UNSUPPORTED_EVENT` |

## 5. Audit action catalog

Written in the same transaction as the change ([INV-12](../invariants.md)). `metadata` holds IDs, codes and, for facts, formatted old and new values (`old_display`, `new_display`; also `old_window`/`new_window` for validity changes, `key`, `version`, `source_type`, and `source_ref` — the command or candidate ID that caused the change); **never** message text or tokens. `audit.record` rejects metadata keys such as `text`, `message` and `body`. Every fact change writes exactly one `fact.*` entry and one `fact_versions` row; accepting a candidate additionally writes `fact_candidate.accepted`. `policy.reviewed` is written when the owner marks the automation policy as reviewed.

| Area | Actions |
|---|---|
| Auth & members | `auth.login`, `auth.logout`, `auth.login_failed` (system-level, no workspace), `workspace.created`, `workspace.updated`, `member.invited`, `member.joined`, `member.role_changed`, `member.removed` |
| Knowledge | `fact.created`, `fact.updated`, `fact.verified`, `fact.archived`, `fact.restored`, `fact_candidate.created`, `fact_candidate.accepted`, `fact_candidate.rejected`, `knowledge.extraction_requested` (character count and an injection flag, never the text), `approved_answer.created/updated/archived`, `policy.updated`, `policy.reviewed` |
| Commands | `command.received`, `command.interpreted`, `command.executed`, `command.failed`, `command.cancelled`, `command.expired` |
| Approvals | `approval.requested`, `approval.approved`, `approval.rejected`, `approval.expired`, `approval.cancelled` |
| Inbox | `message.received`, `message.native_reply_detected`, `reply_draft.created`, `reply_draft.edited`, `reply_draft.superseded`, `reply.sent`, `reply.failed`, `reply.outcome_unknown`, `conversation.takeover`, `conversation.released` |
| Content | `content.created`, `content.generated`, `content.updated`, `content.submitted`, `content.scheduled`, `content.on_hold`, `content.cancelled`, `content.rejected`, `content.publishing`, `content.retry_scheduled`, `content.published`, `content.failed`, `media.uploaded`, `media.rejected` |
| Operations & accounts | `operation.started`, `operation.succeeded`, `operation.failed`, `operation.outcome_unknown`, `operation.reconciled`, `account.connected`, `account.reconnected`, `account.disconnected`, `account.status_changed`, `account.token_refreshed` |
| System | `webhook.signature_invalid`, `report.generated`, `retention.cleanup_ran`, `demo.reset`, `demo.failure_rule_set` |

The **Activity** view renders entries with i18n templates (`activity.<action>`), with actor labels ("Sistem", "Yapay zekâ taslağı", user display name) and a simulated badge.

## 6. System health panel (owner/manager, Phase 6)

Computed from tables (no metrics backend):
- Accounts: status, last error, token expiry.
- Operations last 24 h: counts by type and status; latest failures with codes.
- Jobs: queued count, oldest queued age, dead jobs last 24 h.
- Webhooks: events received 24 h, ignored, failed, signature failures 24 h.
- AI: agent runs 24 h by task and status, failure rate, tokens and estimated cost (configured price table), budget usage.

## 7. Development metrics vs production commitments

| Kind | Examples | Where | Status |
|---|---|---|---|
| **Development budgets** | API read p95 < 300 ms on seed data; webhook ack < 500 ms; fake-LLM command round trip < 3 s | Measured in tests and Playwright on a dev machine | Targets to keep the demo responsive. **Not SLAs.** |
| **Pilot measurements** | Draft acceptance rate, edit rate, time to first reply, publish success rate, duplicate effects (must be 0), grounding violations (must be 0) | Computed from tables ([vision.md §8](../product/vision.md)) | Baselines collected during pilots |
| **Commercial SLAs** | uptime, response time | — | **None promised** until monitoring and multi-instance deployment exist |

## 8. AI evaluation reporting
Eval reports (`backend/evals/reports/<date>-<task>-<provider>-<model>-<prompt_version>.{json,md}`) record dataset version, metrics per label, hard-assertion failures, tokens and cost. Process in [testing-strategy.md §6](../implementation/testing-strategy.md).
