# Session 03 Report — Define and Implement Basic-Versus-Complex Agent Reply Policy

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 03
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Session 01 & 02 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Deterministic Topic Classification & Semi-Automation Reply Matrix (`backend/app/agent/policy.py`):**
   - Implemented a server-side, deterministic classification module that evaluates customer inbound messages, grounding facts, and execution context.
   - Per **INV-04** and prompt guidelines, authorization never relies on or trusts LLM-generated `basic` or `safe` flags.
   - Evaluates inbound customer text across all five supported languages (`tr`, `en`, `ru`, `de`, `ar`) reusing vetted regex patterns and keyword heuristics from `app/inbox/escalation.py`, `app/ai/injection.py`, and `app/policy/rules_reply.py`.
   - Distinguishes **Basic Topics** (`greeting`, `hours`, `location_contact`, `services`, and `pricing` when explicitly permitted and usable) from **Complex Topics** (`complaint`, `refund`, `discount_negotiation`, `custom_quote`, `booking_mutation`, `legal_health_safety`, `voice_derived`, `abusive`, `injection`, `unclear_mixed`, `missing_facts`, `unusable_fact`, `price_disclosure_forbidden_in_public`).
   - Categorizes requests into complexity levels: `basic`, `complex`, or `prohibited`.

2. **Core Invariant: Topic Rule Restricts, Never Broadens:**
   - A reply action is authorized as `automatic` **ONLY** when:
     1. The owner has explicitly granted `rule.mode == "automatic"` for that action type (`dm.send`, `comment.reply`, or `comment.private_reply`).
     2. Server-side classification classifies the request as `basic`.
     3. All existing safety checks pass (valid usable facts, public/private boundary, messaging window open, rate limits / quotas available).
   - If an owner configures `rule.mode == "ask"` (human approval required), even a basic greeting or hours query remains `ask`. A topic rule can restrict an action grant from `automatic` down to `ask`, but **never** broadens an `ask` grant to `automatic`.
   - Prohibited categories (injections, legal/health threats, abuse) are marked `blocked` (`escalate_to_human` / safety block) regardless of mode.
   - Classification evidence, detected topics, complexity, and exact reason codes are recorded in `AgentAction.policy_grant`, `AgentAction.outcome_code`, and `approval.summary`.

3. **Public Comment & Price Disclosure Boundary:**
   - Under no circumstances may public comments (`comment.reply`) disclose prices. In `policy.py` and `backend/app/comments/actions.py`, any price inquiry on a public comment is classified as `price_disclosure_forbidden_in_public` (`complex`), restricting `comment.reply` to `ask` or routing to private reply (`comment.private_reply`).
   - For direct messages (`dm.send`) and private replies (`comment.private_reply`), standard pricing questions are classified as `basic` only if `prices_shared` is true, the requested service price is grounded in a verified, non-stale, non-expired fact (`verified_price_present`), and no custom negotiation or discount request is present.

4. **Integration with Delegation Service (`backend/app/agent/delegation.py`):**
   - Updated `authorize_action` to invoke `evaluate_action_policy` for reply actions (`dm.send`, `comment.reply`, `comment.private_reply`).
   - Automatically resolves customer inbound text, grounding facts, prices shared setting, and transcript presence from the action context / parameters.
   - When a complex topic restricts an otherwise `automatic` action to `ask`, the reason is persisted in `approval.summary` (e.g. `Human approval required: discount_negotiation`).
   - When an action is admitted as `automatic`, `policy_grant` records the matched topic, complexity, and evaluated reason code.

5. **Send-Time and Approval Revalidation Fences (`dm.py`, `comments/actions.py`, `comments/private_reply.py`):**
   - Rechecks policy classification at send time prior to external dispatch:
     - In `backend/app/agent/dm.py` (`revalidate`): Re-evaluates `evaluate_action_policy`, checks messaging window expiration, recent transcript presence, and verifies that pricing facts remain verified and price sharing is still enabled.
     - In `backend/app/comments/actions.py` (`revalidate`): Ensures public comment replies do not contain price disclosures and re-evaluates basic topic classification for automatic grants.
     - In `backend/app/comments/private_reply.py` (`eligibility`): Rechecks basic policy classification and price disclosure on automatic grants before sending private messages to commenters.

6. **Owner-Facing Agent Delegation UI & Localization:**
   - In `frontend/src/features/agent/DelegationForm.tsx`:
     - Added an informative "Yarı Otomasyon Yanıt Politikası" / "Semi-Automation Reply Policy" section.
     - Provides clear visual distinction between what auto-sends under `automatic` mode (Selamlamalar, Doğrulanmış çalışma saatleri, Adres ve iletişim, Standart doğrulanmış fiyatlar, Hizmet açıklamaları) versus what always requires approval (Şikayetler ve iadeler, İndirim ve pazarlık talepleri, Özel teklifler, Randevu oluşturma/iptal, Sesli mesaj yanıtları, Belirsiz veya çelişkili sorular).
     - Localized in Turkish (`frontend/src/i18n/locales/tr/agent.json`) and English (`frontend/src/i18n/locales/en/agent.json`).

