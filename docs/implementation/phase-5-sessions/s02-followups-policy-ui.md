# Session 2: Phase 4 follow-ups, part 2 (policy explain, review button, staff approval state)

**Plan:** `plan.md` §3 P5-00, items **Q3**, **Q4**, **Q5**. **Depends on:** session 1. **Commits:** one per item.

## Read first
`workflows.md` §C.1, `api-design.md` §2.3 and §2.6, `backend/app/policy/{classes,rules_reply,router,service}.py`, `backend/app/inbox/views.py`, `phase-04-summary.md` open questions, frontend `AutomationSettings.tsx`, inbox `DraftCard.tsx`.

## Q3: explain the strictest-class rule
- `policy/classes.effective_mode` also returns the winning class.
- When it differs from the intent's own class, rules R13–R16 add a reason `CONTAINS_<CLASS>` (e.g. `CONTAINS_PRICING` → "Fiyat içeriyor, fiyat ayarı geçerli").
- Reason catalog entry plus `convo.reason.*` strings in tr/en; the inbox shows it as a reason chip.
- Docs: workflows §C.1 (keep the strictest-class rule, document the chip).

## Q4: explicit review button
- New `POST /automation-policies/review` (`automation.manage`): stamps `automation_reviewed_at` once (idempotent after) and audits `policy.reviewed`.
- `PUT /automation-policies` **no longer** stamps it. The seed still stamps directly.
- Automation screen shows "Bu ayarları inceledim" while unreviewed; hides it after.
- Docs: api-design §2.3.

## Q5: staff see approval state of their replies
- `ReplyDraft` gains `approval_state: {status, expires_at, decided_by_name, decided_at, decision_note} | null`, readable by anyone who may read the conversation (workspace isolation unchanged).
- `DraftCard`, for users who cannot approve: pending (who must approve, expiry) or approved/rejected/expired with the name and note.
- Docs: api-design §2.6. Regenerate `openapi.json` and `schema.d.ts`.

## Done when
- Tests: `CONTAINS_PRICING` reason appears when a pricing question is classed under a stricter policy and is absent otherwise; review stamps once, audits once, PUT does not stamp; non-managers get 403; staff view of a pending/approved/rejected/expired draft (backend view + Vitest for `DraftCard`).
- OpenAPI drift check clean; all backend and frontend checks green.
- Three commits with docs.
