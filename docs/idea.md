# Instagram Operations Agent
## Product Specification and Technical Architecture

**Status:** Initial MVP specification  
**Project type:** Open-source core with a hosted SaaS offering  
**Primary platform:** Instagram  
**Primary users:** Small businesses, local businesses, and small teams  
**Initial market:** Türkiye  
**Future market:** Global, English-speaking customers  
**Primary goal:** Build a working application that demonstrates how autonomous agents can manage routine Instagram operations with minimal setup and human intervention.

---

# 1. Product Vision

Instagram Operations Agent is an AI-powered system that helps businesses manage their Instagram operations without requiring the business owner to learn a complicated dashboard, configure AI workflows, or understand agent infrastructure.

The system connects to a business's Instagram Professional account, learns verified information about the business, handles routine customer messages, helps create and schedule content, and reports important activity to the business owner.

The user should interact with the system using natural language and a simple mobile-first interface.

The central product principle is:

**The business owner should not have to adapt to the software. The software should adapt to how the business owner works.**

## 1.1 The problem

Small businesses often manage Instagram through their phones. Their daily work includes:

- Answering repetitive questions about prices, opening hours, services, and availability.
- Responding to customer inquiries and identifying potential customers.
- Preparing posts, captions, and Stories.
- Remembering content schedules.
- Keeping prices and business information consistent.
- Monitoring messages and interactions.
- Understanding what happened during the day.

Existing tools may require users to learn dashboards, configure automation rules, connect multiple services, or understand technical concepts.

The product aims to hide this complexity behind a straightforward, business-aware interface.

## 1.2 The proposed solution

The application provides a single operational system with five core capabilities:

1. **Business knowledge:** Understands the business using verified facts and approved information.
2. **Instagram inbox automation:** Answers routine questions and escalates uncertain situations.
3. **Content operations:** Creates, reviews, schedules, and publishes supported content.
4. **Natural-language control:** Lets users give instructions without navigating complex settings.
5. **Monitoring and reporting:** Tracks actions, errors, approvals, and daily activity.

These capabilities should work together rather than behaving like unrelated AI tools.

For example, if a business changes its monthly membership price, the system should update its structured business knowledge, use the new price in future replies, and flag pending content that still contains the old price.

---

# 2. Product Structure

The product should have one shared codebase and two localized experiences.

## 2.1 Türkiye experience

- Turkish interface and natural-language commands.
- Turkish business onboarding.
- Pricing and billing in Turkish lira where supported.
- Optional assisted setup for less technical customers.
- Local customer support.
- Messaging-based commands and notifications where available.
- Business-specific templates and examples.

The initial acquisition strategy is to visit businesses in Bucak, Burdur, and potentially Antalya, help them connect their accounts, and observe how they use the product.

## 2.2 Global experience

- English interface and natural-language commands.
- Self-service onboarding.
- Online account connection and subscription management.
- Automated extraction of business information, followed by user verification.
- Documentation and onboarding guides.
- Usage-based limits appropriate for the subscription.

These are two product experiences, not separate applications. Shared features, agents, database models, and integrations should remain in the same codebase.

Localization must not be implemented as scattered hardcoded language checks. Use translation files, locale settings, currency configuration, and market-specific onboarding.

---

# 3. Target Users and Initial Scope

## 3.1 Target customer segments (ADR-023)

Any small local business communicating with customers on Instagram is a target customer. Common segments include:

- Cafés, restaurants and bakeries (menus, table reservations, daily specials)
- Beauty, hair and wellness salons (appointments, services, price lists)
- Retail shops and boutiques (opening hours, stock/delivery inquiries, pricing)
- Fitness studios, Pilates and gyms (membership prices, schedules, trial sessions)
- Health clinics, dietitians and therapies (consultation booking, service info)
- Service businesses, hotels, workshops and tutors

The platform provides a business-agnostic core with optional category presets (ADR-023).

Typical use cases include:

- Membership price questions.
- Class schedules and opening hours.
- Trial-session inquiries.
- Location and contact information.
- Promotional campaign content.
- Customer lead collection.

