# Feature Phase 5, Session 01: WhatsApp policy, ADR, client and linking (F-06, part 1)

**Status:** Done offline (backend, frontend, docs). Everything live (a real number, the webhook callback, a real message) is **pending**.
**Baseline:** `1a58d41` (detached worktree). **Migration head:** `0070` (`down_revision = "0061"`; the orchestrator re-chains tracks at merge). Nothing committed.
**Trigger:** OQ-01 is treated as answered by the owner's request of 2026-11-17/18 to implement all Feature Phase 5 sessions. `mvp-scope.md` says so and also says that **trigger evidence (pilot owners will not use Telegram or push) is not yet recorded**. No pilot feedback was invented.

## What was delivered

- **Policy reading and decision.** `docs/research/platform-capabilities.md` §2 updated and a new §2.1 added: Meta Terms for the WhatsApp Business Platform section 4.7 "AI Providers" (page dated 2026-09-23), the Business Messaging Policy (dated 2026-09-23), the Cloud API facts the client uses (send, template, interactive reply buttons, webhook GET handshake, `X-Hub-Signature-256`, retries, envelope, pricing object), all with URLs and the access date 2026-11-18. **ADR-027** (`docs/architecture/decisions/ADR-027-whatsapp-owner-channel-scope.md`): notifications, fixed replies and buttons only; no free-text commands, and why (policy, safety, cost, scope). ADR index and an ADR-012 note updated.
- **Correction to an earlier claim.** The old §2 said service messages are free. Since 2026-10-01 they are charged after 1,000 per number per month, and utility templates inside an open window are charged too.
- **Client** `backend/app/integrations/channels/whatsapp/client.py`: `WhatsAppClient` with `send_template`, `send_interactive_buttons` (local validation of the documented limits before any HTTP call: 1 to 3 buttons, title at most 20, id at most 256, unique, body at most 1024, footer at most 60) and `send_text`; `httpx.MockTransport` injection; no automatic retry; `WhatsAppApiError` keeps Meta's raw `code` and never assumes its meaning; 5xx and 429 are `retryable`; a transport failure or a 2xx without a message id is `ambiguous=True` (never auto-resent); the access token is redacted from every error text.
- **Webhook** `whatsapp/webhook_format.py` (pure): `sign`/`verify_signature` (raw bytes, constant time), `verify_handshake`, and `parse_webhook` (text, button reply, status with pricing, other; messages without `from` dropped and counted; only the configured `phone_number_id` accepted). Router `api/v1/whatsapp_webhook_router.py` at `/api/v1/webhooks/whatsapp` (and the unprefixed alias like Telegram): GET handshake (403 on any mismatch or when unconfigured), POST verifies the signature **before** parsing JSON (401), 400 on invalid signed JSON, 200 for anything validly signed, 500 only when processing raised (Meta retries; dedup makes that safe). CSRF-exempt like the Telegram path.
- **Linking** through the existing one-time-code flow. `channel="whatsapp"` accepted by `POST /workspaces/{id}/channels/link-code`; the response carries `whatsapp_number` and a `https://wa.me/<digits>?text=<code>` deep link; refused with `409 CONFLICT_STATE` (`reason=whatsapp_not_configured`) when the server has no credentials. The owner sends the code (bare, or `LINK CODE`) to the business number; `dispatcher.process_webhook` redeems it with `ChannelLinkService.redeem_link_code` (`channel_user_id` and `channel_chat_id` are the sender's `wa_id`). Replies are fixed TR/EN strings, queued and sent **after** the commit (no HTTP in a transaction). A linked owner's other text gets only the fixed "open the app" text; an unknown sender's text gets nothing. **No owner text reaches the command system, the agent or any LLM** (asserted by a test that makes those entry points raise). Audit metadata for WhatsApp links omits the number (the audit log is append-only, so a phone number there could not be erased); the number lives only in `channel_links`.
- **Dedup** table `whatsapp_webhook_events` (global ingress ledger like `telegram_updates`): atomic `INSERT ... ON CONFLICT DO NOTHING`; sender stored only as a SHA-256 hash. A status event's key is `<wamid>:<status>`, because `sent`, `delivered` and `read` share one wamid and Session 02 needs each (cost metadata). A processing failure rolls the row back so Meta's retry is processed.
- **Settings** (all optional, WhatsApp is off without them): `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN` (secrets, in the redaction set), `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_DISPLAY_PHONE_NUMBER` (digits only, validated), `WHATSAPP_API_VERSION` (default `v27.0`), `WHATSAPP_API_BASE_URL`. `Settings.whatsapp_configured`. Production refuses a partial set, naming the missing variable only. Documented in `.env.example`, `environment-variables.md`, `local-development.md`.
- **Migration `0070`** (`20261118_0070_whatsapp_owner_channel.py`): `whatsapp` added to the channel CHECK constraints of `channel_links`, `channel_link_codes`, `notification_deliveries` (approved), `approvals.decision_channel`, `owner_commands.channel` and `agent_owner_tasks.source_channel` (models and constants kept in sync), plus the `whatsapp_webhook_events` table with the same runtime-role grants as `telegram_updates`. Downgrade deletes only link, link-code and delivery rows of the removed channel; it never deletes approvals, commands or owner tasks (the constraint recreation fails loudly if one exists).
- **Import-linter.** Contract `whatsapp-registry-only` (core, identity, notifications, approvals, operations, inbox, content, commands, api, memory, agent and the other channel adapters never import the adapter; the registry imports it lazily and the webhook router has three named exceptions) and `whatsapp-no-commands-or-ai` (the adapter imports neither commands, AI, agent, the LLM integration nor Instagram). Verified to bite: a temporary `app.identity.service -> ...whatsapp.client` import turned the run into "25 kept, 1 broken"; reverted.
- **Minimal UI** (`frontend/src/features/settings/Channels.tsx`, `hooks.ts`, TR and EN strings): a WhatsApp block under the Telegram one with status badge, "Connect WhatsApp" (shows the code, a countdown and the "Open in WhatsApp" `wa.me` link in the existing modal) and a disconnect confirmation. The block is shown only when the server reports WhatsApp as available (new `GET /workspaces/{id}/channels/availability` returning `{"whatsapp": bool}`, no secrets or numbers) or when a WhatsApp link already exists. Telegram behaviour is unchanged.
- **Contract docs:** `data-model.md` (channel columns and the new table), `integrations.md` (WhatsApp subsection), `mvp-scope.md` (F-06 row; Deferred row marked moved), `openapi.json` and `schema.d.ts` patched by hand (the exporter was not run).

## Contracts

| Item | Value |
|---|---|
| Webhook | `GET/POST /api/v1/webhooks/whatsapp` (alias `/webhooks/whatsapp`); header `X-Hub-Signature-256: sha256=<hmac-sha256 of raw body with the app secret>` |
| Endpoints added | `GET /workspaces/{id}/channels/availability` (`settings.view`); `link-code` accepts `channel: "telegram" \| "whatsapp"` |
| Table | `whatsapp_webhook_events(message_id pk, received_at, status, wa_id_hash, error)`; key `<wamid>` for messages, `<wamid>:<status>` for statuses |
| Link identity | `channel_links.channel_user_id = channel_chat_id = wa_id`; one active link per number |
| Registry | `get_channel("whatsapp")` returns a placeholder `WhatsAppChannel` (`deliver_notification` returns `failed` / `whatsapp_not_implemented`); raises `KeyError` when unconfigured |

## Tests and checks

New tests: `tests/unit/integrations/channels/test_whatsapp_client.py` (payloads, limits, errors, ambiguity, token redaction), `test_whatsapp_webhook_format.py` (signature, handshake, parser), `tests/contract/test_whatsapp_adapter.py` (handshake, signature, dedup, status repeats, full link flow, expired and wrong codes, free text never reaching commands or AI, ignored events, failing reply keeps the link, processing error allows retry, registry), `tests/isolation/test_whatsapp_link_isolation.py` (forced RLS, cross-workspace codes and links, supersede and unlink, global ledger grants, foreign link 404), plus additions to the settings, link-service, link-code API, RLS-list and CSRF-set tests.

| Check | Result |
|---|---|
| `uv run ruff check .`, `ruff format --check .` | pass (828 files formatted) |
| `uv run mypy app` | pass (439 files) |
| `uv run lint-imports` | 26 contracts kept, 0 broken; the new contract proven to bite with a temporary violation (25 kept, 1 broken), then reverted |
| `uv run pytest tests/unit tests/contract tests/security tests/isolation tests/integration/identity tests/integration/test_hardening_integration_regressions.py` | first run 2581 passed, 18 skipped, **5 failed**; see below, all 5 resolved or environment-caused; re-run of the affected files: 59 passed |
| Migration `0070` | `alembic downgrade 0061` then `upgrade head` on the test database succeeded; `compare_metadata` shows no check-constraint drift; the test session also upgrades from an empty schema |
| Frontend `npm.cmd run lint`, `typecheck`, `i18n:check` | pass (2773 keys) |
| Frontend `npm.cmd test` | 64 files, 916 tests passed |
| Frontend `npm.cmd run build` | pass |

The 5 first-run failures: (1) `test_security_audit` flagged `/api/v1/webhooks/whatsapp` as an unexpected CSRF exemption, because `scripts/security_scan.py` has its own copy of the expected set; **fixed** by adding the path there (the test then passes). (2) and (3) `test_members_and_invites::test_owner_creates_an_invite_with_a_one_time_link` and `test_invite_secrets::test_the_invite_token_is_never_logged_...` fail only because this worktree's `.env` sets `APP_BASE_URL` to a tunnel address; they pass with `APP_BASE_URL=http://localhost:8000` (Codex also reproduced the first on an unmodified HEAD copy). (4) and (5) `test_phase6_isolation::test_the_dev_job_listing...` and `test_publishing_isolation::test_the_simulator_listing...` get 404 because the worktree `.env` has `DEMO_TOOLS_ENABLED=false`; they pass with `DEMO_TOOLS_ENABLED=true`. None touches WhatsApp code. The rest of the backend suite (integration directories other than identity, e2e, browser) was not run; the full suite takes over an hour.

## Deviations and limitations

- **Terms text was read in Turkish through a page-to-text tool**, so section 4.7 is paraphrased, not quoted in English. Re-read it and get counsel's view before the first paying WhatsApp owner (recorded in §2.1).
- **Error JSON shape, the "outside the 24-hour window" error code and rate limits were not on the pages read.** The client keeps Meta's raw code and does not interpret it. Session 02 must handle the window by Clock arithmetic and treat an unexpected rejection as failed, not retry blindly.
- **BSUID-only senders cannot be linked** (no `from` number in the payload); they are dropped and counted.
- **The delivery channel is a placeholder.** Nothing creates `whatsapp` delivery rows yet. Notifications and the daily summary are Session 02; approval buttons are Session 03 (button replies and statuses are parsed and ignored).
- The Settings UI polls nothing: after the owner sends the code, the new link shows on the next refetch (as Telegram).
- A WhatsApp number can have one active link, and linking it to another workspace supersedes the first, as on Telegram.
- Four existing tests depend on the worktree `.env` (`APP_BASE_URL`, `DEMO_TOOLS_ENABLED`), see above; they are unrelated to this session.
- `scripts/security_scan.py` keeps its own copy of the CSRF-exempt path set; any future exempt path must be added there as well as in `deps.py` and `test_api_security.py`.

## Pending live (do not claim)

A verified Meta business number and app, the real webhook subscription and callback URL, a real link-code round trip, real template approval (Session 02), and the English re-read of Terms section 4.7 with counsel. No live Meta or WhatsApp call was made by any test or by this session.

## Questions

- Does the owner want the 1,000-free-service-message tier and Türkiye price points checked on the real 2026-10-01 rate card before Session 02 sets cost metadata?
- Should the Settings UI also show the business number when the code modal is closed (today only inside the modal)?
