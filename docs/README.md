# AgentNest Documentation

AgentNest (working name) is an open-source core, with a possible hosted SaaS, that helps small businesses run Instagram operations. It maintains verified business knowledge, drafts and (when allowed) sends grounded replies to customer DMs, prepares and schedules content with explicit approvals, and reports honestly on what happened. It is Turkish-first, mobile-first, and fully demonstrable locally on simulated integrations.

This folder is the **primary engineering specification**. It is written in English for engineers and coding agents. The original product idea is preserved unchanged in [idea.md](idea.md). Where the two differ, these documents win, and [review/gap-analysis.md](review/gap-analysis.md) explains why.

## Reading order

| If you are… | Read |
|---|---|
| New to the project | [product/vision.md](product/vision.md) → [product/mvp-scope.md](product/mvp-scope.md) → [architecture/system-overview.md](architecture/system-overview.md) → [invariants.md](invariants.md) |
| Implementing a phase | [../CLAUDE.md](../CLAUDE.md) → [invariants.md](invariants.md) → [implementation/roadmap.md](implementation/roadmap.md) → the phase doc → the documents it lists under "Read first" |
| Reviewing a change | [invariants.md](invariants.md), the relevant ADR, [architecture/state-machines.md](architecture/state-machines.md), [implementation/task-breakdown.md §1](implementation/task-breakdown.md) (review checklist) |
| Running the demo | [operations/local-development.md](operations/local-development.md) |
| Working on Meta/WhatsApp/Telegram | [research/platform-capabilities.md](research/platform-capabilities.md) first |

## Map

```
docs/
├── README.md                     ← you are here
├── idea.md                       original specification (historical input, unchanged)
├── invariants.md                 non-negotiable engineering invariants (INV-01…20)
├── glossary.md                   one meaning per term; canonical code names
├── review/
│   ├── gap-analysis.md           audit findings on the original spec (G-01…31)
│   └── planning-review-summary.md final summary of the planning work
├── product/
│   ├── vision.md                 vision, principles, goals, non-goals, success metrics
│   ├── personas-and-use-cases.md personas, prioritised use cases, assumptions to validate
│   ├── requirements.md           FR/NFR with priority, phase and traceability to idea.md
│   ├── user-journeys.md          screens, journeys, edge cases, failure states, UX rules
│   ├── mvp-scope.md              stages, inclusions, exclusions, deferrals with triggers
│   └── acceptance-criteria.md    AC-A…G, AC-X, local MVP Definition of Done
├── architecture/
│   ├── system-overview.md        context, processes, stack, canonical flow
│   ├── component-design.md       modules, interfaces, dependency rules, transactions
│   ├── data-model.md             authoritative schema
│   ├── state-machines.md         all stateful entities and allowed transitions
│   ├── workflows.md              functional contracts A–G (incl. policy rules, metric definitions)
│   ├── api-design.md             conventions and endpoint groups
│   ├── agent-runtime.md          LLM tasks, command registry, bounds, injection containment
│   ├── business-knowledge.md     facts, sources, conflicts, rendering, claim validator
│   ├── integrations.md           Instagram, owner channels, LLM, storage contracts
│   ├── background-jobs.md        queue semantics, scheduler, job catalog, domain events
│   ├── security-and-privacy.md   threat model, permissions, KVKK/GDPR view, retention
│   ├── observability.md          IDs, logs, error catalog, audit catalog, health
│   ├── deployment.md             local and pilot production topology
│   └── decisions/                ADR-001 to ADR-022
├── implementation/
│   ├── roadmap.md                phases, gates, research track, working agreement, risks
│   ├── task-breakdown.md         task index and per-task protocol
│   ├── testing-strategy.md       test layers, failure matrix, AI evals, CI
│   ├── phases/                   phase-01 … phase-09
│   └── phase-summaries/          one review summary per finished phase
├── operations/
│   ├── local-development.md      setup, run, seed, simulate, inspect, reset, demo script
│   ├── environment-variables.md  every variable, defaults, secrets
│   └── troubleshooting.md
└── research/
    ├── platform-capabilities.md  verified/conditional/unverified platform facts with sources
    └── open-questions.md         open decisions with provisional defaults
```

## Document rules

1. **One source of truth per topic.** Other documents link to it rather than restate it: schema → data-model; states → state-machines; workflows → workflows; platform facts → platform-capabilities.
2. **Change contracts with code.** A change to schema, endpoints, states or job types updates the corresponding document in the same commit.
3. **Decisions go into ADRs.** New significant decisions get a new ADR. Accepted ADRs are superseded, not edited.
4. **Uncertainty is explicit.** Unknowns go into [research/open-questions.md](research/open-questions.md) with a provisional default. Unverified platform behaviour is never stated as fact.
5. **Terminology** follows [glossary.md](glossary.md).
