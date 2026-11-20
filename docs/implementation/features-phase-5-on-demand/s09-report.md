# Feature Phase 5, Session 09: Human Agent tag for a person's reply up to 7 days (F-10b) and Track C close-out

**Status:** Done offline (research, backend, frontend, docs). Live Instagram behaviour is **pending** (nothing was sent to a real account; Meta has not been asked for the Human Agent feature).
**Baseline:** `1a58d41` plus Session 08's uncommitted work. **Migration head of this track:** `0091` (`down_revision = "0090"`). Nothing committed.
**Trigger:** moved out of Deferred in `mvp-scope.md` on 2026-11-18 at the owner's request (all Feature Phase 5 sessions were requested). Pilot evidence for late replies is **not yet recorded**.

## Research (recorded in `docs/research/platform-capabilities.md` section 1.10, accessed 2026-11-18)

- A **feature**, not an OAuth scope. It needs App Review, Business Verification (Advanced Access) and possibly additional contracts. The Instagram Login scopes stay `instagram_business_basic` and `instagram_business_manage_messages`.
- Rule: a human agent replies within 7 days of the user's last message, for an issue that cannot be resolved in the standard window (business closed, more than 24 hours needed).
- Request: `messaging_type: "MESSAGE_TAG"` and `tag: "HUMAN_AGENT"` beside `recipient` and `message`. Meta's Page `messages` reference says only `HUMAN_AGENT` exists for Instagram. **Unverified:** the same fields under Instagram Login (`graph.instagram.com`); the error when the feature is not granted; the exact 7-day boundary; any way for an app to read whether the feature was granted. Logged as V-HA.
- Meta's pages state no explicit automation prohibition (secondary sources say human-only). Pivoris takes the conservative reading: human-typed only.
- The App Review package (`docs/operations/meta-app-review-package.md`) has a Human Agent row in section 3, a pending Screencast 5 and a checklist item.

## What was delivered

- **Pure rule** `policy/message_tag.py` (added to the import-linter purity contract): `window_state` (`open`, `human_agent_only`, `closed`) and `evaluate_message_tag`. Any automated source (`source != owner`, `origin != legacy`, actor not `user`, an agent action, a follow-up) is rejected after the standard window, and a draft that already holds the tag is rejected even inside it. R2 of the reply policy stays a 24-hour rule, so no assistant draft reaches the extended window.
- **Capability flag** `human_agent` on the account: Meta accounts get it from `compute_capabilities` only when the messaging scope is granted **and** `META_HUMAN_AGENT_ENABLED=true` (default false; the send path and the view re-check the setting); mock accounts carry it (`MOCK_CAPABILITIES`), the simulator supports the tag. `inbox/human_agent.py::available` is the single check.
- **Creating the reply** (`inbox/service.py`): `_check_sendable` returns `(window_end, tag)`. Only `submit_manual_reply`, and editing a draft that already holds the tag, may ask for the extended window. Margin 2 minutes on creation. A reply is refused with 409 `HUMAN_AGENT_NOT_ALLOWED` when it starts from an assistant draft (`from_draft_id` of a non-owner draft) or equals the text or suggestion of a recent assistant draft. Editing an assistant draft after 24 hours still fails with `MESSAGING_WINDOW_CLOSED`. With the flag off the old 409 `MESSAGING_WINDOW_CLOSED` is unchanged.
- **Storage** (migration `0091`): `reply_drafts.message_tag` with CHECK `message_tag_human_only` (tag only with `source = owner`, `origin = legacy`, `created_by_actor_type = user`), `sim_sent_messages.message_tag` (simulator evidence), and the expiry discovery function `discover_expired_reply_draft_ids` replaced so a tagged draft waits for 7 days (downgrade refuses while tagged drafts exist).
- **Approval binding**: the approval payload includes `message_tag` only when set (existing hashes unchanged), so a tag cannot be added or dropped after approval. The approval summary carries the reason `HUMAN_AGENT_TAG`.
- **Send path** (`operations/send._prepare`): for a tagged draft the same policy function re-runs from the stored draft. Automated source cancels (`HUMAN_AGENT_AUTOMATED_SOURCE`), capability off cancels (`HUMAN_AGENT_DISABLED`), a closed 7-day window expires the draft with no operation row, and when the customer wrote again and the standard window is open the reply is sent without the tag. Deadline and reschedule use the effective window end. The `send_reply` ledger row records `provider_ref.message_tag`; the provider is called with the tag only when set (existing test providers without the argument still work). `operations/resume.py` and `inbox/expiry.py` know the 7-day window of tagged drafts.
- **Providers**: `send_text_message(..., message_tag=None)` in the protocol; Meta adds `messaging_type: MESSAGE_TAG` and `tag: HUMAN_AGENT` only when tagged and rejects any other tag before the network; the mock accepts 24 hours untagged or 7 days with `HUMAN_AGENT`, rejects other tags and stores the tag.
- **API**: `ConversationOut.window_state` and `human_agent_until`; `ReplyDraftOut.message_tag`; error `HUMAN_AGENT_NOT_ALLOWED` (409) with EN and TR text. `frontend/openapi.json` and `schema.d.ts` patched in place.
- **Frontend**: the conversation header and list row show the window state: normal timer when open; "Human Agent window: only your own typed reply, until <time>" (workspace time zone) when only the tag can send, with a hint box saying assistant drafts and follow-ups cannot be sent; the existing "closed" text when closed. Reason chip `HUMAN_AGENT_TAG` and the error text, TR and EN.
- **Docs**: `platform-capabilities.md` (section 1.10, V-HA, updated 1.5 row), `meta-app-review-package.md`, `mvp-scope.md` (F-10b row, Deferred row), `workflows.md` (Human Agent tag subsection), `api-design.md`, `data-model.md`, `integrations.md`, `observability.md`, `state-machines.md`, `environment-variables.md`, `.env.example`.

