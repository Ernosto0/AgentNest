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
| `CONTENT_VALIDATION_FAILED` | 422 | — | Content cannot be submitted / fix the listed items (§4.2). The problem document's top-level `errors` lists them (`{code, field, params, message}`) and `params.warnings` the non-blocking ones |
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

Since P5-03b `app/core/errors.py` also holds the codes a publish can fail with or a command can end in, all with tr and en texts and none of them an HTTP error: `MEDIA_REJECTED`, `PUBLISH_DEADLINE_PASSED`, `PUBLISH_QUOTA_EXHAUSTED`, `PROVIDER_UNAVAILABLE`, `PROVIDER_RATE_LIMITED`, `PROVIDER_REJECTED`, `CAPABILITY_MISSING`, `ACCOUNT_NEEDS_REAUTH`, `OUTCOME_UNKNOWN`, `OUTCOME_UNCONFIRMED`, `REFERENCE_NOT_FOUND` (recorded as a command's `error_code`). `query.explain_failure` explains a failed or retrying item's `last_error_code` from `errors.<CODE>.what` / `.next`; a held item's `hold_reason` (`FACT_CHANGED`, `ACCOUNT_UNAVAILABLE`) from `content.hold.<REASON>.what` / `.next`; anything else from `content.failure.unknown.what` / `.next`.

### 4.1 Reason codes
Reason codes are not errors. They explain *why* something was decided or changed, and appear as chips and explanations in the UI. They live in the same module with i18n keys `reasons.<CODE>`.

| Group | Codes |
|---|---|
| Reply policy ([workflows.md §C.1](workflows.md)) | `ACCOUNT_NOT_CONNECTED`, `CAPABILITY_MISSING`, `MESSAGING_WINDOW_CLOSED`, `HUMAN_TAKEOVER`, `LANGUAGE_UNSUPPORTED`, `INTENT_COMPLAINT`, `INTENT_REFUND_REQUEST`, `INTENT_DISCOUNT_REQUEST`, `INTENT_SENSITIVE`, `INTENT_UNSUPPORTED`, `FLAG_COMPLAINT`, `FLAG_REFUND`, `FLAG_DISCOUNT`, `FLAG_LEGAL`, `FLAG_HEALTH_SAFETY`, `FLAG_ABUSIVE`, `FLAG_PERSONAL_DATA`, `ESCALATION_KEYWORD`, `MODEL_REQUESTED_HUMAN`, `FACT_NOT_USABLE`, `GROUNDING_FAILED`, `LLM_UNAVAILABLE`, `LLM_BUDGET_EXCEEDED`, `LLM_OUTPUT_INVALID`, `ATTACHMENT_ONLY`, `INJECTION_SUSPECTED`, `AUTOMATION_OFF`, `POLICY_REQUIRES_APPROVAL`, `READINESS_NOT_READY`, `AUTO_RATE_GUARD`, `CONTAINS_<CLASS>` (`PRICING`, `HOURS`, `LOCATION_CONTACT`, `SERVICES`, `BOOKING`, `PROMOTIONS`, `GENERAL_FAQ`), `POLICY_AUTO` |
| Content hold (`content_items.hold_reason`) | `FACT_CHANGED`, `ACCOUNT_UNAVAILABLE`, `APPROVAL_EXPIRED` |
| Approval cancellation (`approvals.cancel_reason`) | `SUBJECT_EDITED`, `SUPERSEDED`, `FACT_CHANGED`, `WITHDRAWN`, `SUBJECT_CANCELLED` |
| Draft supersession | `NEW_INBOUND`, `OWNER_REPLIED_NATIVELY`, `OWNER_REPLIED`, `FACT_CHANGED`, `REGENERATED` |
| Inbound event ignore (`inbound_events.ignore_reason`) | `UNKNOWN_ACCOUNT`, `ACCOUNT_DISCONNECTED`, `UNSUPPORTED_EVENT` |

### 4.2 Content submission item codes (G17)
Item codes are not error codes: they are the entries of `errors` (blocking) and `warnings` in a `CONTENT_VALIDATION_FAILED` response, in the dry run `POST /content-items/{id}/validate` and in a submitted item's `validation.warnings`. Each has a text in both languages under `content.issue.<CODE>` (a test enforces it). The rules are in [workflows.md §E step 4.1](workflows.md); `content/validation.py` is the single source.

| Code | Kind | `field` | Params | Meaning |
|---|---|---|---|---|
| `CONTENT_MEDIA_REQUIRED` | error | `media_asset_id` | | No image attached |
| `MEDIA_NOT_READY` | error | `media_asset_id` | `status` | The attached asset is not `ready` |
| `CAPTION_REQUIRED` | error | `caption` | | A feed post needs a caption |
| `CAPTION_TOO_LONG` | error | `caption` | `length`, `max` (2200) | |
| `CAPTION_NOT_ALLOWED` | error | `caption` | | A story is published without a caption |
| `ASPECT_RATIO_OUT_OF_RANGE` | error | `media_asset_id` | `width`, `height` | Feed images must be 4:5 to 1.91:1 |
| `CLAIM_VALIDATION_FAILED` | error | `null` | `issues[]` | The claim validator's issues over the caption **and** the overlay suggestions: `{code, field, span, text, matches_verified, fact_key}` |
| `SCHEDULE_IN_PAST` | error | `schedule` | | Earlier than now - 1 min |
| `SCHEDULE_TOO_FAR` | error | `schedule` | | Later than now + 60 days |
| `SCHEDULE_TIME_NONEXISTENT` | error | `schedule` | `local_date`, `local_time`, `timezone` | The local time falls in a DST gap (G13) |
| `SCHEDULE_TOO_SOON_FOR_APPROVAL` | error | `schedule` | `minutes` (15) | The item will wait for an approver (staff, or no `self_approve`) and is less than 15 minutes ahead; "now" is impossible for staff |
| `ACCOUNT_NOT_CONNECTED` | error | `social_account_id` | | No active account, or it is not `connected` |
| `CAPABILITY_MISSING` | error | `social_account_id` | `capability` | The account lacks `publish_feed_image` / `publish_story_image` |
| `PUBLISH_QUOTA_FORECAST_EXCEEDED` | error | `scheduled_at` | | More than `PUBLISH_DAILY_LIMIT` posts in a rolling 24 h window around the time |
| `STORY_ASPECT_NOT_9_16` | warning | `media_asset_id` | `width`, `height` | A story image far from 9:16 may be cropped |
| `OVERLAY_TOO_LONG` | warning | `overlay_text_suggestions.{i}` | | More than 3 lines or a line over 40 characters |

A claim issue's own `code` is the validator's (`MONEY`, `PERCENT`, `TIME`, ...) plus `PLACEHOLDER_UNRENDERED` (a `{{fact:key}}` left in the stored text, which would be published literally) and `CLAIM_UNBACKED` (a commercial claim the model declared that no rendered fact backs). `fact_key` is the verified fact whose current display the value whole-token matches (such an issue has `matches_verified` and does not block), or the key a placeholder names.

### 4.3 Content notification kinds (G14)
Defined in `app/content/notifications.py`; recipients are every member who holds `content.approve` **including the person who caused the event**, plus the item's author. Params carry ids, the internal title, the version and a reason code, never the caption. One notification per recipient and event (`dedup_key = {kind}:{content_id}:v{version}`) until it is read; `is_simulated` follows the item.

| Kind | Severity | Produced when | `params.reason` |
|---|---|---|---|
| `content.on_hold` | attention | A referenced fact changed, or the account was unavailable at the due time | `FACT_CHANGED`, `ACCOUNT_UNAVAILABLE` |
| `content.published` | info | The publish succeeded | |
| `content.failed` | attention | The publish failed for good | the error code (`MEDIA_REJECTED`, `PUBLISH_DEADLINE_PASSED`, ...) |

The kinds exist from P5-04. The publish executor (P5-06) produces `content.published`, `content.failed` and `content.on_hold` (`ACCOUNT_UNAVAILABLE`: an account that is not usable at the due time, or an auth error during the attempt); the impact handlers (P5-07) produce `content.on_hold` with reason `FACT_CHANGED` for each `scheduled` / `retry_scheduled` item a fact change holds, to every `content.approve` holder including the person who changed the fact (the fact notification `knowledge.fact_changed` skips them). Items that go back from `pending_approval` to `draft` are not announced; they are counted in the `knowledge.fact_changed` impact (`by_referrer.content_item`: `on_hold`, `returned_to_draft`, `marked_stale`). Audit entries come from the content transitions (`content.publishing`, `content.published`, `content.failed`, `content.on_hold`, `content.retry_scheduled`) plus `operation.outcome_unknown` and `operation.reconciled`. An approval that expires is announced by the approvals service (`approval.expired`) to the requester.

### 4.4 Notification catalog (H8)
`app/notifications/catalog.py` is the single source: `notify` and `notify_permission_holders` raise `ValueError` for a type that is not listed, and for a severity that differs from the one listed. `uv run python -m app.notifications.catalog` writes `frontend/src/features/notifications/catalog.json`; a backend test fails when that file is out of date and a Vitest test fails when `describe.ts` has no text for a listed type. `params` carry ids and codes, never message or caption text. An unread notification with the same `dedup_key` for the same recipient is never created twice. `is_simulated` follows the subject. The notification centre (`more/notifications`) shows every type with a severity icon **and** the severity word, and a link to the subject.

| Type | Severity | Recipients | `dedup_key` | Producer |
|---|---|---|---|---|
| `approval.requested` | attention | holders of the approval's required permission (authorization approvals only) | `approval:{approval_id}` | `approvals.service.request` |
| `approval.expired` | info | the user who requested it | `approval-expired:{approval_id}` | `approvals.service.expire_one` |
| `content.on_hold` | attention | `content.approve` + the item's author (see 4.3) | `content.on_hold:{content_id}:v{version}` | publish executor, content impact handler |
| `content.published` | info | `content.approve` + author | `content.published:{content_id}:v{version}` | publish executor |
| `content.failed` | attention | `content.approve` + author | `content.failed:{content_id}:v{version}` | publish executor |
| `conversation.needs_human` | attention | `reply.approve` | `needs-human:{conversation_id}` | inbound processing (takeover), reply workflow (escalation) |
| `reply.failed` | attention | `reply.approve` | `reply-failed:{draft_id}` | `operations.resolution.notify_reply_failed` |
| `knowledge.fact_changed` | info | `knowledge.verify`, not the person who changed it | `fact:{fact_id}:v{version}` | `knowledge.impact` |
| `account.needs_reauth` | critical | `integrations.manage` | `account:{account_id}:needs_reauth` | `operations.health.handle_auth_error` |
| `account.permission_missing` | attention | `integrations.manage` | `account:{account_id}:permission_missing:{capability}` | `operations.health.handle_permission_error` (send and publish) |
| `report.daily_ready` | info | `reports.view` | `report:{local_date}` | `reporting.service.generate_daily_report` (the scheduled run only) |

Types that later Phase 6 sessions add to the catalog together with their producer: `account.degraded` (attention, `integrations.manage`, `account:{id}:degraded`) and `account.recovered` (info, `account:{id}:connected`) in the circuit work; `member.joined` (info, owners) with member invites; `knowledge.promotion_expired` (attention, `knowledge.verify`) with retention. The account dedup key follows the form `account:{id}:{status}`; the earlier `account-reauth:{id}` was renamed (unread notifications under the old key are not migrated; the next failure creates a new one).

## 5. Audit action catalog

Written in the same transaction as the change ([INV-12](../invariants.md)). `metadata` holds IDs, codes and, for facts, formatted old and new values (`old_display`, `new_display`; also `old_window`/`new_window` for validity changes, `key`, `version`, `source_type`, and `source_ref` — the command or candidate ID that caused the change); **never** message text or tokens. `audit.record` rejects metadata keys such as `text`, `message` and `body`. Every fact change writes exactly one `fact.*` entry and one `fact_versions` row; accepting a candidate additionally writes `fact_candidate.accepted`. `policy.reviewed` is written once, when the owner confirms the review (`POST /automation-policies/review`); saving the policies writes only `policy.updated`.

| Area | Actions |
|---|---|
| Auth & members | `auth.login`, `auth.logout`, `auth.login_failed` (system-level, no workspace), `workspace.created`, `workspace.updated`, `member.invited`, `member.joined`, `member.role_changed`, `member.removed` |
| Knowledge | `fact.created`, `fact.updated`, `fact.verified`, `fact.archived`, `fact.restored`, `fact_candidate.created`, `fact_candidate.accepted`, `fact_candidate.rejected`, `knowledge.extraction_requested` (character count and an injection flag, never the text), `approved_answer.created/updated/archived`, `policy.updated`, `policy.reviewed` |
| Commands | `command.received`, `command.interpreted`, `command.executed`, `command.failed`, `command.cancelled`, `command.expired` |
| Approvals | `approval.requested`, `approval.approved`, `approval.granted` (a decision by someone other than the requester that is not a self-approval), `approval.rejected`, `approval.expired`, `approval.cancelled` |
| Inbox | `message.received`, `message.native_reply_recorded`, `reply_draft.created`, `reply_draft.edited`, `reply_draft.<status>` (one entry per draft status change: `pending_approval`, `needs_human`, `queued`, `sending`, `outcome_unknown`, `sent`, `failed`, `rejected`, `expired`, `superseded`, `cancelled`, `blocked`), `reply.sent`, `reply.failed`, `reply.outcome_unknown`, `reply.outcome_unconfirmed`, `reply.late_confirmation`, `conversation.takeover`, `conversation.release` |
| Content | `content.created`, `content.generated`, `content.updated`, `content.submitted`, `content.scheduled`, `content.on_hold`, `content.cancelled`, `content.rejected`, `content.publishing`, `content.retry_scheduled`, `content.published`, `content.failed`, `media.uploaded`, `media.rejected` |
| Operations & accounts | `operation.started`, `operation.succeeded`, `operation.failed`, `operation.outcome_unknown`, `operation.reconciled`, `social_account.connected`, `social_account.degraded`, `social_account.needs_reauth`, `social_account.disconnected`, `account.reconnected`, `social_account.token_refreshed` (Phase 7) |
| System | `webhook.signature_invalid`, `report.generated`, `retention.cleanup_ran`, `demo.reset`, `demo.failure_rule_set` |

**Account audit names.** Every status change of a social account is audited as `social_account.<new status>` (entity type `social_account`; the previous status is in the metadata), which is what the code does (`operations/accounts.transition_account`). The one exception is the reconnect of a simulated account, which has a name of its own, `account.reconnected` (Phase 5, passed as `audit_action`). Earlier drafts of these docs called the status changes `account.connected`, `account.disconnected` and `account.status_changed`; those names are not used.

`report.generated` is written with the workspace id (resource type `daily_report`; metadata `local_date`, `scheduled`, `definitions_version`, `is_partial`), by the scheduled run and by every on-demand regeneration, so it appears in the workspace's Activity feed (group *system*).

The **Activity** view renders entries with i18n templates (`activity.<action>` in `core/i18n/{tr,en}.json`, no parameters, so no text can leak into them), with actor labels and a simulated badge. It reads the workspace's `audit_logs` only (system-level rows have no workspace and never show).

- **Groups** (the `type` filter; the fixed map is `app/activity/groups.py`): `messages` (`message.*`, `conversation.*`), `replies` (`reply_draft.*`, `reply.*`), `approvals`, `content` (`content.*`, `media.*`), `knowledge` (`fact.*`, `fact_candidate.*`, `approved_answer.*`, `knowledge.*`, `policy.*`), `commands`, `accounts` (`social_account.*`, `account.reconnected`), `members` (`member.*`) and `system` (`auth.*`, `workspace.*`, `operation.*`, `webhook.*`, `report.*`, `retention.*`, `demo.*`, and any action the map does not know yet).
- **Actor labels:** a user is shown by display name, or "Eski üye" / "Former member" when they are no longer a member of the workspace; `system` is "Sistem", `agent` is "Yapay zekâ", `provider` is "Instagram".
- **Resource labels are resolved at read time**, in batches and scoped to the workspace, from the record itself: a customer by handle (never message text), a content item by title, a fact by its label, an approved answer by title, an approval by its action, an account by username. A record that no longer exists reads "Silinmiş kayıt" and has no link. Audit metadata never holds text, so nothing is stored for labels.
- **Coverage rule:** every action in the table above and every action the code writes has a group and `activity.<action>` texts in both languages; a unit test fails otherwise. A new audit action therefore needs a catalog row, an entry in `groups.py` and two texts in the same change.
- **Actions found in the code and added to the catalog in Phase 6:** `message.native_reply_recorded` (the catalog said `message.native_reply_detected`), `conversation.release` (it said `conversation.released`), `reply_draft.<status>`, `reply.outcome_unconfirmed`, `reply.late_confirmation`, `approval.granted`. `reply_draft.superseded` is now one of the `reply_draft.<status>` entries.

## 6. System health panel (owner/manager, Phase 6)

Computed from tables (no metrics backend):
- Accounts: status, last error, token expiry, and `degraded_until` for a `degraded` account.
- Operations last 24 h: counts by type and status; latest failures with codes.
- Jobs: queued count, oldest queued age, dead jobs last 24 h.
- Webhooks: events received 24 h, ignored, failed (the workspace's own events), and signature failures 24 h. Signature failures are system-level audit rows with no workspace (a forged request cannot be attributed), so that one number is **system-wide** and is labelled so in the API and the screen.
- AI: agent runs 24 h by task and status, failure rate, tokens and estimated cost (configured price table), budget usage.

## 7. Development metrics vs production commitments

| Kind | Examples | Where | Status |
|---|---|---|---|
| **Development budgets** | API read p95 < 300 ms on seed data; webhook ack < 500 ms; fake-LLM command round trip < 3 s | Measured in tests and Playwright on a dev machine | Targets to keep the demo responsive. **Not SLAs.** |
| **Pilot measurements** | Draft acceptance rate, edit rate, time to first reply, publish success rate, duplicate effects (must be 0), grounding violations (must be 0) | Computed from tables ([vision.md §8](../product/vision.md)) | Baselines collected during pilots |
| **Commercial SLAs** | uptime, response time | — | **None promised** until monitoring and multi-instance deployment exist |

## 8. AI evaluation reporting
Eval reports (`backend/evals/reports/<date>-<task>-<provider>-<model>-<prompt_version>.{json,md}`) record dataset version, metrics per label, hard-assertion failures, tokens and cost. Process in [testing-strategy.md §6](../implementation/testing-strategy.md).
