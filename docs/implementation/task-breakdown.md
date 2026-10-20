# Task Breakdown Index

**Purpose:** A compact, dependency-ordered index of all implementation tasks, plus the protocol for executing one task. Task details live in the phase documents and are not repeated here. Sizes: **S** ≈ one short focused session, **M** ≈ one full session, **L** ≈ split into two or three sessions (each ending green).

## 1. Execution protocol for a single task

1. Read the task row in its phase doc and the documents it references.
2. Write or extend tests first where the contract is clear (state transitions, validators, policy rules), then implement.
3. Keep changes within the modules listed for the phase. Respect the import rules ([component-design.md §3](../architecture/component-design.md)).
4. Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest <relevant paths>` (backend) and/or `npm run lint && npm run typecheck && npm test` (frontend).
5. Update docs if a contract changed. Add i18n keys in tr and en. Add error codes to the catalog.
6. Summarise: files changed, tests added, deviations, open questions.

**Review checklist (for the reviewer and the agent):**
- [ ] Workspace scoping on every new query; isolation harness covers new routes.
- [ ] State changes go through the transition function, are audited, and use the expected-state guard.
- [ ] No external call inside a DB transaction; operations ledger used for side effects.
- [ ] No secrets or message text in logs, job payloads or API responses.
- [ ] `is_simulated` propagated where applicable.
- [ ] Time handled via `Clock` and the workspace timezone.
- [ ] LLM output validated; model flags only escalate.

## 2. Index

| ID | Title | Depends on | Size |
|---|---|---|---|
| **Phase 1: Foundation** | | | |
| P1-01 | Repository scaffolding | — | S |
| P1-02 | Backend project | P1-01 | S |
| P1-03 | Core: config, logging, errors, clock, i18n, canonical | P1-02 | M |
| P1-04 | Database and migrations | P1-03 | S |
| P1-05 | Identity schema | P1-04 | S |
| P1-06 | Authentication | P1-05 | M |
| P1-07 | Tenancy and workspaces (+ isolation harness) | P1-06 | M |
| P1-08 | Audit log | P1-04 | S |
| P1-09 | Job queue and worker | P1-04, P1-08 | L |
| P1-10 | CLI and seed | P1-07 | M |
| P1-11 | Frontend scaffold | P1-06 (API contract) | L |
| P1-12 | Frontend test setup | P1-11 | M |
| P1-13 | CI | P1-09, P1-12 | M |
| P1-14 | Docs sync | all P1 | S |
| **Phase 2: Business knowledge** | | | |
| P2-01 | Value types, parsing, formatting | Phase 1 | M |
| P2-02 | Templates | P2-01 | S |
| P2-03 | Knowledge schema | P2-01 | S |
| P2-04 | FactService | P2-02, P2-03 | M |
| P2-05 | Candidates | P2-04 | M |
| P2-06 | Readiness | P2-04 | S |
| P2-07 | Knowledge API | P2-05, P2-06 | M |
| P2-08 | Demo fact seed | P2-04 | S |
| P2-09 | Knowledge UI | P2-07 | L |
| P2-10 | Workspace creation wizard | P2-07 | M |
| P2-11 | Phase 2 tests and E2E | all P2 | M |
| **Phase 3: AI runtime, commands, approvals** | | | |
| P3-01 | LLM integration (fake, OpenAI) | Phase 2 | M |
| P3-02 | Task runner and agent runs | P3-01 | M |
| P3-03 | Renderer and claim validator | P2-01 | M |
| P3-04 | Approvals and notifications | Phase 2 | L |
| P3-05 | Command intake and interpretation | P3-02, P3-04 | L |
| P3-06 | Command executors | P3-05 | M |
| P3-07 | Impact framework (`fact_references`) | P3-06 | S |
| P3-08 | Extraction | P3-02 | M |
| P3-09 | Eval harness | P3-05, P3-08 | M |
| P3-10 | Frontend: commands, approvals, bell, extraction | P3-06, P3-08 | L |
| P3-11 | Phase 3 tests | all P3 | M |
| **Phase 4: Inbox** | | | |
| P4-01 | Social accounts (mock connect) | Phase 3 | S |
| P4-02 | Provider contract + mock messaging | P4-01 | M |
| P4-03 | Webhook ingestion | P4-02 | M |
| P4-04 | Inbound processing | P4-03 | M |
| P4-05 | Drafting (task, context, render, validate) | P4-04, P3-03 | L |
| P4-06 | Policy engine | P4-05 (inputs) | M |
| P4-07 | Reply drafts and approvals | P4-06, P3-04 | M |
| P4-08 | Operations ledger and send/reconcile | P4-07 | L |
| P4-09 | Human actions and approved answers | P4-08 | M |
| P4-10 | Simulator and dev tools | P4-03 | M |
| P4-11 | Frontend inbox | P4-09, P4-10 | L |
| P4-12 | `draft_reply` evals | P4-05 | M |
| P4-13 | Phase 4 tests and E2E | all P4 | M |
| **Phase 5: Content** | | | |
| P5-00 | Phase 4 follow-ups (one draft job per conversation, strictest-class reason, review button, staff approval state, reconnect and resume) | Phase 4 | M |
| P5-01 | Media storage and upload | Phase 4 | M |
| P5-02 | Content model and transitions | P5-01 | M |
| P5-03 | Generation and content commands | P5-02 | L |
| P5-04 | Submission and approval | P5-02 | M |
| P5-05 | Mock publishing | P4-02 | M |
| P5-06 | Publish executor and reconciliation | P5-04, P5-05 | L |
| P5-07 | Content impact handlers | P5-04, P3-07 | S |
| P5-08 | Frontend content | P5-06 | L |
| P5-09 | `draft_content` evals | P5-03 | S |
| P5-10 | Phase 5 tests and E2E | all P5 | M |
| **Phase 6: Reports and demo completion** | | | |
| P6-01 | Reporting | Phase 5 | L |
| P6-02 | Activity and failure command executors | P6-01 | S |
| P6-03 | Activity feed | Phase 5 | M |
| P6-04 | Notifications and Home dashboard | P6-01 | M |
| P6-05 | Integration failure UX (reauth, circuit, health) | Phase 5 | M |
| P6-06 | Members and invites | Phase 5 | M |
| P6-07 | Demo reset and history seed | P6-01 | M |
| P6-08 | Retention and cleanup jobs | Phase 5 | S |
| P6-09 | Full E2E, i18n, accessibility | all P6 | L |
| P6-10 | Local MVP DoD review | P6-09 | S |
| **Phase 7: Meta integration (gated)** | P7-00 … P7-10 | Gate 1 + Gate 2 | see phase doc |
| **Phase 8: Hardening (gated)** | P8-01 … P8-12 | Phase 7 | see phase doc |
| **Phase 9: Owner channel (gated)** | P9-01 … P9-05 | Phase 8 + OQ-01 | see phase doc |
