# Phase 6 Q&A: decisions requiring code changes

**Date:** 2026-10-22 (Europe/Istanbul).
**Source:** [Phase 6 summary, open questions](../phase-summaries/phase-06-summary.md#7-open-questions-for-review) and the owner's answers to the review questionnaire.
**Status:** Q1, Q2 and Q8 implemented and verified locally on 2026-10-23. See [implementation report](qa-implementation-report.md).

Only questions whose accepted answers require application code or translation-catalog changes are included. Question numbers match the review questionnaire. The requirements below record the approved scope; the implementation report records the resulting changes and verification. This follow-up does not establish that Gate 1 has passed.

## Q1. Historical report snapshots

**Question:** Should yesterday's report preserve its original numbers and the records behind those numbers, even after current state changes? Recommended: yes; deliberate regeneration creates a newly calculated snapshot.

**Owner answer:** Yes.

**Accepted decision:** A stored report's values and contributing membership remain consistent with its generation snapshot. Explicit regeneration creates a new snapshot; ordinary reads do not silently recompute the old one.

**Required changes:**

- Persist contributing membership and the measurements needed to explain each stored metric, together with its values.
- Serve historical drill-downs from the corresponding snapshot instead of recomputing their membership from current state.
- Make explicit regeneration create a new snapshot without overwriting the previous snapshot's evidence.
- Preserve the accepted answered-burst calculation and one-decimal median. The linked durations explain the median; their row count is not the median value.
- Update the reporting contracts and add lifecycle coverage for changed conversation/approval state, snapshot-consistent pagination, regeneration and workspace isolation.

**Original gap (resolved):** `backend/app/reporting/service.py` stored aggregate values and overwrote them on regeneration. `backend/app/reporting/drilldown.py` recomputed membership and values at read time. The reproduced AC-E3 mismatch is now covered by lifecycle tests and a browser regression. Migration 0015 adds immutable generations and `report_items`; links and cursors carry the generation ID.

## Q2. Retention-safe report evidence

**Question:** When old source records are deleted, should we retain minimal, content-free evidence that explains historical reports? Recommended: yes; explicitly identify when a report can no longer be fully regenerated.

**Owner answer:** Yes.

**Accepted decision:** Source retention must preserve the minimal evidence behind existing report snapshots. A regeneration request must explicitly identify when the available source data cannot reproduce a complete report.

**Required changes:**

- Retain content-free contributing evidence and metric measurements independently of source records that retention can remove.
- Keep historical values and drill-down membership consistent after source deletion or text redaction, without retaining message text or raw webhook payloads as report evidence.
- Detect and expose incomplete regeneration after source retention; do not silently present the remaining records as complete history.
- Update the reporting/retention contracts and add lifecycle tests for inbound-event deletion, message/draft text redaction, evidence isolation and regeneration completeness.

**Original gap (resolved):** Historical `integration_errors` drill-downs and regeneration depended on inbound-event rows that retention deletes. Saved membership now survives independently, and deletion records content-free source gaps in the same transaction. Regeneration over a known gap returns an explicit error and preserves existing reports.

## Q8. Reconnect wording

**Question:** Should both language catalogs direct users to "Instagram bağlantısı" / "Instagram connection", matching the actual screen?

**Owner answer:** Yes.

**Accepted decision:** The reconnect instruction must name the existing Instagram connection screen in Turkish and English.

**Required changes:**

- Update `errors.ACCOUNT_NEEDS_REAUTH.next` in `backend/app/core/i18n/tr.json` and `backend/app/core/i18n/en.json`.
- Apply matching wording in `frontend/src/i18n/locales/tr/common.json` and `frontend/src/i18n/locales/en/common.json`.
- Verify catalog parity and the connection error's rendered instruction.

**Original gap (resolved):** The instruction directed users to Reconnect in Settings, while the connection screen is a direct More entry. Both backend and frontend catalogs now name the Instagram connection screen in Turkish and English.
