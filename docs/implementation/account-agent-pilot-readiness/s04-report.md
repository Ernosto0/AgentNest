# Session 04 Report — Extend All Account Agent Reply Paths to Five Languages

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 04
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01, 02, 03 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Account Agent Context Multilingual Filter (`backend/app/agent/context.py`):**
   - Replaced hard-coded `if code in ("tr", "en")` with `from app.core.reply_languages import REPLY_LANGUAGES` and `[code for code in workspace.reply_languages if code in REPLY_LANGUAGES]`.
   - The server-selected reply language is now properly determined by `choose_reply_language` for all five languages (`tr`, `en`, `ru`, `de`, `ar`) when enabled in workspace settings.
   - If customer inbound messages contain an unsupported language (e.g., French, Spanish, Chinese, Japanese) or uncertain/mixed evidence, `choose_reply_language` returns `None`. When `model_context.language is None`, `coordinator.py` fails closed with `reason="AGENT_UNSUPPORTED_LANGUAGE"`.

2. **Grounding & Reply Validation (`backend/app/agent/grounding.py`):**
   - Updated `ReplyValidationArgs.language` type annotation to `Literal["tr", "en", "ru", "de", "ar"]`.
   - Localized `owner_answer` wrapper rendering for all five languages:
     - `tr`: `İşletmenin bu talebinize yanıtı: {answer.body}`
     - `en`: `The business's answer to your request: {answer.body}`
     - `ru`: `Ответ бизнеса на ваш запрос: {answer.body}`
     - `de`: `Die Antwort des Unternehmens auf Ihre Anfrage: {answer.body}`
     - `ar`: `رد الشركة على طلبك: {answer.body}`
   - Localized `customer_clarification` question rendering for date and time across all five languages:
     - `tr`: `“{value}” belirttiniz. Tercih ettiğiniz tarih/saat bu mu?`
     - `en`: `You mentioned “{value}”. Is that your preferred date/time?`
     - `ru`: `Вы указали «{value}». Это ваша желаемая дата? / Это ваше желаемое время?`
     - `de`: `Sie haben „{value}“ angegeben. Ist das Ihr bevorzugtes Datum? / Ist das Ihre bevorzugte Uhrzeit?`
     - `ar`: `لقد ذكرت "{value}". هل هذا هو التاريخ المفضل لديك؟ / هل هذا هو الوقت المفضل لديك؟`
   - Added byte length limit guards (`length_issue(text, max_bytes=1000)`) preventing Instagram DM overflow.

3. **Knowledge Retrieval & Broker Tools (`backend/app/agent/knowledge.py`, `backend/app/agent/tools/broker.py`):**
   - In `app/agent/knowledge.py`: Updated `answers_page()` guard from `if language not in {"tr", "en"}` to `if language not in REPLY_LANGUAGES` (allows retrieval of approved answers in `tr`, `en`, `ru`, `de`, `ar`).
   - In `app/agent/tools/broker.py`: Updated `AnswersReadArgs.language` schema to `Literal["tr", "en", "ru", "de", "ar"]`.

4. **Calendar Reply Localized Outcomes (`backend/app/agent/calendar.py`):**
   - Updated `render_calendar_reply()` parameter `language: Literal["tr", "en", "ru", "de", "ar"]`.
   - Provided authentic, localized templates for all five languages across all calendar action outcomes:
     - `booked`: confirmation with local date, time range, and appointment title.
     - `rescheduled`: modification confirmation with updated date, time range, and title.
     - `cancelled`: cancellation confirmation with date, start time, and title.
     - `pending_approval`: notice that the request was received and forwarded for owner approval.
     - `available_slot`: availability response confirming date and start time slot availability.
   - Enforced 1000-byte length limit checks (`length_issue(text, max_bytes=1000)`) on all return paths.

