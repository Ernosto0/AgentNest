# Requirements

**Purpose:** The numbered, testable functional (FR) and nonfunctional (NFR) requirements. Each one has a priority, the phase that delivers it, and a trace to the original specification ([idea.md](../idea.md) section numbers), so that no original requirement is silently dropped.
**Detailed behaviour** of the main workflows is specified in [workflows.md](../architecture/workflows.md). **Acceptance criteria** are in [acceptance-criteria.md](acceptance-criteria.md).

Priority: **M** = must for the local MVP demo, **P** = must before real pilots, **L** = later / deferred.
Phase numbers refer to [roadmap.md](../implementation/roadmap.md).

## 1. Functional requirements

### 1.1 Identity, workspaces, roles

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-001 | Users sign in with email and password. Sessions are server-side and revocable. Users can sign out. | M | 1 | §10.1 |
| FR-002 | A user can create a workspace with name, business category, market, default locale, timezone and currency. | M | 1 (basic), 2 (category templates) | §2, §4.1 |
| FR-003 | Memberships have roles `owner`, `manager`, `staff` with the permission matrix in [security-and-privacy.md §3](../architecture/security-and-privacy.md). | M | 1 | §10.1 |
| FR-004 | Owners invite members through a one-time link and remove members. Membership changes are audited. | M | 6 | §13.3 (assisted onboarding) |
| FR-005 | Users with several memberships switch workspaces. The current workspace is always visible. | M | 1 | §13.3 |
| FR-006 | Users switch UI language between Turkish and English. The default comes from the browser, then the workspace. | M | 1 | §2 |

### 1.2 Business knowledge

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-010 | Category templates (gym, Pilates studio) define expected facts, types, criticality and readiness requirements. | M | 2 | §4.1 profile fields |
| FR-011 | Members with permission create, edit and archive typed facts: money, weekly hours, text, phone, address, URL, boolean, enum. Promotions have an optional validity window. | M | 2 | §4.1, §4.2 |
| FR-012 | Facts have status `unverified` / `verified` / `archived`. Only members with `knowledge.verify` can verify. Editing by such a member verifies the new value. | M | 2 | §4.1 principle |
| FR-013 | Every change creates an immutable version with value, source, actor, reason and time. Users can view the history. | M | 2 | §4.2 |
| FR-014 | Values from non-authoritative sources become **fact candidates**. Discrepancy and contest rules apply ([business-knowledge.md §5](../architecture/business-knowledge.md)). Users accept or reject candidates. | M | 2 | §4.2 conflict handling |
| FR-015 | Readiness (`not_ready`, `ready_for_drafts`, `ready`) is computed and shown as a checklist with missing items. | M | 2 | §4.1, §15 A |
| FR-016 | The owner can paste text (bio, price list, FAQ). The system extracts fact candidates with source excerpts. | M | 3 | §4.1 extraction |
| FR-017 | When a fact changes, the system identifies affected pending reply drafts, approved answers and content. Scheduled content goes `on_hold`. The owner is notified. Published content and sent messages are untouched. | M | 3 (framework), 4 (drafts, answers), 5 (content) | §4.2 steps 6–8 |
| FR-018 | Owners and managers maintain **approved answers** (reusable replies) with linked facts, optionally created from a sent reply. | M | 4 | §4.3 human handoff |
| FR-019 | Brand voice guidelines and escalation keywords are maintained as workspace knowledge. | M | 2 (storage), 4 (used) | §4.1 fields, §4.6 "friendlier" |
| FR-020 | Import facts from the Instagram profile. Website URL extraction uses an SSRF-safe fetcher. | L | after 7 | §4.1 |