## Contracts

| Item | Value |
|---|---|
| Env var | `META_HUMAN_AGENT_ENABLED` (default `false`) |
| Capability | `social_accounts.capabilities.human_agent` |
| Columns | `reply_drafts.message_tag`, `sim_sent_messages.message_tag` (migration `0091`, parent `0090`) |
| Constraint | `ck_reply_drafts_message_tag_human_only` |
| Error / reason codes | `HUMAN_AGENT_NOT_ALLOWED` (409), `HUMAN_AGENT_DISABLED`, `HUMAN_AGENT_AUTOMATED_SOURCE`, `HUMAN_AGENT_TAG` (note) |
| Wire format | `messaging_type=MESSAGE_TAG`, `tag=HUMAN_AGENT` |

## Tests and checks

New tests: `tests/unit/policy/test_message_tag.py` (window boundaries at 24 h and 7 d with the margin, capability off, every automated source parametrised over three ages, tag held inside the window), `tests/integration/inbox/test_human_agent.py` (36 tests: boundaries 23:57:59, 23:58, 24:00:01, 3 days, 7 days minus 2 minutes minus 1 second, 7 days minus 2 minutes, 7 days plus 1 hour; capability off; real-account setting; scope; end-to-end send once through the ledger with the tag in the simulator, the operation and the approval hash; in-window reply untagged; staff reply approved by the owner; edit keeps a matching approval; assistant draft rejected by the database CHECK; assistant, follow-up and approved-answer drafts expire instead of being tagged; starting from or pasting an assistant draft refused; editing an assistant draft never extends its window; capability switched off before send cancels with nothing sent; last minute of 7 days; standard window reopened sends untagged; expiry sweep waits for 7 days; simulator and Meta request shapes; window state in the conversation view for six ages; foreign workspace 404), `test_human_agent_migration.py` (up/down/up), frontend `inbox.test.tsx` (three window-state cases).

### Check results

- Backend: `ruff check`, `ruff format --check`, `mypy app` (436 files) and `lint-imports` (24 contracts kept) clean. `alembic` head `0091`.
- Backend tests (not the full suite): `tests/unit`, `tests/contract`, `tests/security`, `tests/isolation` 2472 passed, 18 skipped (live probes), 3 failed and 1 error on the first pass. The failures were: `test_oauth_client.py::test_authorize_and_capabilities` (exact capability dict, fixed: the new `human_agent` key), `test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config` (environmental: the worktree `.env` has `DEMO_TOOLS_ENABLED=true`; passes with `DEMO_TOOLS_ENABLED=false`), and `test_invite_secrets.py` plus one isolation listing error (both passed on re-run, shared test DB interference as in Session 08). A migration bug found by that run (`op.f` at module import) was fixed. Then `tests/integration/inbox`, `operations`, `identity`, `agent` and `reporting`: 1297 passed, 1 failed (`test_mock_publishing_wiring.py` exact `MOCK_CAPABILITIES` dict, fixed, 4 passed on re-run). New tests: `test_human_agent.py` 36 passed, `test_message_tag.py` (unit) passed, migration up/down/up passed.
- Frontend (PowerShell): `lint` clean, `typecheck` clean, `vitest` 65 files / 921 tests passed, `i18n:check` 2785 keys, `build` clean.
- Not run: the full backend suite (over an hour), `tests/e2e`, `tests/browser`.

## Deviations and decisions

- **No per-account grant is readable from Meta**, so the flag is operator-set (`META_HUMAN_AGENT_ENABLED`) combined with the messaging scope, instead of an OAuth-derived grant. Recorded as V-HA.
- **Tag state at send time can differ from creation**: if the customer wrote again so the standard window is open, the reply goes out untagged (a tag inside the standard window is not needed and is not documented as accepted). The approval still covers the stored tag.
- **Margins**: creation refuses within 2 minutes of a window end (same as the existing 24-hour manual reply check), send refuses within 60 seconds. The conversation view uses the creation margin so the state shown matches what the reply box will accept.
- **The tag is not requested by the user**: it follows from the window state; there is no toggle. A reply that begins from an assistant suggestion (the "use suggestion" path for a conversation handed to a person) is refused after 24 hours with a clear message.
- **`from_draft_id`/text-equality is a heuristic** for "typed by a person": a person who retypes an assistant text with small changes is accepted (it is then their own words and approval). The hard guarantees are the source, origin, actor and agent-action checks.
- `frontend/openapi.json` carried one stray non-UTF-8 byte (a cp1252 section sign from an earlier session); it was repaired to UTF-8 while patching.

## Limitations

- Live behaviour is **pending**: the tagged request under Instagram Login, the error when the feature is not granted and the 7-day boundary are assumptions (V-HA). Real accounts keep the flag off until Meta grants the feature.
- An untagged reply accepted inside the standard window whose send is delayed past the window's end is expired like any draft; the person writes it again and the new reply then carries the tag.
- The weekly report does not count tagged replies separately.

## Questions

1. Should the Human Agent window be offered only to roles that may approve (owner and manager), or to staff as well (staff replies already wait for an owner approval)? Current behaviour: same as any manual reply.
2. Is a UI hint wanted for owners when the flag is off and a customer is past 24 hours ("Human Agent needs Meta approval")? Not added: it would explain an operator setting.
