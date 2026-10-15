# MVP Scope

**Purpose:** Draw a hard line around what the first build includes, what pilot readiness adds, and what is deferred, and explain why. If a feature is not listed under "Included", it is out of scope for that stage.

## 1. Stages

| Stage | Phases | Outcome | External dependencies |
|---|---|---|---|
| **S1: Local MVP demo** | 1–6 | Complete, honest, simulated end-to-end product on a laptop. Satisfies the original spec §20 "Definition of Done for the First Build". | None (Docker for Postgres only) |
| **S2: Real Instagram** | 7 | One real professional account (founder's own, then 1–3 testers) connected, receiving DMs and publishing images. | Meta app, Standard Access, public HTTPS endpoint, S3-compatible storage |
| **S3: Pilot readiness** | 8 (+9 optional) | Deployed, backed up, secured. Legal basics in place. Optional owner messenger channel. | VPS, domain, legal review, (Telegram/WhatsApp) |
| **S4: Self-service SaaS** | not planned in detail | App Review approved, self-service signup, billing. | Meta Advanced Access, payment provider |

## 2. Included in S1 (local MVP demo)

The test for inclusion: **is it needed to demonstrate the core value loop credibly and safely?**

| Capability | Included scope | Explicitly excluded in S1 |
|---|---|---|
| Accounts & workspaces | Email/password login, workspaces, roles owner/manager/staff, workspace switcher, invite by link, tr/en UI | Email delivery, password reset UI (CLI only), SSO |
| Business knowledge | Typed facts from gym/Pilates templates, verification, version history, candidates with discrepancy/contest rules, readiness, paste-text extraction, approved answers, brand voice | Website URL fetch, Instagram profile import, structured class timetables, multiple branches |
| Commands | Web command bar. Closed registry: activity questions, pending approvals, content status, failure explanation, fact query, fact update, brand voice update, content draft request, cancel scheduled content. Clarification and confirmation. | Approve/publish/send by command (never), rescheduling by command, multi-step plans |
| Inbox | Mock account, simulated webhooks through the real ingestion path, conversations, debounce, grounded drafts, policy decisions, approvals, manual replies, takeover, messaging window, echo-based supersede (simulated), approved answers | Attachments analysis (images in DMs are shown as "attachment received" → human), story replies/mentions handling beyond "human_required", comments, Human Agent tag |
| Content | Image upload with validation, `feed_image` and `story_image`, AI content drafts with overlay text suggestions, claim validation, approve & schedule, mock publish worker with container semantics, retries with deadline, cancel, on-hold on fact change | Video, Reels, carousels, image generation, hashtags research, best-time suggestions |
| Approvals | Confirmation and authorisation kinds, binding, expiry, sweep, approvals screen | Multi-level approval chains |
| Reporting | Daily report (computed, templated), activity feed, notification centre, Home dashboard, integration health | Charts, exports, insights from Instagram |
| Simulation | Seed data, dev panel and CLI, failure injection, run-due-jobs, reset, simulation labelling | — |
| AI | `fake` provider (default) and `anthropic` provider, agent run records, eval datasets and runner | Fine-tuning, other providers, vision |
| Ops | Docker Compose Postgres, CI, structured logs | Deployment, backups (S3 stage) |

### Features judged essential to show the value (the demo must not skip them)
1. A customer price question answered with the **verified** price, after one tap of approval.
2. A price change by natural language that **changes the next answer** and **holds the scheduled post** that contained the old price.
3. A scheduled post that **publishes (simulated) at its time**, survives a worker restart, and does not duplicate on retry.
4. A complaint that is **not** answered automatically.
5. A daily report whose numbers **match the activity log**.
6. Everything visibly labelled **simulated**.

## 3. Added in S2–S3 (pilot readiness)

- Instagram Login OAuth, token encryption and refresh, real webhooks with signature verification, real send and publish (images), S3 media with signed URLs, capability detection, disconnect.
- Deployment to a single VPS (TLS, backups, restore drill), RLS defence in depth, login throttling, security review, retention and deletion jobs, Meta data deletion callback, privacy notice and DPA templates (legal review), SMTP for invites.
- Optional (OQ-01): Telegram owner channel.

## 4. Deferred (with reason and trigger)

| Feature | Reason for deferral | Revisit trigger |
|---|---|---|
| **Comment automation** ("fiyat?" → private reply) | Comment webhooks need **Advanced Access**. It adds a second inbound surface. | After App Review; OQ-07 interviews show high value |
| WhatsApp owner channel | Cost, verification, policy uncertainty | OQ-01 |
| Story/post **image generation** (template cards) | Not core to the trust loop; design effort | OQ-15 after pilots |
| Video/Reels/carousels | Transcoding and validation complexity | Pilot demand |
| Website and profile import | SSRF-safe fetching, scraping quality | Self-service onboarding stage |
| Human Agent tag (7-day replies) | Requires separate permission; human-only | Pilot demand for late replies |
| Billing, plans, usage limits | No paying users yet | Paid commitments (OQ-06) |
| Advanced analytics and Instagram insights | Not the core problem | Pilot demand |
| Multiple Instagram accounts per workspace, agencies | Complexity; not the target segment | Market evidence |
| CRM, lead pipeline, booking integrations | Scope explosion | Strong pilot demand |
| Multi-agent / autonomous campaigns | Contradicts the trust model at this stage | Proven trust + concrete use case |
| PWA install + Web Push | Depends on OQ-01 | After S1 demo |
| Additional reply languages (ru, de) | Tourism segment later | OQ-11 |

## 5. Scope guardrails for implementers

- Do not add a table, endpoint, job type or dependency that no phase document lists, without updating the docs first.
- Do not implement a deferred feature "because it is easy". Raise it instead.
- When in doubt between a simpler and a more general implementation, choose the simpler one and note the limitation in the phase summary.