Beauty salons are a possible second segment. Boutique hotels and tourism businesses around Antalya may be explored later, after multilingual support and more complex operational workflows have been validated.

These segments are initial hypotheses. Customer interviews and real usage should determine whether they are worth pursuing.

## 3.2 Primary user

The initial user is a business owner or manager who:

- Uses Instagram regularly.
- Receives repetitive customer messages.
- Has limited time for social media operations.
- Prefers using a phone rather than learning a new software platform.
- Wants automation but needs control over important decisions.

The interface should remain understandable to a nontechnical user.

---

# 4. Core Product Features

## 4.1 Business onboarding

The user creates a workspace and connects an Instagram Professional account through the supported Meta authorization flow.

The application then gathers available business context from permitted sources, such as:

- Instagram profile information.
- Publicly available or user-provided business information.
- Website content, when the user supplies a website.
- Existing content and captions, where access permits.
- Information explicitly entered by the business owner.

The system generates a proposed business profile and asks the user to verify important details.

### Business profile fields

- Business name and description.
- Business category.
- Address and contact details.
- Opening hours.
- Products and services.
- Prices and pricing conditions.
- Frequently asked questions.
- Booking or appointment instructions.
- Promotions and campaign details.
- Brand voice and preferred tone.
- Escalation rules.
- Approved responses and restrictions.

### Onboarding principle

The user should not have to fill out a long questionnaire before seeing value.

Extract what can be extracted, show the proposed facts, and ask only for missing or uncertain information that materially affects automation.

The application must distinguish between verified facts, unverified suggestions, and missing information. It must not invent prices, opening hours, or business policies.

---

## 4.2 Business knowledge and memory

Business knowledge is a core component, not merely a text prompt attached to an AI model.

The system should store important facts as structured records.

Example:

- Fact: Monthly membership price.
- Value: 7,000 TRY.
- Source: Business owner.
- Verification status: Confirmed.
- Last updated: Timestamp.
- Previous value: 6,000 TRY.
- Version: Incremented when updated.

The exact schema can evolve, but critical facts must be queryable and auditable.

### Knowledge update workflow

When the owner says:

"Our monthly membership price is now 7,000 instead of 6,000."

The system should:

1. Interpret the instruction.
2. Identify the affected business fact.
3. Present a confirmation if the update is ambiguous or high impact.
4. Save the new value and retain the previous version.
5. Make the new value available to future agent executions.
6. Identify pending drafts and scheduled content that may contain the old price.
7. Notify the owner about affected content.
8. Record the change in the audit log.

The system should not silently rewrite already-published posts. It should also avoid changing historical conversation records.

### Conflict handling

If the website says 6,000 TRY while the owner confirms 7,000 TRY, the system should apply the defined source-priority policy, preserve the conflicting information for review, and avoid using an unresolved value in a customer response.

The business owner remains the authoritative source for business-specific decisions.

---

## 4.3 Instagram DM automation

The system receives supported Instagram messaging events and determines how each message should be handled.

### Message processing pipeline

1. Receive the event through the Meta integration.
2. Validate the event and identify the account and conversation.
3. Deduplicate the event to prevent duplicate processing.
4. Load relevant conversation history and verified business facts.
5. Classify the intent.
6. Determine whether the request is safe to answer automatically.
7. Generate a response grounded in available facts.
8. Apply policy checks and confidence thresholds.
9. Send the reply when authorized, or route the conversation for human review.
10. Store the result and report failures when necessary.

### Initial supported intents

- Price inquiries.
- Opening hours.
- Location and contact details.
- Services and product information.
- Booking instructions.
- Promotions and frequently asked questions.
- General inquiries requiring an approved response.

### Human handoff

The system should request human intervention when:

- A message is ambiguous.
- Required business information is missing.
- The customer makes a complaint.
- A refund, exception, or special discount is requested.
- The answer involves a sensitive or high-impact decision.
- Business facts conflict.
- The system cannot confidently determine an appropriate response.

The owner should be able to review the conversation, write a response, and optionally mark a response as a reusable approved answer.

