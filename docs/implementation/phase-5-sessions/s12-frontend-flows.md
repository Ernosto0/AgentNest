# Session 12: Frontend flows (generate, schedule, failure, on-hold, approvals)

**Plan:** `plan.md` §3 **P5-08 (part 2)**. **Depends on:** session 11. **Commit:** `P5-08b: …`.

## Read first
Session 11's output, `workflows.md` §E (UI-relevant steps), `user-journeys.md` J4, `api-design.md` §2.7, error catalog (`observability.md`), existing `ApprovalDetailSheet.tsx`, `notifications/describe.ts`, `DevPanel.tsx`, command result rendering.

## Build
- `GenerateSheet`: objective input, type, account; uses `client_request_id`; shows `generation` running/failed; failure leaves the manual draft.
- `ScheduleSheet`:
  - local date and time with "İstanbul saati" (workspace timezone label);
  - "Hemen yayınla" only for users with `content.approve`; **staff never see it** and a <15 min time shows the `SCHEDULE_TOO_SOON_FOR_APPROVAL` message;
  - exact summary of what will be posted and when;
  - "Onayla ve zamanla" (approvers, `self_approve`) vs "Onaya gönder" (staff);
  - maps submit item codes (G17) to inline messages; `SCHEDULE_TIME_NONEXISTENT` handled.
- `FailureDetail`: error-catalog what/next, with the retry/next-attempt info.
- `OnHoldActions`: edit / re-approve / cancel, with the hold reason (`FACT_CHANGED`, `ACCOUNT_UNAVAILABLE`); re-approve handles validation failure showing the old price.
- Simulated permalink with `SimulatedBadge`.
- Other files: `ContentApprovalBody` inside `ApprovalDetailSheet` for `content.publish` (shows exactly the bound payload: caption, overlay, media, time); `notifications/describe.ts` for `content.on_hold|published|failed`; Dev panel simulator list and new failure-rule operations; command results link to content; capability labels (G4).
- All strings tr/en.

## Done when
- Vitest: no "now" option for staff; approver sees both buttons; schedule payload correct for local→UTC; each submit error code renders; on-hold actions per reason; approval body shows bound payload; notification descriptions; INV-18 still holds in every component showing status.
- All frontend checks green; typecheck against regenerated `schema.d.ts`.