7. **Documentation & Contracts:**
   - Updated `docs/architecture/account-agent-contracts.md` with Section 4.1 "Semi-Automation Reply Policy Matrix (Basic vs Complex)", detailing the topic matrix, classification rules, reason codes, public comment restrictions, and revalidation fences.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/app/agent/policy.py`
- `backend/tests/unit/agent/test_agent_policy_matrix_unit.py`
- `docs/implementation/account-agent-pilot-readiness/s03-report.md`

### Files Modified:
- `backend/app/agent/delegation.py`
- `backend/app/agent/dm.py`
- `backend/app/comments/actions.py`
- `backend/app/comments/private_reply.py`
- `docs/architecture/account-agent-contracts.md`
- `frontend/src/features/agent/DelegationForm.tsx`
- `frontend/src/i18n/locales/en/agent.json`
- `frontend/src/i18n/locales/tr/agent.json`

### Migration Revision:
- None required (operates within existing `agent_actions`, `action_approvals`, and `agent_delegation_rules` schema).

---

## 3. Checks Actually Executed and Their Results

### Backend Checks:
1. **Linter & Formatting:**
   - `backend\.venv\Scripts\ruff.exe check backend/app backend/tests` -> **PASS** (0 errors)
   - `backend\.venv\Scripts\ruff.exe format --check backend/app backend/tests` -> **PASS** (898 files already formatted)
2. **Type Checking:**
   - `cd backend; .venv\Scripts\mypy.exe app` -> **PASS** (Success: no issues found in 465 source files)
3. **Architecture Import Linter:**
   - `cd backend; .venv\Scripts\lint-imports.exe` -> **PASS** (Contracts: 27 kept, 0 broken)
4. **Unit Test Suite:**
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent/test_agent_policy_matrix_unit.py -q` -> **PASS** (81 passed in 0.12s)
     - Covers every row of the policy matrix.
     - Tests all 5 languages (`tr`, `en`, `ru`, `de`, `ar`).
     - Tests fail-closed behavior, prompt injection blocking, public comment price forbidding, missing/unusable facts, and `ask` preservation.
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent backend/tests/unit/identity backend/tests/unit/notifications backend/tests/unit/policy -q` -> **PASS** (664 passed in 1.04s)

### Frontend Checks:
1. **i18n Coverage Check:**
   - `cd frontend; npm.cmd run i18n:check` -> **PASS** (en, tr | 2993 keys | 2139 literal t() calls verified)
2. **Linter:**
   - `cd frontend; npm.cmd run lint` -> **PASS** (0 errors)
3. **Type Checking:**
   - `cd frontend; npm.cmd run typecheck` -> **PASS** (0 errors)
4. **Unit Tests:**
   - `cd frontend; npm.cmd test -- --run src/features/agent/agent.test.tsx` -> **PASS** (13 passed in 6.82s)

---

## 4. Acceptance Criteria Satisfied

- [x] **Restrictive Topic Policy Matrix:** Automatic mode auto-sends only basic topics when explicitly granted; never broadens `ask` grants to `automatic`.
- [x] **Deterministic Server-Side Classification (INV-04):** Does not trust model flags; multilingual regex/keyword detection across `tr`, `en`, `ru`, `de`, `ar` handles greetings, hours, location, services, pricing, complaints, refunds, discounts, appointments, voice notes, and prompt injection.
- [x] **Price Disclosure & Public Boundary Enforcement:** Public comments forbid price disclosures. DMs enforce `prices_shared` and verified, non-stale pricing facts.
- [x] **Action Audit & Reason Logging:** Records topic classification, complexity level, and outcome code in `AgentAction.policy_grant` and `AgentAction.outcome_code`.
- [x] **Send-Time & Approval Decision Revalidation:** Rechecks policy in `dm.py`, `comments/actions.py`, and `comments/private_reply.py`.
- [x] **Owner UI & Localization:** Localized semi-automation policy matrix with categorized examples in Turkish and English in `DelegationForm.tsx`.
- [x] **Comprehensive Test Suite:** 81 unit tests in `test_agent_policy_matrix_unit.py` testing every scenario and row of the matrix.

---

## 5. Remaining Failures, External Dependencies, and Unresolved Decisions

- **PostgreSQL Database Container:** PostgreSQL on port 5433 was offline during testing; all verification was completed using offline unit tests, mock sessions, static analysis (`mypy`), linting (`ruff`), import contracts (`lint-imports`), and frontend checks (`tsc`, `eslint`, `vitest`).
- **External Dependencies:** No new external dependencies introduced.
- **Unresolved Decisions:** None. Implementation strictly adheres to Section 03 brief in `answeres2.md` and system invariants (INV-02, INV-03, INV-04, INV-16).