### Important restriction

The system must respect Meta's current Instagram API capabilities, messaging policies, permissions, and response windows. It must not assume that an arbitrary Instagram account can send unrestricted outbound messages.

---

## 4.4 Content creation

The system helps the business prepare Instagram content using verified business information and the requested campaign objective.

### Content types

- Post captions.
- Reels captions and supporting text.
- Story copy and creative concepts.
- Promotional announcements.
- Educational content.
- Frequently asked question content.
- Campaign-specific content.

Actual media generation and publishing depend on the selected integrations and the supported Meta API formats.

### Content creation workflow

1. The owner describes the objective in natural language.
2. The system identifies the audience, message, format, and relevant business facts.
3. The agent proposes the content.
4. The application checks prices, dates, claims, and other critical facts.
5. The owner reviews or approves the draft when required.
6. The content is scheduled or published through a supported integration.
7. The system records the result and any errors.

Example:

"Prepare a Story campaign for our new membership offer."

The agent should generate a proposed Story concept and copy, use the verified price, and ask for approval before publishing if the campaign introduces a new commercial claim.

### Media input

The owner should eventually be able to send an image or video through a supported messaging channel and say:

"Schedule this Story for 19:00."

The system should validate the media format, account capabilities, and requested publication time. It should then show a clear confirmation of the exact content and schedule.

Do not promise that every Story format or publishing action is supported until the relevant Meta API capability has been verified.

---

## 4.5 Content scheduling and publishing

The publishing subsystem should be reliable and deterministic.

It should not depend on an AI model remaining active until the scheduled time.

A scheduled content record should include:

- Workspace and Instagram account.
- Content type.
- Caption and media references.
- Scheduled time and timezone.
- Approval status.
- Publishing status.
- Retry count.
- External publication identifier, when available.
- Last error and timestamps.

### Publishing lifecycle

Draft → Pending Approval, if required → Approved → Scheduled → Publishing → Published.

Failure paths should include:

- Validation Failed.
- Approval Rejected.
- Publishing Failed.
- Retry Scheduled.
- Cancelled.

The worker should validate that the content is still approved before publication. Retries must not create duplicate posts.

The user must receive an accurate result. A scheduled post is not the same as a successfully published post.

---

## 4.6 Natural-language command interface

The user should be able to manage common operations without learning the internal architecture.

Examples:

- "How many DMs did we receive today?"
- "Prepare a summary of today's conversations."
- "Our monthly price has changed to 7,000 TRY."
- "Make our replies a little friendlier."
- "Prepare a Story for our new campaign."
- "Show me content waiting for approval."
- "Cancel tomorrow's scheduled post."
- "Why did yesterday's post fail?"

### Command processing

The system should:

1. Identify the user's workspace and permissions.
2. Parse the requested action and its parameters.
3. Retrieve the necessary business facts.
4. Determine whether the action is read-only or changes external state.
5. Request confirmation when necessary.
6. Execute the operation through a typed tool or service.
7. Verify the outcome.
8. Return a concise result and record the operation.

The language model interprets intent. It should not directly manipulate the database or independently claim that an external action succeeded.

Use typed command schemas and explicit permissions for operations.

---

## 4.7 Messaging-based control and notifications

Messaging-based control is a key product differentiator, but the core application must not depend on a single messaging provider.

### Planned interactions

The owner can eventually:

- Request reports.
- Update business facts.
- Submit media.
- Request content drafts.
- Approve or reject proposed actions.
- Receive warnings about failures.
- Receive notifications when human attention is required.

### Channel strategy

**Mobile-first web application:** The primary interface for the initial prototype. It should work well on a phone and remain usable on desktop.

**Telegram:** A possible early messaging integration because it supports bot messages, file handling, and interactive buttons.

**WhatsApp:** A desired channel for the Turkish market, subject to the available official integration, applicable business messaging policies, permissions, and cost.

The architecture should support adding channels independently. The business logic must not be embedded directly in Telegram or WhatsApp handlers.

### Approval security

