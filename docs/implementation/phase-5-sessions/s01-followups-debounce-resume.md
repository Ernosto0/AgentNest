# Session 1: Phase 4 follow-ups, part 1 (debounce and resume)

**Plan:** `plan.md` §3 P5-00, items **Q2** and **Q6**. **Depends on:** Phase 4 on `main` (`a021ff9`). **Commits:** one per item.

## Read first
`docs/architecture/background-jobs.md` (§2, §3, §6), `workflows.md` §C, `docs/implementation/phase-summaries/phase-04-summary.md` (D8, limitations, open questions), `api-design.md` §2.9, `backend/app/jobs/{queue,worker}.py`, `backend/app/inbox/{processing,jobs,service,impact}.py`, `backend/app/operations/{accounts,accounts_router,jobs}.py`.

## Q2: one draft job per conversation
- `draft_reply` dedup key becomes `draft_reply:{conversation_id}`; `run_at` is **not** extended on re-enqueue; payload `message_id` becomes optional.
- New `jobs` primitive `RescheduleJob(run_at)`: the worker re-queues the same row without consuming an attempt (`attempts − 1`).
- At T3 of the draft job, if a newer inbound arrived during the run, discard the result and raise `RescheduleJob(now + debounce)`. Result: one job per conversation, nothing swallowed.
- Update every enqueue site (`inbox/processing.py`, `service.py`, `impact.py`).
- Docs: background-jobs §2/§6, workflows §C, Phase 4 decision D8 note.

## Q6: resume on reconnect
- `operations/accounts.reconnect_mock(account_id)`: `needs_reauth → connected`, same external id, audit `account.reconnected`, enqueue `resume_account`.
- Route `POST /social-accounts/{id}/reconnect` (mock provider only; permission `integrations.manage`; foreign id → 404).
- New `jobs.queue.expedite(session, dedup_key, clock)`: sets `run_at=now` on a queued row.
- `resume_account` job: re-enqueues or expedites `send_reply:{draft}` for queued drafts still inside their window. It must **not** resume `on_hold` content (plan G.2).
- UI: "Yeniden bağlan (simülasyon)" button on the connection screen (tr/en strings; `i18n:check` green).
- Docs: background-jobs (resume is Phase 5, not 6), api-design §2.9, and strike the Phase 4 limitation.

## Done when
- Tests: rapid inbound messages in one conversation → one job, newest message drafted; inbound during a run → rescheduled, no attempt consumed; `auth_revoked` send → reconnect → queued reply sent exactly once (ledger shows one op); reconnect needs permission and rejects foreign ids; `expedite` unit test.
- Phase 4 tests still green; lint, format, mypy, import-linter clean; frontend checks green.
- Two commits, docs updated in them.
