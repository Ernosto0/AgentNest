# Feature Phase 5, Session 03: WhatsApp approval buttons and track close-out (F-06, part 3)

**Status:** Done offline (backend, docs). Everything live (a verified number, a real button tap, Meta's real behaviour for forwarded interactive messages) is **pending**.
**Baseline:** `1a58d41` plus Sessions 01 and 02's uncommitted work. **Migration head:** `0071` (no new migration: no schema change was needed). Nothing committed. No frontend change, so the frontend checks were not run and `openapi.json` is unchanged.

## What was delivered

- **Buttons out** (`backend/app/integrations/channels/whatsapp/approval_buttons.py`, called from `WhatsAppChannel.deliver_notification`). For `approval.requested` inside the 24-hour window the adapter mints two tokens with the existing `ActionTokenService.create_action_token` (approve and reject, bound to the recipient member, the approval, the decision and the approval's payload hash, expiring with the approval, stored as SHA-256 hashes) and sends one interactive reply-button message: titles `Onayla`/`Reddet` or `Approve`/`Reject`, button ids `act:<token>`. The id carries only the opaque token (no approval id, workspace id or decision). The body says **what is being approved** (revised after review: approval must be informed): for a reply draft the proposed reply text, for a content item the type, title, schedule and caption, for price cards, reschedules and pauses their label, price or time (the Telegram fields), plus a fixed kind label and the expiry in the workspace timezone. The long text (reply or caption) is clipped so the whole body is at most 1,000 characters (Meta allows 1,024), with an ellipsis and "(tam metin uygulamada)" / "(full text in the app)"; short fields are clipped to 80 characters and the expiry line is never cut. The approval binds to the full payload hash unchanged. The customer's inbound message and handle are never read or shown. Tokens are minted before the "sending" marker commit, so they exist before the message can. No new token scheme.
- **Outside the window.** The window is judged at send time as in Session 02. Outside it (or when the owner never wrote) the message is the existing `agentnest_approval_requested_v1` template, **without buttons and without minting a token**, and its text says to open the app. The template registry has no quick-reply button and none was added (reasons in ADR-027's Session 03 addendum). `delivery_metadata.approval_buttons` records `sent`, `not_sent_outside_window` or `approval_not_found`; `approval_id` is recorded; no token is ever stored in metadata, job payloads or logs.
- **An approval that is no longer pending when the job runs is not announced** (terminal `approval_not_pending`, nothing sent, no tokens).
- **Buttons in** (`approval_buttons.handle_button_reply`, called from `dispatcher.process_webhook` for `InboundButtonReply`). The sender is resolved through the channel link (`resolve_channel_user`: active link, active user, still a workspace member). An unlinked or revoked sender gets **no reply** and the dedup row stays `ignored`. For a linked sender the token is consumed with `channel="whatsapp"` (single-use, expiry, same member and workspace, approval still pending, all in one locked transaction), then `approvals.service.decide(channel="whatsapp")` runs with the token's payload hash, the same service as web and Telegram (so an edited subject is stale, a missing permission is refused, the subject callback runs once). The tap also extends the 24-hour window anchor. The answer is a fixed, localised session message sent after the commit (no HTTP in a transaction).
- **Replay and stale show the current state**, in a fixed sentence: approved, rejected, already approved, already rejected, expired, "changed or withdrawn, this button no longer applies", "not allowed", "not valid". The state is shown only if the tapper is the token's own member; a different linked member who taps a forwarded button gets only "not valid", and a foreign workspace's token is "not valid" too.
- **Free text never decides.** Only `interactive.button_reply` reaches this module. A text message that contains `act:<valid token>` or "approve" gets the Session 01 fixed "open the app" reply, and the tokens stay unused.
- **Phase 9 code touched** (`backend/app/approvals/action_tokens.py`): `consume_action_token` gained `channel: str = "telegram"` (it was hard-wired to Telegram) and a read-only `lookup_action_token` that returns the record without consuming it, used to describe a replay. Telegram behaviour and tests are unchanged.
- **Live probe harness** `backend/tests/contract/test_whatsapp_live.py` (marker `whatsapp_live`, registered in `pyproject.toml`): a session text ping and an interactive message with two **probe** button ids (`probe:approve`, `probe:reject`, which decide nothing). Skipped unless `WHATSAPP_LIVE_ACCESS_TOKEN`, `WHATSAPP_LIVE_PHONE_NUMBER_ID` and `WHATSAPP_LIVE_TO` are all set; it never reads the application's own `WHATSAPP_*` settings; probe failures cannot leak exception text. Offline safety tests in `tests/unit/integrations/channels/test_whatsapp_live_safety.py`.
- **Docs:** ADR-027 Session 03 addendum, `integrations.md` (Approval buttons), `platform-capabilities.md` §2.2 note, `mvp-scope.md` F-06 row, the Track A summary and the `roadmap.md` entry.

## Tests and checks

New: `tests/integration/notifications/test_whatsapp_approval_buttons.py` (38 cases), `tests/contract/test_whatsapp_live.py` (2, skipped), `tests/unit/integrations/channels/test_whatsapp_live_safety.py` (5).

| Item | Test |
|---|---|
| Buttons inside the window, summary fields shown, opaque ids, hashed bound tokens, no token in metadata or jobs | `test_inside_the_window_the_owner_gets_approve_and_reject_buttons`, `test_english_owner_gets_english_buttons` |
| Proposed reply shown, customer message never present; truncation with ellipsis and app pointer (hash unchanged); English note; content title and caption; long title and caption always fit 1,000 | `test_a_reply_approval_shows_the_proposed_reply_but_never_the_customer_message`, `test_a_long_reply_is_cut_with_an_ellipsis_and_a_pointer_to_the_app`, `test_the_english_cut_note_and_labels`, `test_a_content_approval_shows_the_post`, `test_a_secondary_field_is_clipped_and_the_body_always_fits` |
| Outside the window or never written: template, no buttons, no tokens | `test_outside_the_window_it_is_the_plain_template_without_buttons` (25 h, 23 h 58 min, never), `test_the_window_is_judged_at_send_time_not_at_notify_time` |
| Already decided before the job runs | `test_an_approval_decided_before_the_job_runs_is_not_announced` |
| Retry mints fresh single-use tokens | `test_a_retried_send_mints_fresh_single_use_tokens` |
| Approve and reject through the approval service, channel `whatsapp`, audit, window anchor, reply after commit | `test_approve_decides_once_through_the_approval_service`, `test_reject_decides_as_rejected`, `test_an_english_owner_gets_an_english_answer` |
| Replay, sibling button | `test_replay_shows_the_current_state_and_decides_nothing_twice` |
| Duplicate webhook (dedup) | `test_a_duplicate_webhook_delivery_is_processed_once` |
| Expiry (and the exact expiry instant) | `test_an_expired_button_is_refused_...`, `test_a_button_tapped_at_the_exact_expiry_instant_never_approves` |
| Forwarded button: other linked member, unlinked number, foreign workspace | `test_a_forwarded_button_tapped_by_another_linked_member_reveals_nothing`, `..._from_an_unlinked_number_gets_no_reply`, `test_a_token_of_another_workspace_is_refused` |
| Unlinked owner, revoked membership, lost permission | `test_an_unlinked_owner_cannot_use_a_button_sent_earlier`, `test_a_revoked_member_cannot_decide`, `test_a_member_who_lost_the_permission_is_refused` |
| Decided on the web, stale, withdrawn | `test_an_approval_decided_on_the_web_shows_its_current_state`, `test_a_stale_approval_is_not_approved`, `test_a_withdrawn_approval_shows_that_the_button_no_longer_applies` |
| Malformed or unknown ids | `test_malformed_or_unknown_button_ids_are_refused_without_effect` (7 ids) |
| Free text never decides; token never in logs | `test_free_text_never_decides_even_when_it_contains_a_valid_token`, `test_a_token_never_reaches_the_logs` |

| Check | Result |
|---|---|
| `uv run ruff check app tests evals migrations`, `ruff format --check app tests evals migrations` | pass (839 files formatted) |
| `uv run mypy app` | pass (444 files) |
| `uv run lint-imports` | 26 contracts kept, 0 broken (the adapter importing `app.approvals` is allowed by the WhatsApp contracts) |
| `uv run pytest tests/unit tests/contract tests/security tests/isolation tests/integration/notifications tests/integration/approvals tests/integration/identity tests/integration/test_hardening_integration_regressions.py` | 2865 passed, 20 skipped, **2 failed** (6 min 13 s; re-run after the informed-approval revision, the same two environmental failures; unit, contract, security, isolation, notifications, approvals and identity) |
| Frontend | not run (no frontend change) |

The 2 failures are environmental and unrelated to WhatsApp, both already recorded in Session 02's report: `test_deployment_workflow_and_rollback::test_cli_migration_status_head_only_and_check_config` fails only because the worktree `.env` sets `DEMO_TOOLS_ENABLED=true` (it passes with `DEMO_TOOLS_ENABLED=false`); `test_invite_secrets::test_the_invite_token_is_never_logged_...` fails in the long run but passes alone (2 passed), an ordering effect.

## Deviations and limitations

- **What the message shows** follows the Telegram fields except the account name (it would need an Instagram import that the WhatsApp import contract forbids) and the customer's message (ADR-027). For unknown approval kinds only a short allow-list of summary fields is shown. A long reply or caption is cut in the message; the owner opens the app for the full text.
- **No quick-reply button on the template** (outside the window the owner must open the app). A template `button` message type (a quick-reply tap) is not parsed.
- **Forwarded interactive messages:** whether the buttons stay tappable for a forward is not documented in the pages read; the design assumes they may and refuses every tap whose number is not the token's member.
- **A retried send mints a second pair of tokens**; the first pair, never delivered, expires with the approval and is unusable by anyone who has not seen it.
- **A failed decision consumes the token** (stale, forbidden): the same as Telegram. The owner decides in the app.
- **No deep link** to the approval in the message (links need a URL button or a variable in a template; left out again).
- **Quiet hours:** an approval request that is not critical and not expiring within 2 hours is held as `skipped_quiet_hours` (Session 02 policy), so no buttons are sent for it.
- Integration directories other than notifications, approvals and identity, e2e and browser tests were not run (the full suite takes over an hour).

## Pending live (do not claim)

A verified Meta number and app, the real webhook subscription, approved templates, a real interactive message with two buttons on a phone, a real tap arriving as `interactive.button_reply` with the id intact (token length 22 against the 256-character limit), the behaviour of forwarded buttons, and a tap after the 24-hour window. The live harness is ready but was not run. No live Meta or WhatsApp call was made by any test or by this session.

## Questions

- (Resolved by the orchestrator, 2026-11-18: blind approval is not acceptable; the message now shows the proposed text, as built above.)
- Should an approval that arrives outside the window be followed by a one-line "reply with any message to get buttons" hint? That would turn a free-text reply into a window opener, which is allowed, but it is a product choice.
