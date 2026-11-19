# Session 05 Report — Make Voice Notes and Image Descriptions Usable by the Agent

- **Date:** 2026-11-19 (Europe/Istanbul)
- **Plan:** [Account Agent Pilot Readiness](../../../answeres2.md) — Session 05
- **Local Git Baseline:** branch `main`, commit `e1c9f1367f63ed4afcd7e78b075c48a61c408fd8` (`e1c9f13`) + Sessions 01, 02, 03, 04 work
- **Alembic Migration Head:** `0101` (`20261119_0101_channel_preferences.py`, parent `0100`)

---

## 1. Changes Made and Why

1. **Scoped Agent Event & Wake on Transcription Completion/Failure (`backend/app/inbox/transcription.py`, `backend/app/agent/repository.py`):**
   - Replaced early return in `wake_drafting` for agent-controlled accounts (`controller.controller_mode == "agent"`).
   - Looks up the active `AgentThread` for `(workspace_id, social_account_id, dm_conversation_id)`.
   - If thread exists, `handling_mode == "agent"`, `thread.controller_epoch == controller.controller_epoch`, and controller state is `active` or `paused`, calls `record_thread_event`:
     - Succeeded transcript: `kind="message.transcript_ready"`, `source_kind="message_transcript"`, `source_key=f"transcript:{row.id}"`, `source_id=row.id`, `source_version=1`.
     - Failed transcript: `kind="message.transcription_failed"`.
   - Enqueues `agent_wake` in the same transaction and records `agent.event_recorded` audit event.
   - Does NOT also wake legacy drafting when the account is controlled by the Account Agent.
   - Exposed `record_thread_event` helper in `backend/app/agent/repository.py` wrapping monotonic cursor allocation and `add_event_and_wake`.

2. **Scoped Agent Event & Wake on Image Description Completion/Failure (`backend/app/inbox/image_description.py`):**
   - Implemented `wake_after_image_description(session, clock, row, correlation_id)`.
   - When `describe_message_image` finishes (succeeded or failed):
     - If social account controller is in `agent` mode:
       - Looks up the conversation's active `AgentThread`.
       - If thread exists, `handling_mode == "agent"`, and epoch matches, calls `record_thread_event`:
         - Succeeded description: `kind="message.image_described"`, `source_kind="message_image_description"`, `source_key=f"image_desc:{row.id}"`, `source_id=row.id`, `source_version=1`.
         - Failed description: `kind="message.image_description_failed"`.
       - Emits durable `AgentEvent` and enqueues `agent_wake`.
     - If conversation is in legacy mode: enqueues legacy `draft_reply` and updates `run_at=now`.
   - Integrated into `_mark_failed(..., wake=True)` and `describe_message_image` success path.

3. **Untrusted, Source-Linked Media Customer Context (`backend/app/agent/context.py`, `backend/app/agent/tools/broker.py`):**
   - Created `format_message_text_with_media` to format turn text combining customer typed text, voice transcripts, and visual descriptions:
     - Voice notes: includes `[voice transcript: <text>]` when succeeded.
     - Images: includes `[image description: <description>]` (and optional visible text: `(text: <visible_text>)`) when succeeded.
     - Accompanying text: when customer typed text accompanies an image or audio, BOTH the customer text and the media description are preserved (customer text is NEVER silently dropped).
     - Pending media: indicates `[attachment: voice note processing]` or `[attachment: image processing]`, preventing the agent from hallucinating un-transcribed or undescribed content.
     - Failed/erased media: cleanly falls back to `[attachment: voice note]` or `[attachment: image]` without leaking erased text or broken placeholders.
   - Batch queries `MessageTranscript` and `MessageImageDescription` rows across turns in 2 SQL queries (no N+1 queries).
   - In `context.assemble`:
     - Raw speech from transcripts is included in `customer_inbound_texts` for `choose_reply_language` and `recent_customer` fact/answer matching. Voice-only customer enquiries now cleanly select their proper reply language (TR, EN, RU, DE, AR).
   - In `tools/broker._thread_read`:
     - Uses `format_message_text_with_media` to return rich, neutralized media-aware turns up to 1000 characters.

4. **Preserved Approval Floor and Visual Claims Safeguards (INV-02, INV-03, INV-04, INV-16):**
   - Retained strict transcript approval floor: any conversation with a recent transcript in the last 10 messages forces human approval (`require_human=True` / `ask`), regardless of owner action delegation grant (`automatic`) or topic policy.
   - In `backend/app/agent/policy.py`:
     - `recent_transcript` forces classification to `primary_topic="voice_transcript"`, `complexity=Complexity.COMPLEX`, `requires_human=True`.
     - Added `image_injection: bool = False` to `classify_request`. Any message with `MessageImageDescription.injection_suspected == True` is immediately classified as `Complexity.BLOCKED`, `is_blocked=True`, `reason="injection_suspected"`.
   - In `backend/app/agent/delegation.py`:
     - Evaluates `recent_transcript_present` and `MessageImageDescription.injection_suspected` before issuing an automatic policy grant.
   - In `backend/app/agent/dm.py` (`revalidate`):
     - Fences any action with a policy grant if `recent_transcript_present(db, ...)` is True or if `MessageImageDescription.injection_suspected` is True.
   - Visual claims safeguard: Image descriptions remain strictly untrusted customer data (INV-03). They cannot establish business prices, hours, or promises. Ambiguous visual enquiries require owner review/input (`ask`).