An approval should be tied to a specific operation, user, workspace, and expiration time. The system must not treat a vague message such as "okay" as permission to execute an unrelated pending action.

---

## 4.8 Reports and activity monitoring

The owner should be able to understand what the system did without inspecting technical logs.

### Initial reports

- Incoming message count.
- Number of automated replies.
- Conversations requiring review.
- Unanswered conversations.
- Scheduled content.
- Successful and failed publications.
- Recent knowledge changes.
- Important agent errors.

Example report format:

"Today, 42 conversations were processed. Seven require your review. Two scheduled posts are waiting for approval."

All numbers must come from actual stored events. The application must never fabricate operational metrics.

### Activity log

Each significant operation should record:

- Operation type.
- Workspace and account.
- Triggering user or agent.
- Relevant input and output references.
- Start and completion timestamps.
- Approval details, where applicable.
- Execution status.
- Error details, if any.

Avoid storing unnecessary personal information or exposing sensitive customer messages in routine logs.

---

# 5. Approval and Autonomy Model

The application should not be fully autonomous by default. Autonomy should be configurable by action type.

## 5.1 Automatic actions

Possible examples after validation:

- Answering routine questions using verified facts.
- Generating daily reports.
- Processing approved content schedules.
- Classifying incoming conversations.
- Updating internal operational status.

## 5.2 Approval-required actions

Examples:

- Publishing a new promotional campaign.
- Announcing a new price.
- Publishing content with a new commercial claim.
- Changing important business policies.
- Sending a message with uncertain implications.

## 5.3 Human-handled actions

Examples:

- Serious complaints.
- Refund requests.
- Sensitive customer issues.
- Conflicting or missing business facts.
- Requests outside the account's authorized capabilities.

The approval model should be explicit and configurable. Do not let the model bypass it by generating a different tool call.

---

# 6. Agent Architecture

The system should use a small set of clearly defined components rather than creating many independent agents without a concrete need.

## 6.1 Command Router

Receives user instructions and classifies them into supported operations.

Examples:

- Query today's activity.
- Update business knowledge.
- Create content.
- Schedule publication.
- Review pending approvals.

It produces a validated command rather than executing arbitrary code.

## 6.2 Business Knowledge Service

Retrieves and updates structured business facts, tracks versions, detects conflicts, and provides relevant context to other components.

## 6.3 Conversation Agent

Classifies customer messages, retrieves relevant facts, drafts responses, and determines whether the message requires escalation.

## 6.4 Content Agent

Creates content drafts and creative concepts based on business context, brand voice, and campaign objectives.

## 6.5 Operations Orchestrator

Coordinates multi-step operations. For example, a campaign workflow may create a draft, validate the facts, request approval, schedule publication, and track the result.

## 6.6 Deterministic Execution Workers

Perform operations such as publishing content, sending authorized messages, retrying failed jobs, and recording results.

The LLM proposes or selects an allowed operation. Deterministic workers execute it using validated parameters.

## 6.7 Policy and Approval Service

Checks permissions, action risk, approval requirements, expiration, and execution eligibility.

## 6.8 Reporting Service

Builds reports from stored events and operational records rather than relying on the language model to estimate counts.

### Agent design principle

Use ordinary functions and deterministic services whenever possible. Introduce agentic planning only where a task requires reasoning across multiple steps.

---

# 7. Technical Architecture

## 7.1 Proposed stack

### Frontend

- React.
- TypeScript.
- Responsive, mobile-first interface.
- PWA support as a later enhancement.
- Shared UI components.
- Localization support.

### Backend

- Python.
- FastAPI.
- Pydantic for request and command validation.
- SQLAlchemy for database access.
- Alembic for database migrations.

### Data and background processing

- PostgreSQL for persistent application data.
- Redis for queueing and short-lived coordination where appropriate.
- Celery or an equivalent background worker system.
- S3-compatible object storage for media, if required.

### AI integration

- Provider-independent LLM adapter.
- Structured outputs for command interpretation.
- Tool calling with typed schemas.
- Context retrieval from business knowledge.
- Model-independent evaluation tests.

