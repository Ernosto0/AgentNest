# Phase 6: open questions and deviations

Running ledger kept by the operator. One entry per item, newest sessions last. Passed to session 11 for the phase summary.

## Session 1 (P6-01a, P6-01b)
- **Median first response rule (confirm).** The brief and workflows §F.1 leave open what counts as an answered burst. Chosen: the burst's first inbound message is in the period, and the next outbound message (any sender kind) is before `period_end`. Deleted inbound messages are ignored. The median is rounded to one decimal. Written into workflows §F.1.
- **Half-open periods.** Periods are `[start, end)`. On a live "today" (`end = now`) a record stamped exactly at `now` is not yet counted. Matters for AC-E4 tests with `FrozenClock`.
- **`MESSAGING_WINDOW` duplicated** in `reporting/definitions.py` so reporting does not import inbox logic. A test asserts it equals `app.inbox.context.MESSAGING_WINDOW`.
- **Stale docstring** in `query_activity_summary.py` ("arrives in Phase 6"); session 2 rewrote that executor.

## Session 2 (P6-01c, P6-01d, P6-02a, P6-02b)
- First attempt was stopped by the owner part-way; a retry kept the committed work and committed the rest as P6-02b. No deviations or questions reported.
- The report did not map each "Done when" bullet to a named test, and did not read the Vitest pass count.

## Session 3 (P6-03a, P6-03b, P6-01e)
- **Flaky test:** `frontend content/crosscutting.test.tsx` failed once in a full run, passed on two reruns. Looks timing-related; not investigated.
- **Module location deviation:** activity code lives in the new package `backend/app/activity/` (not `audit/feed.py` etc.) because the import contract "audit and jobs depend only on core" forbids the labels. New modules were added to the "no API layer" contract.
- **Catalog names corrected in observability §5:** `message.native_reply_detected` -> `message.native_reply_recorded`, `conversation.released` -> `conversation.release`; added `reply_draft.<status>`, `reply.outcome_unconfirmed`, `reply.late_confirmation`, `approval.granted`.
- **`operation.*` actions** are in the `system` group (H7 names no group); `system` also catches unmapped actions.
- **Report screen** shows server summary section titles and `summary.text` only for an empty day; rows are built from metrics with frontend labels so numbers can be links. Zero/null rows hidden.
- **`resource.link`** in activity entries is a plain route string or null, not `{api, route}`.
- **i18n files** `tr.json`/`en.json` rewritten by script, LF; diff is additions only.
- **OPEN (non-blocking):** `screen_link` for `content_on_hold_now` is `/content?status=on_hold`, but `ContentPage` only reads `?tab=`, so the shortcut opens the default tab. Should probably map to the `problems` tab.
- **For session 7:** must add `member.invite_revoked` etc. to observability §5, `groups.py` and the activity texts (coverage test fails otherwise).

## Session 4 (P6-04a, P6-04b, P6-04c)
- **Ledger item closed:** `ContentPage` now reads `?status=` and maps it to the tab; `/content?status=on_hold` opens `problems`.
- **Dev servers / E2E:** the owner's `npm run dev` and `uvicorn --reload` were running; Vite served a broken module graph (`NotificationBell` export), so E2E ran on `E2E_API_PORT=8100 E2E_WEB_PORT=5273`. **Restart the dev Vite server.** E2E global setup re-seeded the dev database `agentnest` (demo data there was wiped, as it always does).
- **Only scenario A E2E run** (15/15 on 3 projects); the full suite is session 10/11.
- **Interpretation:** the "failures" attention card uses `content_failed` (failed today); the needs-human card uses `attention_now`, which also counts `needs_approval`/`failed` conversations.
- **Existing tests rewritten:** bell now links to a page (not a sheet); placeholder assertion in `app.test.tsx`; unknown notification types in tests replaced by catalog types; `mockApi` background routes extended.
- **Dedup key rename:** unread notifications under the old `account-reauth:{id}` key are not migrated; one extra notification may appear (noted in observability §4.4).
- **For later sessions:** each new notification type (5: `account.degraded`/`account.recovered`; 7: `member.joined`; 9: `knowledge.promotion_expired`) must extend `catalog.py`, regenerate `catalog.json` (`uv run python -m app.notifications.catalog`) and add a `describe.ts` sentence.

## Session 5 (P6-05a, P6-05b)
- **Full backend suite not re-run on the final two commits.** It passed (2427) on the tree before the split; after the split only ruff, mypy, lint-imports and selected folders were re-run. Session 6 was asked to run the full suite first. E2E not run.
- **Existing test changed:** `test_publish_retry.py::test_ac_f2…` asserted `consecutive_failures == 5`; with H10 the attempts (1, 6, 21, 51 min apart) do not share one 10-minute window, so it now asserts the account stays `connected` with counter 1.
- **Commits split by file, not hunk** (`health.py` and the send reschedule are in 5a).
- **Dedup:** `account.degraded` key is `account:{id}:degraded`; an unread one from an earlier cycle suppresses a new one (existing dedup behaviour).
- **Half-open:** a degraded account is probed only by the health check or the half-open send/publish. The publish quota read is skipped for non-`connected` accounts, including half-open; the provider enforces the limit at publish time.
- **Policy rule R1** (`workflows.md` ~line 170) still requires `connected` exactly; unchanged (not in the brief). A draft can still be created while degraded but is held at send time.

## Session 6 (P6-05c, P6-05d)
- First attempt was interrupted (previous process ended); the retry reviewed its uncommitted system-health files, fixed 5 mypy errors and committed them.
- **Full backend suite green** (2438 passed); closes the session 5 gap. Frontend 458 tests; **full E2E 90/90** on ports 8100/5273.
- **Response fields renamed** to avoid the response-schema secret scan on "token": `connection_expires_at`, `input_units`, `output_units`.
- **Bug fixed:** `accounts_router.account_out` was not filling `degraded_until`.
- **Link targets beyond the brief:** the `account.*` notification link and the on-hold "check the connection" link now point to Connections (3 existing test hrefs changed).
- **System health screen** never shows raw error codes; uses `errors.<CODE>.what`, generic sentence for uncatalogued codes.
- **Dev database `agentnest` migrated** to 0013 with `alembic upgrade head` (it was at 0012, so `/readyz` returned 503).
- **Prettier slip:** ran prettier with defaults once, reformatted existing files; reverted with `git checkout` and reapplied only the intended edits (repo has no prettier config). Final diff has no formatting churn.
- **OPEN (non-blocking):** the `ACCOUNT_NEEDS_REAUTH` catalog text still says "Ayarlar'da Yeniden bağla'ya basın" (session 4/5 wording); consider aligning with the new Connections screen.