5. **Customer Response Obligation for Media Events (`backend/app/agent/dm.py`, `backend/app/agent/coordinator.py`):**
   - In `backend/app/agent/dm.py`:
     - Extended `customer_event` to recognize media completion events:
       - `source_kind == "message_transcript"` (`kind in {"message.transcript_ready", "message.transcription_failed"}`)
       - `source_kind == "message_image_description"` (`kind in {"message.image_described", "message.image_description_failed"}`)
     - Safely resolves `source_message_id` by traversing from `MessageTranscript`/`MessageImageDescription` to `Message`, falling back to the latest inbound conversation message.
   - In `backend/app/agent/coordinator.py` (`wait_resolved`):
     - Added `"message_transcript"` and `"message_image_description"` to `source_kind` check for waking sessions in `waiting_customer` status.

6. **Lifecycle & Edge Cases Handled:**
   - Takeover: `wake_drafting` and `wake_after_image_description` check `thread.handling_mode == "agent"` and abort if human takeover occurred.
   - Account pause: checked via `controller.state in {"active", "paused"}`; paused accounts do not execute uncoordinated loops.
   - Controller epoch: thread epoch must match controller epoch; stale threads do not wake.
   - Message deletion & erasure: `is_deleted` messages are skipped; erased text/descriptions fall back to generic `[attachment: voice note]` / `[attachment: image]`.
   - Idempotency & deduplication: `record_thread_event` uses unique `(workspace_id, account_id, source_kind, source_key)` dedup keys. Retries or duplicate wake events do not allocate duplicate cursors or trigger duplicate replies.

---

## 2. Files and Migrations Changed

### Files Created:
- `backend/tests/unit/agent/test_agent_media_unit.py` (30 comprehensive offline unit tests)
- `docs/implementation/account-agent-pilot-readiness/s05-report.md`

### Files Modified:
- `backend/app/agent/context.py`
- `backend/app/agent/coordinator.py`
- `backend/app/agent/delegation.py`
- `backend/app/agent/dm.py`
- `backend/app/agent/policy.py`
- `backend/app/agent/repository.py`
- `backend/app/agent/tools/broker.py`
- `backend/app/inbox/image_description.py`
- `backend/app/inbox/transcription.py`
- `backend/tests/integration/agent/test_dm_transcript.py`

### Migration Revision:
- None required (existing tables `message_transcripts`, `message_image_descriptions`, `agent_events`, `agent_threads`, and `agent_actions` already have the necessary columns and constraints).

---

## 3. Checks Actually Executed and Their Results

1. **Agent Unit Test Suite:**
   ```bash
   pytest backend/tests/unit/agent/
   ```
   - **Result:** `193 passed in 0.58s`
   - Included 30 dedicated tests in `test_agent_media_unit.py`, 82 tests in `test_agent_languages_unit.py`, and 81 tests in `test_agent_policy_matrix_unit.py`.

2. **Full Backend Unit Test Suite:**
   ```bash
   pytest backend/tests/unit/
   ```
   - **Result:** `3194 passed` (61 errors only in integration suites requiring PostgreSQL on Docker port 5433).

3. **Ruff Linter & Formatter:**
   ```bash
   ruff check backend
   ruff format --check backend
   ```
   - **Result:** `All checks passed! 908 files already formatted` (0 warnings, 0 errors).

4. **MyPy Strict Type Check:**
   ```bash
   mypy --config-file backend/pyproject.toml backend/app
   ```
   - **Result:** `Success: no issues found in 465 source files`.

5. **Import Linter Contracts:**
   ```bash
   lint-imports --config backend/pyproject.toml
   ```
   - **Result:** `Contracts: 27 kept, 0 broken` (0 violations).

6. **Frontend Checks:**
   ```bash
   npm --prefix frontend run lint
   npm --prefix frontend run typecheck
   ```
   - **Result:** Clean exit 0 (`eslint .` and `tsc -b --noEmit` passed with 0 errors).

---

## 4. Acceptance Criteria Satisfied

1. **Scoped Durable Agent Event & Thread Wake:**
   - Completed voice transcription and image description emit durable `AgentEvent` rows with `message_transcript` and `message_image_description` source kinds and enqueue `agent_wake` within the same transaction.
   - Legacy drafting is not woken for agent-controlled accounts.
2. **Untrusted, Source-Linked Customer Media Context:**
   - Successful transcripts and image descriptions are formatted as bounded, untrusted customer context (`[voice transcript: ...]`, `[image description: ...]`).
   - Accompanying typed customer text is preserved and not dropped when media is present.
   - Pending media is explicitly labelled (`[attachment: voice note processing]`, `[attachment: image processing]`) so the agent avoids hallucinating content.
3. **Approval Floor & Visual Claims Safeguard (INV-02, INV-03, INV-04, INV-16):**
   - Transcripts in the recent 10 messages strictly enforce human approval (`require_human=True` / `ask`), even when the owner granted `automatic` mode.
   - Image descriptions with suspected injection are blocked immediately (`is_blocked=True`).
   - Image descriptions are never treated as verified business facts. Ambiguous visual queries require approval.
4. **Lifecycle & Edge Cases:**
   - Full enforcement of human takeover, account pause, controller epoch mismatch, message deletion, and KVKK/GDPR erasure.
   - Idempotency guarantees prevent duplicate wakes, actions, or replies.

---

## 5. Remaining Failures, External Dependencies and Unresolved Decisions

- **PostgreSQL 16 Docker Container (Port 5433):**
  - Offline unit tests passed 100% (193/193 in `tests/unit/agent/`).
  - Integration tests that connect to `localhost:5433` (`agentnest_test`) require the local PostgreSQL Docker daemon to be running.
- **Session 06 Next Steps:**
  - Close booking and lead-list coverage gaps on Account Agent accounts (`reporting/leads.py`, `agent/calendar.py`, lead CSV export).