### Deployment and development

- Docker Compose for local development.
- Environment-based configuration.
- Automated tests.
- Structured logging.
- Database migrations.
- Separate frontend, API, and worker processes.

This is the proposed baseline, not a requirement to introduce every component before the first working demonstration. Keep the initial setup as simple as possible.

---

# 8. System Architecture

The high-level request flow is:

User or Instagram event → Channel/API Gateway → Authentication and Workspace Context → Command Router or Event Processor → Knowledge and Policy Services → Agent or Business Logic → Approval Service, when required → Execution Worker → Instagram API or Internal Database → Verification → Activity Log and Notification.

### Component responsibilities

**Frontend:** Collects user input, displays drafts, shows approval requests, and presents operational status.

**API:** Authenticates requests, validates data, enforces workspace boundaries, and exposes application operations.

**Agent layer:** Interprets requests, retrieves context, and proposes actions.

**Business services:** Enforce rules for knowledge, content, conversations, and approvals.

**Worker layer:** Executes slow or scheduled operations and handles retries.

**Integration layer:** Communicates with Meta and optional messaging providers.

**Database:** Stores persistent state, version history, operations, and audit records.

**Notification layer:** Informs the user about results, failures, and actions requiring attention.

External integrations must be isolated behind service interfaces so they can be replaced or disabled without rewriting the product.

---

# 9. Initial Database Model

The schema should be normalized where appropriate and include workspace ownership from the beginning.

## 9.1 Core tables

### users
- id
- email
- authentication fields or external identity reference
- created_at

### workspaces
- id
- name
- locale
- timezone
- currency
- created_at

### workspace_members
- workspace_id
- user_id
- role
- created_at

### social_accounts
- id
- workspace_id
- platform
- external_account_id
- account_name
- connection_status
- encrypted_credentials_reference
- created_at
- updated_at

### business_facts
- id
- workspace_id
- key
- value
- value_type
- source
- verification_status
- version
- updated_by
- updated_at

### business_fact_versions
- id
- business_fact_id
- previous_value
- new_value
- changed_by
- change_reason
- created_at

### conversations
- id
- workspace_id
- social_account_id
- external_conversation_id
- status
- last_message_at
- assigned_to
- created_at

### messages
- id
- conversation_id
- external_message_id
- direction
- message_type
- content_reference
- processing_status
- created_at

### content_items
- id
- workspace_id
- social_account_id
- content_type
- caption
- media_reference
- status
- scheduled_at
- published_at
- external_publication_id
- created_at
- updated_at

### approvals
- id
- workspace_id
- operation_type
- operation_reference
- requested_by
- approved_by
- status
- expires_at
- created_at
- resolved_at

### agent_runs
- id
- workspace_id
- operation_type
- status
- input_reference
- output_reference
- error_code
- started_at
- completed_at

### audit_logs
- id
- workspace_id
- actor_type
- actor_id
- action
- resource_type
- resource_id
- metadata
- created_at

### scheduled_jobs
- id
- workspace_id
- job_type
- resource_reference
- scheduled_at
- status
- attempts
- idempotency_key
- last_error
- created_at
- updated_at

Additional tables can be introduced when actual requirements justify them. Do not build a complex CRM schema before the MVP needs one.

---

# 10. Security and Reliability

Security and operational correctness are product requirements.

## 10.1 Authentication and authorization

- Authenticate users before accessing workspace data.
- Enforce workspace isolation in every relevant query and operation.
- Apply role-based permissions to sensitive actions.
- Do not trust workspace IDs supplied by the frontend without authorization checks.
- Protect administrative operations.

## 10.2 Credentials

- Never expose Meta access tokens to the frontend.
- Store tokens encrypted or through a secure secret-management mechanism.
- Keep API keys and secrets in environment configuration or a secret manager.
- Never commit credentials to the repository.
- Avoid logging access tokens, authorization codes, or sensitive message content.

## 10.3 Webhook processing

