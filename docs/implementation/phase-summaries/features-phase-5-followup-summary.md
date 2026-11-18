# Feature Phase 5, Track C Close-Out Summary: Follow-up and Late Replies

- **Phase:** Feature Phase 5, Track C (F-10: one customer follow-up inside the 24-hour window, and the Human Agent tag for a person's reply up to 7 days)
- **Specification:** [features-phase-5-on-demand/sessions.md](../features-phase-5-on-demand/sessions.md), Track C, source [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md)
- **Sessions executed:** 08 and 09. Reports: [s08](../features-phase-5-on-demand/s08-report.md), [s09](../features-phase-5-on-demand/s09-report.md)
- **Baseline Git commit:** `1a58d41` (`main`). **Nothing is committed**: both sessions are uncommitted in the Track C worktree.
- **Alembic migrations of this track:** `0090` (`conversation_follow_ups`, parent `0083` after merge re-chain) and `0091` (`reply_drafts.message_tag`, `sim_sent_messages.message_tag`, expiry discovery function, parent `0090`); merged migration head is `0100`.
- **Status:** **Implemented and verified offline. Stopped for review.** Nothing was sent to a real Instagram account, and Meta has not been asked for the Human Agent feature.
- **Date:** 2026-11-18

---

## 1. Executive summary

Two small features that answer "what if the customer goes quiet, or I answer late". When a customer asked about a price or booking, got the assistant's answer and then stayed quiet, the owner can have **one** follow-up draft created (off by default, always approved by the owner, never after the 24-hour window, rechecked at send time). And when the 24-hour window is over, a **person** (never the assistant) can still reply for up to 7 days using Instagram's Human Agent tag, behind a capability flag that is off until Meta grants the feature. Both go through the existing approval and operations-ledger paths; neither adds a model call.

---

## 2. What changed, by feature

### 2.1 F-10 one follow-up (Session 08)
- Rule `inbox/follow_up.py`, no model call: a sent assistant answer to a price or booking question arms one delayed check (`follow_up_check`) after `follow_up_hours` (1 to 20, default 6). The check re-verifies everything under the conversation lock and creates one approval-required draft (`FOLLOW_UP_REQUIRES_APPROVAL`) from the owner's text or a built-in neutral text, rendered from usable facts and claim-validated.
- At most one per conversation, enforced by the table `conversation_follow_ups` (unique row, CHECK constraints, conditional state change). A new customer message cancels a scheduled row and withdraws a pending or queued follow-up.
- The 24-hour window is checked at draft time (boundary `last_inbound + 24h - 5 min`) and at send time (`SEND_MARGIN`, with `CUSTOMER_REPLIED`, `FOLLOW_UP_OFF` and `HUMAN_TAKEOVER` rejections before any operation row exists).
- Workspace setting (owner only, off by default, dedicated endpoints), two weekly report metrics (`follow_ups_sent`, `follow_up_replies`), settings panel, draft and approval labels, TR and EN.

### 2.2 F-10b Human Agent tag (Session 09)
- Research recorded in `platform-capabilities.md` section 1.10 with sources and access date: the Human Agent **feature** (App Review, Business Verification), the 7-day rule, the wire format `messaging_type=MESSAGE_TAG` plus `tag=HUMAN_AGENT`, and what is still unverified (V-HA). The App Review package has a Human Agent row, Screencast 5 (pending) and a checklist item.
- **One pure rule** `policy/message_tag.py` decides at creation and at send time. The reply policy rules stay 24-hour rules, so no assistant draft, approved answer, follow-up or agent draft can reach the extended window. A database CHECK allows the tag only on `source = owner`, `origin = legacy`, a user actor.
- **Capability** `human_agent`: a Meta account needs the messaging scope and `META_HUMAN_AGENT_ENABLED=true` (default off); mock accounts carry it. Without it the old 409 `MESSAGING_WINDOW_CLOSED` is unchanged.
- **Only a person's own typed reply** (the manual reply path) is accepted between 24 hours and 7 days; text started from or equal to an assistant draft is refused (`HUMAN_AGENT_NOT_ALLOWED`). The tag is part of the approval payload hash. The send executor re-runs the rule from the stored draft, uses the same ledger row `send_reply:{draft}`, and the Meta provider sends the two documented fields; the simulator allows 7 days only with the tag and records it.
- **Conversation view**: window state `open`, `human_agent_only` (with the end time) or `closed`, in the header and list, TR and EN.

---

## 3. Tests proving each acceptance criterion

| Criterion | Proof |
|---|---|
| S08: off by default creates nothing; one follow-up per conversation; customer reply cancels; window boundaries at draft and send time; isolation | `tests/unit/inbox/test_follow_up.py`, `tests/integration/inbox/test_follow_up.py`, `test_follow_up_settings.py`, `tests/isolation/test_follow_ups_isolation.py` |
| S08: report metrics | `tests/integration/reporting/test_follow_up_metrics.py` |
| S08: migration `0090` | `tests/integration/inbox/test_follow_up_migration.py` |
| S09: boundaries just under and over 24 hours and 7 days | `tests/unit/policy/test_message_tag.py`, `tests/integration/inbox/test_human_agent.py` (boundary table) |
| S09: AI draft, follow-up, approved answer and agent sources rejected; the database refuses a tag on them | `test_message_tag.py` (parametrised sources), `test_human_agent.py` (CHECK, expiry instead of tag, starting from or pasting an assistant draft, editing an assistant draft) |
| S09: flag off rejects, at creation and at send time | `test_human_agent.py` (capability off, switched off before send), `test_the_capability_needs_the_messaging_scope_and_the_setting` |
| S09: through the ledger, once, with the tag in the approved payload; simulator and Meta request shapes | `test_human_agent.py` (end to end, staff then owner approval, provider tests) |
| S09: window state shown in the view; isolation | `test_human_agent.py` (six ages, foreign workspace 404), frontend `inbox.test.tsx` (three states) |
| S09: migration `0091` | `tests/integration/inbox/test_human_agent_migration.py` |

---

## 4. Checks run

- Backend: `ruff check`, `ruff format --check`, `mypy app`, `lint-imports` (24 contracts kept) clean; Track C head `0091`, merged head `0100`.
- Backend tests: unit, contract, security and isolation (2472 passed, 18 skipped), and the inbox, operations, identity, agent and reporting integration directories (1297 passed); the few failures found were an exact-dict expectation of capabilities (fixed), an environment-only `.env` check and shared-DB interference, details in the [s09 report](../features-phase-5-on-demand/s09-report.md). The full suite (over an hour), `tests/e2e` and `tests/browser` were not run.
- Frontend (PowerShell): `lint`, `typecheck`, `i18n:check` (2785 keys), `build` clean; `vitest` 65 files / 921 tests passed.

## 5. Demo steps (offline)

1. Settings > Workspace: turn the follow-up on (owner), set 1 hour. Let a simulated customer ask a price, approve the answer, then stay quiet: a follow-up draft appears for approval; a customer message withdraws it.
2. With a mock account (capability on), once a simulated customer message is more than 24 hours old (in tests the injected clock is advanced; there is no demo control for it): the conversation header says "Human Agent window: only your own typed reply, until ...". Type a reply: it is queued, approved and sent; the simulator records `message_tag = HUMAN_AGENT`. Paste an assistant suggestion instead: refused.
3. Once it is more than 7 days old: the header says closed and the reply is refused.

## 6. Deviations from the briefs

- No automatic follow-ups (always owner-approved); agent-controlled accounts excluded (S08).
- The Human Agent capability is operator-set because Meta documents no per-account grant (S09, V-HA); the extended-window reply goes out untagged if the customer wrote again meanwhile.

## 7. Limitations and live items pending

- Everything about real Instagram behaviour is pending: follow-up delivery timing, the tagged request under Instagram Login, the error when the feature is not granted, the 7-day boundary (V-HA).
- Meta must grant the Human Agent feature (App Review, Business Verification) before `META_HUMAN_AGENT_ENABLED` can be turned on for real accounts; Screencast 5 is pending.
- Skipped follow-ups are visible only in the audit log; reports do not count tagged replies separately.

## 8. Open questions for the owner

1. Is an automatic (no-approval) follow-up wanted later? (needs a new policy action class)
2. Should staff, not only owners and managers, be able to use the Human Agent window? (today: same as any manual reply; staff replies wait for an owner's approval)
3. Pilot evidence that owners need late replies and follow-ups is still to be recorded in `mvp-scope.md`.