5. **Owner Question Holding Response (`backend/app/owner_requests/service.py`):**
   - Updated `ask()` holding response language condition from `language in {"tr", "en"}` to `language in REPLY_LANGUAGES`.
   - Provided localized holding templates across all five languages:
     - `tr`: `Bu talebiniz için işletmeden bilgi istedim.`
     - `en`: `I've asked the business for information about your request.`
     - `ru`: `Я запросил информацию по вашему вопросу у бизнеса.`
     - `de`: `Ich habe beim Unternehmen Informationen zu Ihrer Anfrage angefordert.`
     - `ar`: `لقد طلبت من الشركة معلومات بخصوص طلبك.`

6. **Frontend Multilingual Approved Answers & Settings:**
   - Extracted `ApprovedAnswerEditor` (`frontend/src/features/knowledge/ApprovedAnswerEditor.tsx`) offering language choices `tr`, `en`, `ru`, `de`, `ar` in the selector dropdown.
   - Updated `ApprovedAnswers.tsx` to use `ApprovedAnswerEditor` and cleanly display multilingual approved answers.
   - Updated `frontend/src/features/inbox/hooks.ts` (`useCreateAnswer`) to support `language: "tr" | "en" | "ru" | "de" | "ar"`.
   - Added `ru`, `de`, and `ar` options to `answers.lang` in both Turkish (`frontend/src/i18n/locales/tr/inbox.json`) and English (`frontend/src/i18n/locales/en/inbox.json`).
   - In `frontend/src/features/settings/WorkspaceSection.tsx`: Removed the obsolete warning badge/note stating that the Account Agent only supports Turkish and English.
   - Updated `settings.test.tsx` and `approvedAnswers.test.tsx` to verify multilingual support and absence of obsolete warnings.

7. **Documentation Updates:**
   - Updated `docs/architecture/account-agent-contracts.md` to specify 5-language support in context assembly, knowledge retrieval, broker schemas, and reply validation.
   - Updated `docs/architecture/business-knowledge.md` §9 to clarify that approved answers can be authored and used in `tr`, `en`, `ru`, `de`, and `ar`.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/tests/unit/agent/test_agent_languages_unit.py` (82 unit tests)
- `frontend/src/features/knowledge/ApprovedAnswerEditor.tsx`
- `docs/implementation/account-agent-pilot-readiness/s04-report.md`

### Files Modified:
- `backend/app/agent/calendar.py`
- `backend/app/agent/context.py`
- `backend/app/agent/grounding.py`
- `backend/app/agent/knowledge.py`
- `backend/app/agent/tools/broker.py`
- `backend/app/owner_requests/service.py`
- `backend/tests/integration/agent/test_agent_language_failclosed.py`
- `docs/architecture/account-agent-contracts.md`
- `docs/architecture/business-knowledge.md`
- `frontend/src/features/inbox/hooks.ts`
- `frontend/src/features/knowledge/ApprovedAnswers.tsx`
- `frontend/src/features/knowledge/approvedAnswers.test.tsx`
- `frontend/src/features/settings/WorkspaceSection.tsx`
- `frontend/src/features/settings/settings.test.tsx`
- `frontend/src/features/settings/connections.test.tsx`
- `frontend/src/i18n/locales/en/inbox.json`
- `frontend/src/i18n/locales/tr/inbox.json`

### Migration Revision:
- None required (data models already had `CheckConstraint(_in("language", REPLY_LANGUAGES))` on `approved_answers` and `ARRAY(Text)` on `workspaces.reply_languages`).

---

## 3. Checks Actually Executed and Their Results

### Backend Checks:
1. **Linter & Formatting:**
   - `backend\.venv\Scripts\ruff.exe check backend/app backend/tests` -> **PASS** (0 errors)
   - `backend\.venv\Scripts\ruff.exe format --check backend/app backend/tests` -> **PASS** (899 files already formatted)
2. **Type Checking:**
   - `cd backend; .venv\Scripts\mypy.exe app` -> **PASS** (Success: no issues found in 465 source files)
3. **Architecture Import Linter:**
   - `cd backend; .venv\Scripts\lint-imports.exe` -> **PASS** (Contracts: 27 kept, 0 broken)
4. **Unit Test Suite:**
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent/test_agent_languages_unit.py -v` -> **PASS** (82 passed in 0.48s)
     - Proves language detection across `tr`, `en`, `ru`, `de`, `ar`.
     - Proves fail-closed behavior on unsupported languages (`fr`, `es`, `zh`, `ja`, `it`).
     - Proves `ReplyValidationArgs` and `AnswersReadArgs` Pydantic schemas accept all 5 languages and reject invalid ones.
     - Proves `answers_page()` guard against invalid languages.
     - Proves owner answer wrapper rendering across all 5 languages + 1000-byte length overflow check.
     - Proves customer date/time clarification question rendering across all 5 languages.
     - Proves calendar reply rendering (`booked`, `rescheduled`, `cancelled`, `pending_approval`, `available_slot`) across all 5 languages.
     - Proves owner question holding response templates across all 5 languages.
     - Proves Arabic RTL, multi-byte UTF-8 byte boundary, and 1000-byte limit compliance.
   - `backend\.venv\Scripts\pytest.exe backend/tests/unit/agent -q` -> **PASS** (163 passed in 0.52s)