- Verify incoming webhook authenticity where supported.
- Deduplicate events using provider event or message identifiers.
- Handle repeated and out-of-order events safely.
- Acknowledge incoming webhooks promptly and process long-running tasks asynchronously.
- Monitor rejected and failed events.

## 10.4 Idempotency and retries

A repeated event must not cause duplicate replies or publications.

Each external operation should have a stable operation identifier and an appropriate idempotency strategy.

Retry transient failures with bounded backoff. Permanent failures should be reported rather than retried indefinitely.

## 10.5 Auditability

For every consequential action, the application should be able to answer:

- What was requested?
- Who or what initiated it?
- Which facts were used?
- Was approval required?
- Was approval granted?
- What operation was executed?
- Did it succeed?
- What happened if it failed?

## 10.6 Data retention

Define retention and deletion behavior for customer messages, generated media, logs, and disconnected accounts. Provide a way to disconnect integrations and delete associated data in accordance with applicable requirements.

---

# 11. Meta and External Integration Strategy

Meta integration is a major external dependency and should be validated early.

The product must verify the current requirements for:

- Instagram Professional account eligibility.
- Facebook or Meta account connection requirements.
- OAuth authorization.
- Instagram messaging permissions.
- Webhook subscriptions.
- Content publishing capabilities.
- Media format restrictions.
- Rate limits.
- App Review and production access.

Do not assume all features will work with an unreviewed development application.

### Development strategy

Define an integration interface with operations such as:

- Connect account.
- Retrieve permitted account information.
- Receive and process messaging events.
- Send an authorized reply.
- Publish supported content.
- Retrieve publication status where supported.

The real Meta adapter should implement the verified capabilities. A mock adapter should implement the same interface for local development.

This allows the product to be demonstrated before every external permission is approved.

The mock adapter must be clearly labeled as simulated and must never present simulated actions as real Instagram activity.

---

# 12. User Interface

The interface should prioritize mobile usability rather than simply shrinking a desktop dashboard.

## 12.1 Main navigation

A possible initial navigation structure:

- Home.
- Inbox.
- Content.
- Business Knowledge.
- Approvals.
- Activity.
- Settings.

On mobile, use a compact navigation pattern and keep the most common actions accessible.

## 12.2 Home

Show:

- Connection status.
- Recent activity.
- Messages requiring attention.
- Content awaiting approval.
- Upcoming scheduled posts.
- Recent publishing failures.
- A natural-language command input.

Avoid overwhelming the user with charts and technical metrics.

## 12.3 Inbox

Show conversations, customer messages, generated replies, processing status, and escalation state.

The owner should be able to inspect an automated response and take over a conversation when needed.

## 12.4 Content

Show drafts, approvals, scheduled content, publication history, and errors.

Content cards should distinguish clearly between draft, awaiting approval, scheduled, published, and failed states.

## 12.5 Business Knowledge

Show verified facts in an understandable format.

Allow users to edit prices, hours, services, FAQs, and tone preferences without knowing how AI memory works.

Show where a fact came from and when it was last updated when useful.

## 12.6 Approvals

Show the exact proposed action, its content, its target account, and any relevant schedule.

Approval and rejection actions must be explicit. Avoid ambiguous one-click actions that could publish the wrong content.

## 12.7 Settings

Include account connections, language, timezone, business profile, automation rules, approval preferences, and notification settings.

---

# 13. Open-Source and SaaS Model

The product should use one shared core with an open-source repository and a hosted offering.

## 13.1 Open-source core

The repository should include the main application, core agents, business logic, supported integration interfaces, database models, and local development setup.

A permissive license such as Apache-2.0 is a candidate if the intention is to allow broad reuse, modification, and commercial hosting.

The final license choice should be made deliberately before public release. A fully open-source license generally allows other parties to host their own instances.

## 13.2 Hosted SaaS

Potential revenue sources include:

- Managed hosting.
- Assisted onboarding.
- Ongoing support.
- Managed integrations.
- Backups and monitoring.
- Higher usage limits.
- Team features.
- Billing and subscription management.

The paid product should earn revenue by reducing the customer's operational burden, not by making the open-source installation artificially difficult.

