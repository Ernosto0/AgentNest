# Session 10: Content commands (owner command system)

**Plan:** `plan.md` §3 **P5-03 (commands half)**. **Depends on:** session 9 (and session 6 for the cancel route). **Commit:** `P5-03b: …`.

## Read first
Phase 3 docs: `phase-03-command-system.md`, `phase-03-summary.md`, `agent-runtime.md` (interpreter), `workflows.md` §A/§D, `backend/app/commands/{registry,resolver,service,transitions}.py` and existing executors (fact update is the template, including its `Confirm` approval), `testing-strategy.md`.

## Build
- `InterpretCommandInput.content_catalog` with aliases `C1..Cn`: items in the next 14 days plus recent failures.
- ContentRef resolver: alias → else filter by local date (workspace timezone), type and status; 0 matches → `REFERENCE_NOT_FOUND`; >1 → clarification with title and time options.
- Executors (`commands/executors/`):
  - `content.create_draft`: no confirmation; `interpreting → executing` shortcut; creates a draft and enqueues generation (session 9).
  - `content.cancel_scheduled`: confirmation approval `command.cancel_content` with payload `{content_id, content_version}`; generalise `Confirm` beyond `fact_id`; permission `content.approve` checked against the **human**; executes as the decider; stale version → 409.
  - `query.content_status`.
  - `query.explain_failure`: `latest_failure` or a ref, explained from the error catalog with links.
- Fake interpreter grammar for the demo phrases ("Deneme dersi için bir story hazırla", "yarınki postu iptal et", "son hata neydi?").
- Command result payloads link to content items.
- Docs: workflows §A (new intents), agent-runtime interpreter section, api-design (command result shapes).

## Done when
- Tests: demo phrase → draft created with generation queued; resolver ambiguity (two matches → clarification) and not-found; cancel via command → confirm → item `cancelled`, op/job cancelled, stale version rejected; permission checked against the confirming human; explain_failure on a failed item; isolation.
- Phase 3 command tests still green; all checks green.