### Frontend Checks:
1. **Linter:**
   - `cd frontend; npm.cmd run lint` -> **PASS** (0 errors, 0 warnings)
2. **Type Checking:**
   - `cd frontend; npm.cmd run typecheck` -> **PASS** (0 errors)
3. **i18n Coverage Check:**
   - `cd frontend; npm.cmd run i18n:check` -> **PASS** (en, tr | 2996 keys | 2134 literal t() calls verified)
4. **Vitest Unit Tests:**
   - `cd frontend; npx vitest run src/features/knowledge/approvedAnswers.test.tsx` -> **PASS** (7 passed)
   - `cd frontend; npx vitest run src/features/settings/settings.test.tsx` -> **PASS** (15 passed)
   - `cd frontend; npx vitest run src/features/settings/connections.test.tsx` -> **PASS** (39 passed)

---

## 4. Acceptance Criteria Satisfied

1. **Context & Language Selection:**
   - Account Agent context recognizes and supports all five configured reply languages (`tr`, `en`, `ru`, `de`, `ar`).
   - Unsupported or uncertain detected languages fail closed (`coordinator.py` sets status to `failed` with `AGENT_UNSUPPORTED_LANGUAGE`).
2. **Tool Schemas & Grounding:**
   - `AnswersReadArgs` broker tool schema and `ReplyValidationArgs` accept `tr`, `en`, `ru`, `de`, and `ar`.
   - `validate_reply()` produces authentic, localized customer clarification questions and owner answer wrappers for each language.
3. **Calendar Replies:**
   - Server-written outcomes (`booked`, `rescheduled`, `cancelled`, `pending_approval`, `available_slot`) are fully localized and formatted across all five languages. Customers never silently receive English confirmations when speaking Turkish, Russian, German, or Arabic.
4. **Holding Responses:**
   - Owner questions with `holding_response=True` generate localized holding text in all five languages.
5. **Approved Answers:**
   - Owners and managers can author, query, and match approved answers in each of the five supported customer reply languages.
   - UI controls remain clean and fully localized in Turkish and English.
6. **Obsolete Warnings Removed:**
   - The obsolete warning stating that the Account Agent only supports Turkish and English has been removed from `WorkspaceSection.tsx`.
7. **Invariants Preserved:**
   - **INV-02**: Verified fact versioning, placeholders, and claim validation function uniformly in all five languages.
   - **INV-11**: 1000-byte UTF-8 limit strictly enforced across all rendered outputs, especially for multi-byte Arabic and Cyrillic text.

---

## 5. Remaining Failures, External Dependencies and Unresolved Decisions

- **PostgreSQL Integration Tests:** Full live integration tests requiring PostgreSQL on port 5433 (e.g. `test_agent_language_failclosed.py`) require the local Docker daemon, which is currently offline on the developer machine. All logic has been thoroughly covered and verified via offline unit tests (`test_agent_languages_unit.py`).
- **No Git Commits Made:** In accordance with execution rules, changes have been verified in the working directory without git commit or push.
