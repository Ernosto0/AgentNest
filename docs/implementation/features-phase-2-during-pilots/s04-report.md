# Session 04 report: story replies and story mentions (F-04)

**Status:** implemented and tested offline. Nothing is verified against the real Instagram API.
**Migration:** `0052` (`20261116_0052_story_mention_thank_you.py`, `down_revision = "0048"`). Re-chain at merge.

## What changed

- **Finding on "blanket human_required".** A story reply that carries text was never forced to a person: only a message with no text is (`ATTACHMENT_ONLY`). So the real gaps were: a reply had no story context, and a text-less story mention always went to a person. Both are addressed; text-less story replies keep `ATTACHMENT_ONLY`.
- **Story reply context.** New `backend/app/inbox/stories.py` (read-only). A story reply's `story.id` is matched to a published `story_image` content item of the same workspace and account (`external_media_id`). The stored title, objective and overlay lines go to `draft_reply` as a labelled `<story_context>` data section. Placeholders are reduced to `[name]` so no value reaches the model. "No longer live" is added when the reply came 24 hours or more after publication. A story we did not publish has no context and is drafted exactly as before. Edits to `context.py` and `drafting.py` are small call sites.
- **Story mention.** Ingestion needed no parser change. A message is a plain mention when every waiting message is text-less and only `story_mention` attachments. If the owner has set up a thank-you for the reply language, no model runs and the template is the reply: rendered from usable facts, claim-validated, policy intent `story_mention`, class `reply.story_mention`, approval required by default. A template that fails to render or validate goes to a person (`FACT_NOT_USABLE` / `GROUNDING_FAILED`). Without a template the old `ATTACHMENT_ONLY` path holds. A mention next to a photo or text is not a plain mention.
- **Template storage.** The thank-you is an approved answer with the new intent `story_mention` (reuses the existing UI, RBAC, placeholder and literal-value checks, `needs_review` on fact change). One non-archived per language; no example question needed; intent cannot change to or from it; never offered to the model for ordinary DMs; "save sent reply as answer" never produces it.
- **Delegation.** Only a new action class `reply.story_mention` (so the existing automation policies can later make it automatic). Delegation ladder logic is untouched.
- **Conversation view.** `MessageOut.story` and a `StoryNote` component: for our own stories the stored picture (via the existing authenticated media endpoint), title and overlay lines, and "expired"; for any other story reply "a story we have no details for"; a mention shows "Mentioned you in their story" in place of "Photo or file". The provider story URL is never displayed (CSP `img-src 'self'`).
- **Simulator.** `webhook_format.message_item` writes a `story_reply` attachment as `reply_to.story`. Two new demo scripts: `story_reply`, `story_mention`.
- **Evals.** New dataset `evals/draft_reply/stories.yaml` (4 cases), `story_context` input key. Fake draft task uses the story title to pick the product for "how much is this?".
- **Docs.** `integrations.md` (webhook fields), `workflows.md`, `agent-runtime.md`, `api-design.md`, `data-model.md`, ADR-014, `platform-capabilities.md` (unverified row), `mvp-scope.md`.

## Contracts

- API: `MessageOut.story: StoryOut | null` = `{kind: reply|mention, known, title, lines[], media_asset_id, media_deleted, expired}` (all required). `ApprovedAnswerIn.example_questions` may be empty (service still requires one except for `story_mention`). Intent `story_mention` accepted. `PolicyItem.action_class` gains `reply.story_mention`. Error code `already_exists` on field `intent` (422) for a second thank-you in a language.
- `frontend/openapi.json` and `schema.d.ts` updated (exporter output differed from the committed file only in these changes, so the full export was used).
- DB: CHECK constraints replaced on `approved_answers.intent` and `automation_policies.action_class`. No new table, so no RLS or table-count test change. Downgrade deletes `story_mention` rows.
- LLM: `draft_reply` prompt `v3` (`app/ai/prompts/draft_reply/v3.md`, `DraftReplyInput.story_context`); `test_eval_harness` accepts `v3`. No new settings, jobs or notification types. New reason codes: none (reuses `ATTACHMENT_ONLY`, `POLICY_REQUIRES_APPROVAL`, `FACT_NOT_USABLE`, `GROUNDING_FAILED`).
- i18n (en/tr, `inbox.json`): `convo.story.*`, `automation.class.reply_story_mention`, `answers.intent.story_mention`, `answers.mentionHint`, `answers.mentionExists`.