## 13.3 Assisted onboarding

For early Turkish customers, the founder can help with:

1. Connecting the customer's account.
2. Entering and verifying business information.
3. Configuring initial automation rules.
4. Testing common customer questions.
5. Preparing the first content schedule.
6. Explaining how to review approvals and failures.

Over time, repeated setup tasks should become automated so the business can onboard without founder involvement.

---

# 14. MVP Scope

The first implementation should demonstrate a complete, testable workflow.

## Included in the initial prototype

1. Workspace and business profile.
2. Structured business knowledge with version history.
3. Natural-language command input.
4. AI-assisted command interpretation.
5. Business-aware DM response drafting.
6. Human review and approval.
7. Content draft creation.
8. Content scheduling model.
9. Mock publishing worker.
10. Activity log and daily summary.
11. Mobile-first dashboard.
12. Mock Instagram account and event data.
13. Tests for the core workflows.
14. A clear path to adding the real Meta integration.

The initial prototype should work locally without requiring production Meta permissions or a paid messaging provider.

## Deferred until the core works

- Production WhatsApp integration.
- Multiple messaging providers.
- Full autonomous campaign management.
- Instagram Ads management.
- Multi-platform publishing.
- Advanced CRM.
- Agency-scale account management.
- Complex analytics.
- Subscription billing.
- Sophisticated multi-agent collaboration.

These features should be introduced only after the initial workflow is functional and the integration requirements are understood.

---

# 15. Prototype Demonstration Scenarios

The following scenarios should be possible in the local application.

## Scenario A: Business setup

1. Open the application.
2. Create or select a demo workspace.
3. Load sample business information for a fictional gym.
4. Review its opening hours, services, prices, and FAQs.
5. Mark the important facts as verified.
6. Open the home dashboard and see the business ready for testing.

## Scenario B: Automated customer inquiry

1. Simulate an Instagram DM asking about membership prices.
2. The application loads the verified pricing facts.
3. The Conversation Agent drafts a response.
4. The policy service determines whether it can be sent automatically.
5. If approval is required, the response appears in the review queue.
6. The user approves it.
7. The mock integration records a simulated successful send.
8. The conversation and audit log reflect the result.

## Scenario C: Change a business fact

1. Enter: "Our monthly membership price is now 7,000 TRY."
2. The system identifies the pricing fact.
3. The user confirms the update if required.
4. The new value is saved with version history.
5. A subsequent price inquiry uses the new value.
6. Pending content containing the old price is flagged for review.

## Scenario D: Create and schedule a Story

1. Enter: "Prepare a Story promoting our trial session."
2. The Content Agent generates a draft.
3. The application displays the proposed copy and media placeholder.
4. The user reviews and approves it.
5. The user selects a scheduled time.
6. The scheduler creates a job.
7. The mock worker executes the job at the appropriate time in a test environment.
8. The application records the simulated result.

## Scenario E: Review the day's operations

1. Generate several simulated messages and content operations.
2. Open the daily report.
3. Verify that counts are calculated from stored records.
4. Inspect failed operations and pending approvals.
5. Confirm that the displayed results match the activity log.

## Scenario F: Failure handling

1. Configure a simulated publishing failure.
2. Run the scheduled job.
3. Verify that the worker records the error.
4. Verify that retries are bounded.
5. Confirm that duplicate publication is prevented.
6. Show a clear failure state to the user.

These scenarios are intended for development and testing. Simulated results must be visibly distinguished from real platform operations.

---

# 16. Development Phases

## Phase 1: Working local prototype

Build the frontend, API, database models, mock integration, business knowledge, command processing, approvals, content drafts, scheduling, and activity logs.

Goal: demonstrate the complete user experience with simulated Instagram operations.

## Phase 2: Real Instagram connection

Implement Meta OAuth, account validation, required webhook subscriptions, and the first supported messaging or publishing capability.

Validate permissions and API restrictions before expanding the feature set.

## Phase 3: Reliable automation

Add robust retries, event deduplication, execution monitoring, better policy checks, evaluation datasets, and clear human handoff.