### 1.3 Natural-language commands

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-030 | A command input is available on Home (web) and accepts Turkish and English. | M | 3 | §4.6, §12.2 |
| FR-031 | Commands are interpreted into the closed registry of command types ([agent-runtime.md §3](../architecture/agent-runtime.md)). Anything else → `unsupported` with suggestions. | M | 3 | §4.6 |
| FR-032 | Ambiguous references ("tomorrow's post") produce a clarification with explicit choices. | M | 3 (framework), 5 (content refs) | §4.6 step 2 |
| FR-033 | Every command that changes facts, settings or scheduled content requires a **confirmation** showing the exact effect (e.g., "6.000 ₺ → 7.000 ₺"). Creating a draft does not, because drafts still need approval before publication. | M | 3 | §4.2 step 3, §4.6 step 5 |
| FR-034 | Read-only questions about activity, pending approvals, content status and failures are answered from records. | M | 3 (basic), 6 (full) | §4.6 examples, §4.8 |
| FR-035 | Commands can never approve, publish or send. Approval only via explicit approval actions. | M | 3 | §4.7 approval security |

### 1.4 Instagram inbox

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-040 | Message webhooks are signature-verified, stored raw, deduplicated, acknowledged immediately and processed asynchronously. | M | 4 | §4.3 steps 1–3, §10.3 |
| FR-041 | Conversations and messages are stored. The inbox lists conversations with attention filters: needs reply, needs approval, escalated, all. | M | 4 | §12.3 |
| FR-042 | Message bursts are debounced into one draft. New inbound messages supersede pending drafts. | M | 4 | §4.3 |
| FR-043 | Drafts are generated in the customer's language from **usable** facts, approved answers and brand voice, using placeholders and the claim validator. | M | 4 | §4.3 step 4–7 |
| FR-044 | A deterministic policy decision (`auto`, `approval_required`, `human_required`, `blocked`) with reason codes is recorded per draft. | M | 4 | §4.3 step 6–8, §5 |
| FR-045 | Complaints, refunds, discount or exception requests, sensitive topics, missing or contested facts, unsupported language and ambiguity are routed to a human. | M | 4 | §4.3 human handoff, §5.3 |
| FR-046 | Users approve, edit-and-approve, or reject drafts, and write manual replies. | M | 4 | §4.3 |
| FR-047 | Replies are sent through the operations ledger. The status (`queued`, `sending`, `sent`, `failed`, `checking`) is visible. | M | 4 | §4.3 step 9–10 |
| FR-048 | The 24-hour messaging window is enforced and the remaining time is displayed. Expired drafts are explained. | M | 4 | §4.3 restriction |
| FR-049 | Users take over a conversation (automation stops) and release it. | M | 4 | §12.3 |
| FR-050 | Owners configure automation per action class (`auto` / `approval` / `off`). Default is `approval`. `auto` requires readiness `ready`. | M | 4 | §5, §12.7 |
| FR-051 | Replies typed by the owner in the native Instagram app are detected (echo) and supersede drafts. | M (mock), P (real, V-02) | 4, 7 | §4.3 |
| FR-052 | An optional automation disclosure suffix is applied to auto-sent replies (on by default). | M | 4 | OQ-13 |

### 1.5 Content and publishing

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-060 | Users upload images. Validation (type sniffing, size, dimensions), PNG→JPEG conversion and EXIF stripping are applied. | M | 5 | §4.4 media input |
| FR-061 | Content items of type `feed_image` and `story_image`. A story has suggested overlay text and no caption. | M | 5 | §4.4, §4.5 |
| FR-062 | Content drafts are generated from an objective ("deneme dersi için story") using usable facts and brand voice. | M | 5 | §4.4 workflow |
| FR-063 | Content is validated with the claim validator. Problems are shown inline before submission. | M | 5 | §4.4 step 4 |
| FR-064 | Content is submitted for approval with an exact schedule (workspace timezone) or "publish now". Self-approval is a single explicit action for permitted users. | M | 5 | §4.5 |
| FR-065 | A deterministic publish job runs at the scheduled time and re-checks approval, version and account. It uses the container flow and reconciles before any retry. Retries are bounded by a deadline. There are no duplicates. | M | 5 | §4.5 |
| FR-066 | Users cancel scheduled content. Scheduled content affected by fact changes moves to `on_hold`. | M | 5 | §4.2, §4.5 |
| FR-067 | Content cards show distinct states. Failures show cause and next step. | M | 5 | §12.4 |
| FR-068 | The publishing quota is checked before publishing (50 per 24 h, plus the provider quota endpoint). | M | 5 | §11 rate limits |
| FR-069 | Video and Reels publishing, carousels. | L | after 7 | §4.4 |

