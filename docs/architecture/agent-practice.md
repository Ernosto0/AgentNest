# Isolated Account Agent practice

The owner's test chat chooses its proposal path before calling a model. A legacy controller
uses the existing bounded reply-drafting task. An Account Agent controller uses
`agent.practice.run_practice`, the production `account_agent_step` provider contract,
`agent.context.SYSTEM`, and the tool schemas exposed by the production default broker.
A paused Agent remains labelled as an Agent and produces a blocked result without a model call.

## Snapshot and authority

The preparation transaction captures the owner's isolated test history, current business
knowledge, dependency-validated approved answers, Agent personality, configuration/delegation
versions, full `dm.send` action rule, current grantor authority and reply-limit availability.
Facts use the production Agent's visibility predicate. No customer messages, customer memory,
private owner answers or live calendar contents are assembled into a practice conversation.

The snapshot tool adapter validates arguments against the production tool schema. Reply
proposals use `grounding.validate_template_reply`, the same pure exact-source, placeholder,
claim and byte-limit validator used by the live broker. Language must equal the server-selected
snapshot language. The existing pure delegation `decide` and topic-policy functions determine
whether a proposed reply would be automatic, approval-required or blocked. An `off` action or
an action restricted to owner-task sources cannot become an approval-required customer reply.

## Effect boundary

Practice never calls `ToolBroker.dispatch` or any live tool handler. Knowledge, answer and
thread reads are bounded snapshot reads. Memory reads are empty and memory writes acknowledge
simulation without persistence. Owner questions end with an explanation that owner input would
be needed; they create no question or notification.

Calendar requests end with an explicitly simulated, human-required result. They do not read
live availability, accept a production appointment as evidence, create an appointment or claim
that a booking succeeded. Tools unavailable on the production DM surface (including content
publication) remain unavailable in practice. These restrictions are shown in Turkish and English
instead of representing simulated operations as verified outcomes.

The only resulting application records are the isolated `assistant_test_turns` outcome and
model-call accounting in `agent_runs`. No Agent session/thread/action, approval, operation,
customer message/memory, calendar mutation, customer-report source or owner notification is
created. This boundary is enforced by dependency shape: the snapshot dispatcher receives no
database session or operation executor.

## Provider accounting and persistence

Practice calls use the existing `ai.step_runner` transaction boundary and daily model-call
reservation/repair accounting. They retain the existing allowed `AgentRun.task = account_agent_step`,
with `agent_step_id = null`, `prompt_version = practice_v1`, and a simulated test-turn reference
in the metadata-only input snapshot. This requires no new task CHECK value or migration.
The provider call runs after the reservation transaction has closed. Model input/output values
and tool arguments are not persisted into an extra run snapshot.

The loop is bounded by eight model calls including repairs, eight tool proposals, 120 seconds
between calls, the production request-size limits and existing per-call provider timeout. At
the last available model call a schema repair is not allowed to exceed that activation budget.
Practice remains subject to its existing workspace hourly/daily submission limits. It does not
consume the customer AI-reply quota.

Results retain the existing migrated decision vocabulary: `auto`, `approval_required`,
`human_required` and `blocked`. Before saving a sendable result, the apply transaction rechecks
Agent settings/delegation versions and verifies that the referenced business facts remain usable
at exactly the source versions used for the proposal. A changed fact produces a non-sendable
`FACT_CHANGED` outcome. Reset/gone/already-completed turns discard the result.

## Verification

`tests/integration/inbox/test_agent_practice.py` exercises the actual job on a migrated
PostgreSQL database with a scripted Agent provider. It proves the legacy generator is not
called, model calls run without an open transaction, canonical decisions commit successfully,
the production tool-validation observation reaches the next step, authority limits apply,
repairs count against the daily model budget, and customer/domain tables are unchanged.

Pure adapter regressions cover the five supported reply-language schemas, forged facts,
invented values, injection/escalation, explicit approval, source-restricted delegation and
simulated effect proposals. Real-model linguistic quality and real calendar outcomes are
separate live acceptance tasks; practice tests do not claim either.