## Phase 4: Messaging channels

Introduce the first supported messaging provider behind the channel abstraction. Evaluate Telegram and WhatsApp based on customer preference, official integration requirements, and operating cost.

## Phase 5: Initial paid pilots

Onboard a small number of local businesses, measure setup effort and actual usage, and test willingness to pay.

## Phase 6: Self-service SaaS

Improve onboarding, billing, tenant management, deployment, localization, documentation, and operational monitoring.

The order can change if Meta's approval process or customer feedback reveals a different priority.

---

# 17. Testing and Quality Criteria

The initial implementation should have automated tests for important business rules.

### Business knowledge

- Verified facts are used in generated responses.
- Updating a fact preserves its previous version.
- Conflicting facts are surfaced.
- Missing prices are not invented.

### DM processing

- Duplicate incoming events are processed safely.
- Responses use the correct workspace context.
- Ambiguous messages can be escalated.
- Unauthorized outbound operations are blocked.

### Content and scheduling

- Drafts do not publish without required approval.
- A scheduled job uses the correct timezone.
- Repeated worker execution does not create duplicate posts.
- Failed jobs are recorded and reported.
- Changes to important facts can flag affected scheduled content.

### Security

- One workspace cannot access another workspace's records.
- Secrets are not exposed to frontend responses or logs.
- Expired or unauthorized approvals cannot execute actions.

### User experience

- Core workflows work on mobile-sized screens.
- Every important operation has a visible status.
- Errors explain what happened and what the user can do next.
- The application clearly distinguishes real integrations from simulated ones.

Potential evaluation targets can be established after collecting a baseline. For example, test routine-message accuracy, setup time, duplicate-operation rate, and publishing success rate. These should be measured rather than assumed.

---

# 18. Initial Success Metrics

The purpose of the first prototype is to demonstrate product behavior, not to claim production performance.

Measure:

- Time required to configure a demo business.
- Time required to process a routine customer inquiry.
- Accuracy of responses against verified business facts.
- Number of conversations correctly escalated.
- Percentage of operations completed successfully.
- Number of duplicate actions.
- Number of pending approvals.
- User understanding of system status.
- Time saved compared with the manual workflow.

For the first local pilot, interview approximately 10 to 15 businesses, aim to identify several serious pilot candidates, and try to secure paid commitments before investing heavily in advanced features. These are practical validation targets, not guaranteed conversion benchmarks.

---

# 19. Implementation Principles

1. Build a working end-to-end prototype before adding numerous agents.
2. Use one shared codebase for Turkish and global experiences.
3. Keep business rules outside LLM prompts.
4. Use structured business facts for prices, hours, and policies.
5. Treat AI output as a proposal until validated.
6. Separate planning from external execution.
7. Require approval for actions that need it.
8. Make operations observable and auditable.
9. Design for retries, duplicate events, and external API failures.
10. Keep provider integrations behind interfaces.
11. Make the mobile experience a first-class product requirement.
12. Avoid requiring customers to understand MCP, API keys, or workflow configuration.
13. Prefer a small number of useful, reliable capabilities over a large number of incomplete features.
14. Keep the local demo usable without external credentials.
15. Never report a simulated operation as a real-world success.

---

# 20. Definition of Done for the First Build

The initial build is ready for a hands-on demonstration when:

- The application starts locally using documented instructions.
- A user can open the mobile-friendly dashboard.
- A demo business can be loaded and edited.
- Business facts can be verified and versioned.
- A simulated DM produces a business-aware draft.
- The approval flow works end to end.
- A business price update changes subsequent responses.
- A content draft can be approved and scheduled.
- A mock worker executes and records a scheduled job.
- Failures and retries are visible.
- The activity report matches actual stored records.
- The automated tests pass.
- No real Instagram action is falsely represented as having occurred.

**Final product direction:** Build a reliable Instagram operations system whose complexity stays behind the scenes. The initial goal is not to demonstrate how many agents the application contains. It is to demonstrate that a business owner can give an instruction, see the system understand it, approve important actions, and trust the recorded outcome.