### 1.6 Approvals

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-070 | An approvals list and detail show exactly what will happen: text, media, account, schedule and the facts used. | M | 3 (confirmations), 4–5 | §12.6 |
| FR-071 | Approvals are bound to subject version + payload hash, single-use, expiring, and permission-checked ([ADR-014](../architecture/decisions/ADR-014-approval-and-policy-model.md)). | M | 3 | §4.7 approval security |
| FR-072 | Expired approvals are swept and subjects updated. The requester is notified. | M | 3 | §4.7 |

### 1.7 Reports, activity, notifications, home

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-080 | The daily report is computed from records with documented metric definitions in the workspace timezone. The summary is templated, and simulated data is labelled. | M | 6 | §4.8 |
| FR-081 | The activity view lists audited events in owner language, filterable by type, linking to subjects. | M | 6 (audit written from 1) | §4.8 activity log |
| FR-082 | The notification centre shows approvals requested, escalations, failures, reauth needed, report ready, and discrepancies. | M | 3 (basic), 6 | §4.7 |
| FR-083 | The Home dashboard shows connection status, attention items, approvals, upcoming posts, recent failures and the command input. | M | 6 (incremental from 3) | §12.2 |
| FR-084 | Integration health: account status, recent failures, recovery actions. | M | 6 | §10.3, §12.7 |

### 1.8 Integrations and channels

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-090 | A mock Instagram account can be connected to demo workspaces. The stateful simulator follows the same contract as the real API. | M | 4 | §11 development strategy |
| FR-091 | Failure injection for the simulator: transient, rate limit, auth revoked, outcome unknown, invalid media. | M | 5–6 | §15 F |
| FR-092 | Connect a real Instagram professional account via Instagram Login OAuth. | P | 7 | §4.1, §11 |
| FR-093 | Tokens are encrypted at rest, refreshed automatically, and moved to `needs_reauth` on failure. | P | 7 | §10.2 |
| FR-094 | Real webhooks, sending and publishing (feed and story images) through the Meta adapter. | P | 7 | §11 |
| FR-095 | Disconnect an account: revoke and delete tokens, stop processing. Data deletion follows retention rules. | P | 7–8 | §10.6 |
| FR-096 | Meta data deletion callback endpoint with a status URL. | P | 8 | §10.6 |
| FR-097 | An owner messaging channel (Telegram provisional) for notifications, commands, media and approvals, through the channel abstraction. | P | 9 | §4.7 |
| FR-098 | LLM providers `fake` (default) and `openai` behind one interface. | M | 3 | §7.1 AI |
| FR-099 | WhatsApp owner channel. | L | after OQ-01 | §4.7 |

### 1.9 Demo and simulation

| ID | Requirement | Pri | Phase | Trace |
|---|---|---|---|---|
| FR-100 | Seed command creates demo workspaces (Turkish gym, English Pilates studio) with fictional facts, users and a mock account. | M | 2, 4, 6 | §14, §15 |
| FR-101 | Simulator (dev UI panel + CLI): send scripted or custom customer messages, inject failures, run due jobs now. | M | 4–6 | §15 |
| FR-102 | Reset a demo workspace to its seed state. | M | 6 | §15 |
| FR-103 | All simulated records and screens are visibly labelled "Simulated". | M | 4+ | §11, §15 |

## 2. Nonfunctional requirements

