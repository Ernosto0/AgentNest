# Product Vision

**Purpose:** What the product is, for whom, why, and what it deliberately is not. It is the stable "north star" for scope decisions. Requirements live in [requirements.md](requirements.md); scope lives in [mvp-scope.md](mvp-scope.md).

Working name: **AgentNest** (repository name; final product name is open, see OQ-10). Descriptive name: *Instagram Operations Agent*.

## 1. Vision

Small businesses run their Instagram from a phone, between customers. AgentNest learns verified facts about the business. Its Phase 7.5 account agent can hold natural DM and public-comment conversations, remember relevant customer context, ask the owner for missing information and perform supported actions within explicit account delegation. It helps prepare and schedule posts and tells the owner what actually happened. The earlier bounded draft and approval workflow remains available for accounts that have not switched controllers.

> **The business owner should not have to adapt to the software. The software should adapt to how the business owner works.** (from the original specification)

The value is **trust under delegation**. The owner hands over repetitive work only if the system never invents a price, never sends something unapproved, and never claims an action succeeded when it did not. Every design decision serves that trust.

## 2. Problem

Owners of local small businesses (cafés, boutiques, salons, studios, clinics, services):
- answer the same DM questions (price, hours, location, trial session) dozens of times a week, often late;
- lose leads because replies are slow or forgotten;
- post irregularly because content preparation competes with running the business;
- let prices and information drift: an old price in a pinned post, a different price on the website;
- have no simple view of what happened today.

Existing tools need dashboards, rule builders or technical setup, and are usually English-first.

## 3. Product principles (ranked; earlier wins on conflict)

1. **Never fabricate.** Business-critical values come only from verified facts ([invariants.md](../invariants.md) INV-02).
2. **Never act without the required permission.** Approvals are explicit, bound and expiring (INV-04, INV-16).
3. **Tell the truth about outcomes.** Scheduled ≠ published; simulated ≠ real (INV-05, INV-09, INV-18).
4. **Hide complexity, not control.** No MCP, API keys or workflow builders for owners; still, every automated action is inspectable and reversible where possible.
5. **Phone-first, Turkish-first.** Designed for a phone held in one hand, in Turkish; English shares the same codebase.
6. **Small and reliable beats large and impressive.** Few capabilities that work end to end, rather than many partial ones.
7. **Works without paid services in development.** The open-source core runs locally on mocks.

## 4. Goals

### Product goals (first 12 months)
- G1. A local demo that shows the full loop (facts → DM draft → approval → simulated send → fact change → content → scheduled simulated publish → honest daily report) without any external credentials.
- G2. Real Instagram connection for a handful of assisted pilot businesses in Bucak/Burdur (and possibly Antalya), first under Standard Access, then after App Review.
- G3. Owners of pilot businesses use it daily for DM replies and weekly for content, and at least some agree to pay.
- G4. A clear path to self-service onboarding for the global English experience.

### Engineering goals
- E1. All invariants enforced by mechanisms and tests, not conventions.
- E2. One-command local setup on Windows, macOS and Linux (Docker for Postgres plus uv plus npm).
- E3. Every phase is demoable and verifiable against explicit acceptance criteria.
- E4. Provider independence: LLM, Instagram, storage and owner channels behind interfaces with fakes.

## 5. Non-goals (for the MVP and pilots)

- Fully autonomous campaign optimization or publishing without an explicit, action-specific owner delegation.
- Instagram Ads, multi-platform publishing (Facebook, TikTok), agency-scale multi-account management.
- CRM (lead pipelines, customer profiles beyond the conversation), booking/appointment system integration.
- AI image or video generation.
- Complex analytics and insights dashboards.
- Subscription billing and self-service payments.
- Multi-agent teams or unbounded agent execution; Phase 7.5's single logical account agent has durable, bounded steps.
- Comment actions on arbitrary third-party posts; Phase 7.5 handles only evidenced capabilities on the connected business's media.
- Outbound messaging to customers who have not written first (prohibited by Instagram's model anyway).

## 6. Market structure: one codebase, two experiences

| | Türkiye experience (first) | Global experience (later) |
|---|---|---|
| Language | Turkish UI, commands and replies (English replies supported for tourists) | English |
| Onboarding | **Assisted**: the founder visits the business and sets it up together with the owner | Self-service, with extraction from pasted text and later the website/profile |
| Currency / formatting | TRY, `tr_TR` formatting | Per workspace |
| Owner channel | Web first; external messenger chosen from pilot evidence (OQ-01) | Web; messenger optional |
| Billing | Manual invoicing for pilots | Online subscription (deferred) |

Differences are expressed through **workspace configuration** (`market`, `default_locale`, `currency`, `timezone`, category templates), never through language checks in code ([ADR-016](../architecture/decisions/ADR-016-localization.md)).

## 7. Business model (summary)

Open-source core plus hosted SaaS ([ADR-019](../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md)). The paid offering sells managed hosting, the founder's Meta-reviewed app (self-hosters must obtain their own App Review), assisted onboarding, support, backups and monitoring, and higher limits. The license is undecided (OQ-02).

## 8. Validation plan and success metrics

These are **measurements to take**, not promises. Targets are set after a baseline exists.

| Metric | Definition | Source |
|---|---|---|
| Demo setup time | Minutes from first `git clone` to completing Scenario A | Timed by a tester following [local-development.md](../operations/local-development.md) |
| Pilot setup time | Minutes from arriving at the business to readiness `ready` | Founder's onboarding log |
| Draft acceptance rate | Approved-unchanged drafts ÷ all decided drafts | `reply_drafts`, `approvals` |
| Edit rate | Approved-after-edit ÷ decided drafts | `reply_drafts.source`, versions |
| Escalation correctness | Share of complaint, refund and discount messages that were escalated | Eval set + weekly manual sample |
| Grounding violations | Ungrounded critical values in **sent** messages. **Must be 0.** | Validator logs + manual sample |
| Median time to first reply | Inbound to reply sent, split by auto vs approved | `messages` |
| Duplicate side effects | Duplicate sends or publishes. **Must be 0.** | Simulator + operations ledger + manual checks |
| Publish success rate | Published ÷ attempted | `operations` |
| Daily active owners | Owners opening the app or acting on a notification per day | Sessions, approvals |
| Time saved (perceived) | Owner's estimate before vs after | Interview at week 2 and week 4 |
| Willingness to pay | Pilots agreeing to a paid plan | Founder's CRM notes |

Pilot programme (from the original spec): interview about **10–15 businesses**, identify several serious pilot candidates, and seek paid commitments before investing in advanced features.
