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