| ID | Requirement | Measurement | Phase | Trace |
|---|---|---|---|---|
| NFR-01 | **Mobile-first:** all MVP flows complete at 360×740 without horizontal scrolling. Touch targets ≥ 44 px. Primary actions are reachable one-handed. | Playwright at 390×844 and 360×740; manual check on a real Android and iPhone | 1+ | §12 |
| NFR-02 | **Localisation:** 100 % of UI strings in `tr` and `en`. Locale-correct formatting. No hard-coded language checks. | i18n key-parity lint; grep rule | 1+ | §2 |
| NFR-03 | **Security:** invariants INV-01, 03, 04, 10, 16, 20 hold. OWASP ASVS L1 basics for auth and session. | Isolation suite, security tests, Phase 8 review | 1+ | §10 |
| NFR-04 | **Responsiveness (development budgets, not SLAs):** with seed data on a dev laptop, API reads p95 < 300 ms. Webhook acknowledgement < 500 ms. Fake-LLM command round trip < 3 s. | pytest timing test on seed data; Playwright timing for command round trip | 3–6 | — |
| NFR-05 | **Reliability:** restart survival (INV-07), idempotency (INV-06), bounded retries with deadlines. | Crash/restart tests, duplicate-delivery tests | 1, 4, 5 | §10.4 |
| NFR-06 | **Observability:** correlation IDs across HTTP, jobs, runs and operations. Error codes catalogued. Every async resource has a visible status. | Tests assert IDs present; catalog lint | 1+ | §4.8, §17 |
| NFR-07 | **Accessibility:** WCAG 2.1 AA basics: contrast, labels, focus states, no colour-only status. | axe checks in Playwright | 1+ | — |
| NFR-08 | **Privacy:** data minimisation (no usernames or IDs in LLM prompts), retention jobs, export and deletion paths. | Tests for prompt builders; retention job tests | 3, 8 | §10.6 |
| NFR-09 | **Portability:** development on Windows, macOS and Linux. Docker only for Postgres. | Setup docs tested on Windows (founder machine) | 1 | §7.1 |
| NFR-10 | **Cost:** the local demo needs no paid service. A pilot deployment fits a single small VPS + managed or self-run Postgres + S3-compatible storage. | Deployment doc; monthly bill | 1, 8 | §13 |
| NFR-11 | **Maintainability:** CI runs lint, format check, type check, unit, integration, isolation and E2E (fake providers). Every state transition has a test. | CI | 1+ | §17 |
| NFR-12 | **Browser support:** current Chrome (Android/desktop), Safari iOS 16.4+, Firefox, Edge. | Playwright projects (Chromium, WebKit) | 1+ | §12 |
| NFR-13 | **Testability:** an injectable clock, deterministic fake LLM, and simulator with failure injection. | Used by test suites | 1, 3, 4 | §17 |
| NFR-14 | **AI quality:** eval suites per LLM task with hard assertions (zero ungrounded values passing validation; all complaints escalated in the dataset) and tracked baselines. | Eval reports | 3+ | §17, §18 |

## 3. Original specification items not adopted as specified

These are deliberate changes, not omissions. Rationale in [gap-analysis.md](../review/gap-analysis.md).

| Original | Status |
|---|---|
| §7.1 Redis + Celery | Replaced by PostgreSQL job queue ([ADR-006](../architecture/decisions/ADR-006-postgres-job-queue.md)) |
| §6 eight components as agents | Four bounded LLM tasks + deterministic services ([ADR-007](../architecture/decisions/ADR-007-deterministic-workflows-bounded-llm-tasks.md)) |
| §9 `scheduled_jobs` table | Split into domain status + `jobs` + `operations` |
| §9 `business_fact_versions(previous_value, new_value)` | Full snapshots in `fact_versions` + `fact_candidates` |
| §4.4 "Story copy" as caption | Overlay text suggestion; text must be in the image |
| §4.1 website extraction in onboarding | Pasted text in MVP; URL fetch later (FR-020) |
| §13.1 Apache-2.0 candidate | Undecided (OQ-02) |
| §4.4 "send image via messaging channel and schedule" | Phase 9 / later (UC-25) |

## 4. Section coverage map of the original specification

Every section of [idea.md](../idea.md) and where it now lives. "Kept" means adopted with at most clarification; "Changed" means deliberately revised (see §3 and the gap analysis).

