# Session 13 handoff: owner tasks and content tools

**Status:** In progress, interrupted at the user's request. This is a checkpoint, not Session 13 acceptance.

Sessions 11 and 12 were implemented, operator reviewed, and committed separately as
`25c80ec` (public replies/moderation) and `1604ce3` (comment-to-DM). Their reports
record offline evidence and remaining live capability gates. Session 13's partial
work is being committed separately at this checkpoint.

## Completed in this checkpoint

- Started from clean `main` at `1604ce3` after separate reviewed commits for Sessions 11 and 12.
- Added migration `0029` and `OwnerTask` persistence for account-scoped, requester-bound task intake.
- Added authenticated task POST/list/GET routes, request ID deduplication, owner-task agent events and wakes.
- Added owner-task prompt context and reconstruction of the requester's current membership at coordinator claim and broker dispatch. Customer inputs do not enter this intake route.

## Verification and limits

- `mypy app evals`: passed, 291 source files.
- Scoped Ruff check and format check passed after fixing initial import ordering and migration formatting; `git diff --check` passed. Database tests, migration upgrade, API/client generation, and affected regressions were **not** completed before interruption.
- Content read, prepare, schedule, publish and cancel tools are **not implemented**. The legacy content approval rule and publish executor were not changed. No agent content publication is authorized by this checkpoint.
- No live Meta actions, real-model evaluation, deployment, or Session 13 acceptance occurred.

## Continue Session 13

1. Run final scoped Ruff checks and migration-backed tests for task intake, idempotency, member revocation, foreign accounts, and route permissions. Regenerate OpenAPI/client types for the new routes.
2. Complete content tools over existing content services. Resolve ambiguous or missing media through clarification; keep selected assets and account targets exact.
3. Bind schedule/publish/cancel to action delegation, exact approval, content/media/fact versions and deadlines. Preserve manual content flows; recheck revocation at scheduled publish dispatch and reconcile ambiguous publish outcomes.
4. Run focused and affected regressions, update this report with actual evidence and acceptance IDs, then request operator review. Migration head is `0029`.
