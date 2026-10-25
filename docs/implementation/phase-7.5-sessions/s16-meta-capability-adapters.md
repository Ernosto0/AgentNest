# Session 16: Meta capability adapters

**Task:** P7.5-16. **Status:** Planned. **Prerequisite:** Session 15 and applicable R75 contract findings.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 3, 10.

## Goal

Implement the new capabilities behind the real Meta adapter with honest capability detection, typed errors and evidence-backed contracts.

## Read first

Current `platform-capabilities.md`, R75-01 through R75-06, Phase 7 live checklist and OAuth fixes; `app/integrations/instagram/{meta,oauth,error_mapping,webhook_format}.py`; `tests/contract/fixtures/meta/` and existing live harness.

## Build

1. Refresh current official comment/moderation/private-reply contracts and record exact source dates/status. Resolve endpoint/scopes/access/event/eligibility/error/readback questions before enabling corresponding real methods. A fetch failure is an open research item.
2. Implement provider methods, parser fields and pagination against supported contracts; extend actual-grant capability mapping and reconnect/scope expansion. Preserve account identity checks, token encryption, redirect/callback and disconnect fences.
3. Map transport/API failures per operation. A possible accepted reply/moderation effect is ambiguous; a missing result must not be classified as safely retryable. Support verified state reads where available and explicit unknown where not.
4. Add fixture-backed real adapter tests matching the stateful mock contract. Mark fixture origin/date/version: synthetic or authentic sanitized. Do not turn a hand-authored example into a recording.
5. Extend the opt-in manual harness for read/comment/public-reply/private-reply/moderation cases with specific test targets and no secret output. Harness construction is offline work; execute only with explicit live authorization. No destructive probe chooses arbitrary existing customer comments.

## Verify and done when

Run offline contracts for every implemented capability, grant loss, pagination, malformed success, rate limits, deadline expiry, target ownership and uncertain effects. Verify no token/credentials leak into errors/logs. If primary/live contracts remain unavailable, finish adapter scaffolding and disabled provisional synthetic paths, mark the capability externally pending, and let independent offline verification continue. Do not assert G7.5-D or AC75-23 passed.

## Handoff

Write `s16-report.md` with capability-by-capability implementation/research/evidence status, fixture provenance and exact remaining founder checks. Session 18 performs authorized end-to-end application acceptance rather than substituting direct adapter probes for it.
