# Follow-up review fixes

Date: 2026-11-20 (Europe/Istanbul). Baseline: `e3580a4`.

## Changes

1. **Independent sentences cannot inherit basic-topic authority.** The request classifier
   splits full stops and colons as well as existing clause separators, while preserving
   decimal numbers and times such as `1.5` and `09:00`. An unknown second request remains
   approval-required even when the reply references a verified fact for the first request.
   Regressions cover Turkish, English, German, Russian and Arabic.
2. **Unanswered history does not require an Agent event.** Response evidence supplements
   the current event-owned response with scoped, undeleted earlier inbox messages from
   legacy/human handling. Earlier complaints, image warnings and pending media therefore
   constrain the current response after adoption/release. Existing outbound replies and
   sent-draft coverage still discharge resolved history. The query remains bounded and
   overflow cannot authorize automation. Deleted messages and other customers' conversations
   remain excluded. A pending media completion from this unrecorded history may wake the
   latest unanswered response without fabricating an original customer event or duplicating
   an already sent reply.
3. **The fact-revalidation test uses an actual schema state.** The test withdraws
   verification with `status = unverified` rather than trying to store nonexistent
   `status = stale`. It now reaches and verifies the expected non-sendable `FACT_CHANGED`
   result on migrated PostgreSQL.

The related transcript unit test also now supplies real-shaped response evidence and patches
the function used by `dm.revalidate`, so it exercises the transcript approval floor instead of
passing because the evidence was empty. No application transcript rule was relaxed.

The Account Agent contract documentation was updated. No migration or API change is required.

## Verification

- Four affected policy/media/practice/acceptance unit files: **184 passed**.
- The three review integration files plus existing context/grounding integration tests:
  **54 passed**, including all new history/sentence regressions and the formerly failing
  fact-revalidation case. These passed in the combined selection; its one outdated mock
  failure was then corrected and all 184 unit tests re-run successfully.
- Full backend Ruff lint: **passed**. Full format check: **918 files formatted**.
- `mypy app`: **passed**, 469 source files.
- Import linter: **27 kept, 0 broken**.
- `git diff --check`: **passed**.

Database checks used PostgreSQL 17 on loopback port 55439 and the dedicated disposable
`pivoris_three_review_fixes_20261120_test` database. Existing application databases were not
reset or migrated. The disposable PostgreSQL instance was stopped after verification.

## Existing failures outside these three fixes

Broader verification also ran `tests/integration/agent/test_dm_transcript.py`. Its no-voice
control passed, but these two existing voice tests failed because no `AgentAction` was created:

- `test_an_automatic_dm_delegation_still_asks_when_a_voice_note_is_in_the_conversation[True]`
- `test_voice_only_inbound_generates_approval_required_draft`

Both failures were reproduced with the committed `e3580a4` versions of the three modified
application modules loaded in memory before pytest. The voice tests and their assertions
were preserved. This report does not claim the full backend suite or live voice acceptance
passes.

No commit, push, deployment, production configuration change or live provider send was performed.
