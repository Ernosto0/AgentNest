# Session 01: Contracts and architecture alignment

**Task:** P7.5-01. **Status:** Planned. **Prerequisite:** inspected Phase 7 baseline.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 1-7, 10 and 14.

## Goal

Make the requested account-agent architecture internally consistent and implementable before adding runtime behavior.

## Read first

`docs/architecture/decisions/ADR-007*`, `ADR-009*`, `ADR-014*`, `ADR-022*`, `ADR-024*`; `docs/architecture/{agent-runtime,component-design,data-model,state-machines,workflows,api-design,background-jobs,security-and-privacy}.md`; product vision/scope/requirements; platform capabilities and current Phase 7 report.

## Build

1. Verify current gates, migration head and OAuth changes. Record a baseline; no outdated historical blocker is carried forward without checking.
2. Finalize ADR-024 under the requested product direction. Supersede only affected decisions and update their status/index according to repository rules. Replace no-tool enforcement language in `CLAUDE.md` and INV-03/04/16 with typed broker/authority/evidence mechanisms; preserve their underlying guarantees and historical phase evidence.
3. Update product scope and requirements for natural conversation, memory/personality, owner questions, autonomous moderation and comment-to-DM. Define content-tool scope and the new action-level owner settings.
4. Formalize section 7's records, enums, APIs, jobs and transition tables in canonical architecture docs. Document domain-to-agent event ownership, short transactions and import contracts. Decide exact action/operation names and consistent customer/thread identifiers.
5. Define permissions, automatic/human authorization evidence, public/private visibility and retention. Record controller migration and revocation semantics. Specify account agent pause versus individual-thread takeover.
6. Open R75-01 through R75-06 in the platform research register with primary sources, dates and evidence status. Refresh accessible official documentation; record failures honestly. Identify provisional mock assumptions and any truly blocking ambiguity without guessing live behavior.

## Verify and done when

Review a normal DM, owner wait/resume, autonomous deletion, private reply and uncertain operation against the contracts. Each has a state, authorization path, event owner, deadline and recovery outcome. Check relative links and document consistency; no runtime tests are necessary for documentation-only changes. G7.5-A is satisfied when the accepted target and enforceable contracts agree; accepting the architecture does not certify implementation or platform behavior.

## Handoff

Write `s01-report.md` with the supersession map, permission/schema/job/API decisions, open research and exact migration baseline. Session 02 must not have to invent these contracts.
