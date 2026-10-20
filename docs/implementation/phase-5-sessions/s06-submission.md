# Session 6: Submission, scheduling and approval

**Plan:** `plan.md` §2 **G2, G5, G13, G14 (notification kinds), G16, G17**, and the "staff cannot Publish now" decision, §3 **P5-04**. **Depends on:** session 5. **Commit:** `P5-04: …`.

## Read first
`workflows.md` §E (steps 1–5, 7, 8), `state-machines.md` §5, `observability.md` §4, ADR-014 note, the existing approvals service (`request`, `record_policy_grant`, callbacks registry, `cancel_for_subject`) and how `inbox`/`knowledge` register subject callbacks.

## Build
- `content/validation.py` (pure, unit-testable) implementing the G17 codes: blocking `CONTENT_MEDIA_REQUIRED`, `MEDIA_NOT_READY`, `CAPTION_REQUIRED`, `CAPTION_TOO_LONG`, `CAPTION_NOT_ALLOWED`, `ASPECT_RATIO_OUT_OF_RANGE`, `CLAIM_VALIDATION_FAILED` (+issues; covers caption **and** overlay suggestions), `SCHEDULE_IN_PAST`, `SCHEDULE_TOO_FAR`, `SCHEDULE_TIME_NONEXISTENT`, `SCHEDULE_TOO_SOON_FOR_APPROVAL`, `ACCOUNT_NOT_CONNECTED`, `CAPABILITY_MISSING`, `PUBLISH_QUOTA_FORECAST_EXCEEDED`; warnings `STORY_ASPECT_NOT_9_16`, `OVERLAY_TOO_LONG`. tr/en texts.
- `content/scheduling.py`: `zoneinfo`; window now − 1 min ≤ t ≤ now + 60 days; G13 (nonexistent local time → error; ambiguous → earlier instant, echoed in `schedule_local`); staff must schedule ≥ now + 15 min.
- Quota forecast: no rolling 24 h window around `t` may exceed `PUBLISH_DAILY_LIMIT` (counts items already scheduled).
- `content/payload.py`: canonical approval payload `{content_id, version, content_type, social_account_id, caption, overlay_text, media_asset_id, media_sha256, scheduled_at}` with `overlay_text` = the suggestions list (G5) → `payload_hash`. Stable under key order.
- `content/service.submit(ctx, item_id, schedule, self_approve, expected_version, actor)`:
  - `content.approve` + `self_approve` → `record_policy_grant(self_approved=True)` → `scheduled`.
  - Staff → `approvals.request(authorization, content.publish, required content.approve, expires_at=scheduled_at)` → `pending_approval`.
  - `self_approve` without the permission → 403.
  - On `scheduled`: `execute_before = scheduled_at + publish_max_delay_minutes` (G16), copy `is_simulated` from the account, enqueue `publish_content` with `run_at=scheduled_at` and dedup `publish:{id}:v{version}`. (The job handler itself arrives in session 7: register a stub or enqueue the type only if the registry allows; otherwise leave a clearly marked TODO test-only handler and say so in the report.)
- `content/subject.py` approval callbacks: approve → `scheduled` + enqueue; reject → `rejected` (with note); expire → `draft (APPROVAL_EXPIRED)` + notify requester. Hash/version mismatch at decision time → 409.
- Routes: `submit`, `cancel` (G1/E7; `publishing` → 409; ledger cancellation through `content/hooks.py`), `reapprove` (G2: increments `version`, full revalidation, fresh keys).
- Notification kinds `content.on_hold`, `content.published`, `content.failed` defined (G14) even though producers land in later sessions.
- Docs: workflows §E (G2, G5, G13), state-machines §5, observability §4 (G17, G14), api-design §2.7.

## Done when
- Tests: AC-D3 `unit/content/test_validation.py`; AC-D4 (19:00 Istanbul → 16:00 UTC, approval bound to version+hash, job `run_at`); AC-D7 `test_cancel.py`; AC-D8 `test_staff_submit.py` (staff cannot publish now, <15 min → 422, pending approval expires at `scheduled_at`); DST cases for Europe/Istanbul and Europe/Lisbon; payload-hash stability; stale hash → 409; self-approve without permission → 403; isolation.
- All checks green.