## Files

Added: `backend/app/inbox/stories.py`, `backend/app/ai/prompts/draft_reply/v3.md`, `backend/migrations/versions/20261116_0052_story_mention_thank_you.py`, `backend/evals/draft_reply/stories.yaml`, `backend/tests/integration/inbox/test_story_context.py` (33 tests), `backend/tests/unit/inbox/test_stories.py`, `frontend/src/features/inbox/StoryNote.tsx`.
Changed: backend `ai/schemas.py`, `ai/tasks/draft_reply.py`, `demo/scripts/customer_messages.yaml`, `inbox/{answers,context,drafting,router,schemas,views}.py`, `integrations/instagram/webhook_format.py`, `knowledge/{approved_answers,constants}.py`, `policy/{classes,schemas}.py`, `evals/{loader,runner}.py`; tests `test_simulator.py`, `test_automation_policies.py`, `test_eval_harness.py`, `test_reply_rules.py`; frontend `openapi.json`, `api/schema.d.ts`, `ConversationPage.tsx`, `inbox/hooks.ts`, `ApprovedAnswers.tsx`, two test files, two `inbox.json` locale files; the docs listed above. `backend/pyproject.toml` D-01 line kept.

## Tests (all run from `backend/` with the required env vars; DBs `agentnest_p2s04[_a|_b]_test`)

- `tests/integration/inbox/test_story_context.py`: 33 passed. `test_simulator.py` (with `DEMO_TOOLS_ENABLED=true`, needed for dev routes): 36 passed.
- `tests/unit tests/isolation tests/security tests/contract` (shard `_a`): 2020 passed, 13 skipped, 3 failed. The 2 isolation failures need `DEMO_TOOLS_ENABLED=true`; rerun with it: pass (with `test_simulator_published.py`, 16 passed). `tests/security/test_invite_secrets.py` failed in the shard but passes alone (2 passed); not investigated further, unrelated to this work (likely shared-state flake).
- `tests/integration/inbox tests/integration/policy tests/integration/knowledge` minus `test_simulator.py` (shard `_b`): 435 passed, 6 failed, all `test_simulator_published.py`, which pass with `DEMO_TOOLS_ENABLED=true` (above).
- `tests/integration/agent/test_memory_review.py tests/unit/evals tests/unit/inbox`: 138 passed. Evals `python -m evals run --task draft_reply`: 65/65, 0 hard failures (fake).
- Not run: the rest of `tests/integration` (content, retention, reporting, etc.); this session did not change those modules.
- `ruff check`, `ruff format --check`, `mypy app` (361 files), `lint-imports` (23 kept): clean.
- Frontend (PowerShell): `npm.cmd run lint`, `typecheck`, `i18n:check` (2444 keys) clean; `npm.cmd test` 52 files, 789 passed; `npm.cmd run build` succeeded.

## Deviations and decisions

- Mention template is an approved answer, not a workspace setting (reuses UI and validation). "Expired story" is interpreted as a reply 24 h or more after our own story was published: the stored record still gives context and the model is told it is no longer live; the thumbnail is the stored picture, not a provider URL.
- No fetch of a caption from the Graph API: no confirmed way (unverified). Stories we did not publish stay on the old path.
- Prompt bumped to `v3`; if Session 02 also bumps `draft_reply`, renumber at merge. Session 02 also edits `context.py`/`drafting.py` (my edits: `DraftContext` three new defaulted fields, `story_context=` in `_task_input`, a `_mention_plan` branch in `plan_with`).
- `reply.story_mention` appears as a sixth row on the automation settings page; `auto` still needs readiness `ready`, as for other classes.

## Open questions

- Real webhook shapes (V-08): does a mention carry a story id, and does the story-reply `story.id` equal the media id returned when publishing? Both unverified.
- Should a mention thank-you be offered in the other reply language when only one language has a template? Currently it goes to a person.
- The thank-you applies to account-agent mode? In agent-controlled accounts the mention is still just an event for the agent (unchanged).