| idea.md section | Status | Now specified in |
|---|---|---|
| §1 Product vision, problem, solution | Kept | [vision.md](vision.md) |
| §2 Türkiye / global experiences | Kept, made concrete | [vision.md §6](vision.md), [ADR-016](../architecture/decisions/ADR-016-localization.md) |
| §3 Target users, segments | Kept, as hypotheses | [personas-and-use-cases.md](personas-and-use-cases.md) |
| §4.1 Onboarding | Kept; website extraction deferred | FR-002, FR-010–016, FR-020; [workflows.md §A](../architecture/workflows.md) |
| §4.2 Business knowledge, update workflow, conflicts | Kept; strengthened (candidates, contest/discrepancy, on-hold) | [business-knowledge.md](../architecture/business-knowledge.md), [workflows.md §B](../architecture/workflows.md) |
| §4.3 DM automation, intents, handoff, restriction | Kept; window and policy made explicit | FR-040–052; [workflows.md §C](../architecture/workflows.md) |
| §4.4 Content creation, media input | Kept; Story text in image; media via messenger in Phase 9 | FR-060–063, FR-097; [agent-runtime.md §5](../architecture/agent-runtime.md) |
| §4.5 Scheduling and publishing lifecycle | Kept; states refined and mapped | FR-064–068; [state-machines.md §5](../architecture/state-machines.md) |
| §4.6 Natural-language commands | Kept; closed registry | FR-030–035; [agent-runtime.md §3](../architecture/agent-runtime.md) |
| §4.7 Messaging control, channels, approval security | Kept; web first, channel gated by OQ-01 | FR-097, FR-099; [ADR-012](../architecture/decisions/ADR-012-owner-channel-abstraction.md) |
| §4.8 Reports and activity | Kept; metrics defined precisely | FR-080–084; [workflows.md §F](../architecture/workflows.md) |
| §5 Approval and autonomy model | Kept; deterministic policy + bound approvals | [ADR-014](../architecture/decisions/ADR-014-approval-and-policy-model.md) |
| §6 Agent architecture | Changed (four bounded tasks) | [ADR-007](../architecture/decisions/ADR-007-deterministic-workflows-bounded-llm-tasks.md) |
| §7 Technical stack | Kept, except Redis/Celery | [system-overview.md §3](../architecture/system-overview.md) |
| §8 System architecture flow | Kept, mapped to components | [system-overview.md §4, §6](../architecture/system-overview.md) |
| §9 Database model | Changed (revised schema) | [data-model.md](../architecture/data-model.md) |
| §10 Security and reliability | Kept; threat model added | [security-and-privacy.md](../architecture/security-and-privacy.md), [ADR-011](../architecture/decisions/ADR-011-external-operations-ledger.md) |
| §11 Meta integration strategy | Kept; verified against docs | [platform-capabilities.md](../research/platform-capabilities.md), [integrations.md §3](../architecture/integrations.md) |
| §12 User interface | Kept; detailed | [user-journeys.md](user-journeys.md) |
| §13 Open source and SaaS | Kept; license left open | [ADR-019](../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md), OQ-02 |
| §14 MVP scope, deferred list | Kept; staged | [mvp-scope.md](mvp-scope.md) |
| §15 Demo scenarios A–F | Kept; G added | [acceptance-criteria.md](acceptance-criteria.md), [local-development.md §6](../operations/local-development.md) |
| §16 Development phases | Changed (9 phases + research track + gates) | [roadmap.md](../implementation/roadmap.md) |
| §17 Testing and quality criteria | Kept; expanded | [testing-strategy.md](../implementation/testing-strategy.md) |
| §18 Success metrics | Kept; mapped to data sources | [vision.md §8](vision.md) |
| §19 Implementation principles | Kept | [invariants.md](../invariants.md), [CLAUDE.md](../../CLAUDE.md) |
| §20 Definition of done for first build | Kept; extended | [acceptance-criteria.md](acceptance-criteria.md) (DoD) |
