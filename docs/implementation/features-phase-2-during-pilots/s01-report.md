# Feature Phase 2, Session 01: Voice transcription foundation (F-03, part 1)

**Status:** Implemented and verified offline (backend checks and the test directories listed in section 4). Not committed. Stopped for review. Frontend untouched (no UI, no API change, so no `openapi.json` change).
**Baseline:** `main` at `20a0551`, with the unrelated uncommitted `backend/pyproject.toml` import-linter line for D-01 left intact (I only added one line to the neighbouring `openai` contract).
**Migration head:** `0049` (was `0048`). The next free migration is `0050`.
**Real device, real account, real provider:** none was used. No real key was used, no network call was made, and OpenAI transcription quality on real Turkish voice notes is **pending** (section 6).

## 1. What was built

### The flow
1. **Webhook parsing** (`integrations/instagram/webhook_format.py`). A voice note is `message.attachments[]` with `type: "audio"` and `payload.url`. I checked the Meta webhook examples page on 2026-11-16: the attachment type values (including `audio`) and `payload.url` are documented; **the URL's lifetime and hosts are not documented**, and there is no recorded real payload, so both are unverified. The parser now lower-cases and trims the attachment type (a missing or blank type is `file`), and drops an audio URL longer than 2 048 characters. New builder `audio_attachment(url)`. The mock produces `{type: audio, url: "mock-audio://<fixture>"}`; `demo/simulator.voice_attachment(fixture)` and a new `voice_note` demo script (`demo/scripts/customer_messages.yaml`) use it.
2. **Request** (`inbox/transcription.py::request_transcript`, called from `inbox/processing.py::_on_customer_message` in the transaction that stores the message). If the message has an `audio` attachment and transcription is not off, it inserts a `pending` `message_transcripts` row and enqueues `transcribe_voice_note` (an insert; no external call). A voice note with no URL is recorded as `failed` (`VOICE_URL_MISSING`) at once and no job is queued. Echoes (the business's own messages) are never transcribed. Only the first audio attachment of a message is handled.
3. **Job** `transcribe_voice_note` (three phases like `draft_reply`): [T1] read the row, the message and the workspace's 24 h count, close the transaction; download and transcribe with **no transaction open**; [T3] lock the row, re-check the message is still there and not deleted or erased (otherwise `VOICE_SOURCE_GONE`, nothing stored), store text and metadata, audit. A permanent failure is recorded and the job succeeds; a transient one retries (backoff 10 / 60 / 300 s, max 3) and the `on_dead` hook then records the failure, so the dead job stays visible (INV-13).
4. **Failures stay on the existing human path.** Nothing changes for the conversation: an attachment-only message is still `needs_human` with `ATTACHMENT_ONLY` (rule R11), whether the transcript succeeded or failed. Nothing reads the transcript yet (tested).

### Transcription provider interface (`app/integrations/transcription/`)
Its own small interface, not part of `LLMProvider` (no tools, no schema, different data):
- `base.py`: `TranscriptionProvider.transcribe_audio(clip, *, model, timeout_s) -> TranscriptionResult`, `AudioFetcher.fetch(url, *, max_bytes, timeout_s) -> FetchedAudio`.
- `fake.py`: `FakeTranscriptionProvider` (deterministic text from a fixture, scriptable with `queue(...)`; it **refuses real audio** instead of inventing text) and `FixtureAudioFetcher` for mock accounts (only `mock-audio://` URLs, no network). Fixtures: `price_question_tr`, `hours_question_tr`, `disfluent_tr`, `english_question`, `silence`, `toolong`; failure fixtures `expired`, `unreachable`, `oversize`, `notaudio`.
- `openai_provider.py`: `OpenAITranscriptionProvider` (`audio.transcriptions.create`; only the audio is sent, no prompt, no language hint, no metadata; `max_retries=0`; `json` for `gpt-4o*-transcribe` models, `verbose_json` for `whisper-1`; typed errors).
- `fetch.py`: `HttpsAudioFetcher` for real accounts: https only, no credentials, port 443 only, host must end in `.cdninstagram.com`, `.fbcdn.net` or `.fbsbx.com`, every resolved address globally routable, no redirects, no cookies or proxy, **no Authorization header**, `Content-Length` and streaming size cap, content-type check, total deadline of twice the timeout; the signed URL never reaches a log or an error message.
- `audio.py`: content-type allowlist, file-signature sniffing (a declared type that disagrees with the signature is refused), duration probe for MP4/M4A and WAV.
- `__init__.py`: `build_transcriber`, `get_transcriber`, `get_audio_fetcher(simulated=...)`, `override_transcription(...)` for tests.
- The `openai` SDK is now imported by two adapters; `pyproject.toml` has one more `ignore_imports` entry in the "only the OpenAI adapter imports the openai SDK" contract.

### Storage: new table `message_transcripts` (migration `0049`)
A related row, not a column on `messages`, so a machine transcript can never be mistaken for the customer's typed text, and a failure has a place to live. Columns: `id`, `workspace_id`, `message_id` (composite FK to `messages`, cascade; unique per message), `attachment_index`, `status` (`pending|succeeded|failed`), `reason_code` (required exactly when failed), `source` (`transcript`, check-constrained), `text`, `language` (`tr|en|other|null`, detected from the transcript text by the existing deterministic detector; the provider's guess is only the fallback), `provider`, `model`, `duration_seconds`, `audio_bytes`, `is_simulated`, `completed_at`, `erased_at`, `created_at`, `updated_at`. RLS enabled and forced, tenant policy, role grants like 0046 and 0048. Added to `CATEGORY_C_TABLES` (57 tables). Documented in `data-model.md`.

### Retention, erasure, privacy
- **The audio is never stored** (held in memory during the job only), so there is no raw-audio retention rule to apply. If a later session keeps audio for a player it must add one.
- **The transcript is personal data** and follows message text: `retention_cleanup` nulls `message_transcripts.text` at 365 days of the message's age (`RetentionCounts.transcripts_nulled`, in the retention audit entry), keeping the row and metadata and setting `erased_at`. The same erasure (`inbox/transcripts.py::erase_transcripts`) runs on a provider delete event, conversation erasure, customer erasure and account erasure. A transcript still `pending` at that moment becomes `failed` (`VOICE_SOURCE_GONE`) so a late job cannot store text. Conversation and customer exports include the transcript.
- **Docs:** `sub-processor-register.md` (OpenAI now also does speech-to-text on customers' voice; change record; the 30-day notice and an OpenAI speech-to-text retention/training confirmation are **pending**), `privacy-policy.md` (section 4 item and the retention table), `kvkk-aydinlatma-metni-template.md`, `security-and-privacy.md`, `mvp-scope.md` (new "Feature Phase 2" section with the F-03 row and the rule "approval mandatory for every transcript-based reply"), `environment-variables.md`, `.env.example`, `data-model.md`, `background-jobs.md`, `integrations.md`, `workflows.md` (R11 note), `observability.md` (audit catalog).

## 2. New contracts

**Settings** (all in `app/core/config.py`, documented in `environment-variables.md` and `.env.example`):
`TRANSCRIPTION_PROVIDER` (`auto` default | `off` | `fake` | `openai`; `auto` follows `LLM_PROVIDER`; production refuses `fake`; `openai` needs `OPENAI_API_KEY`), `TRANSCRIPTION_MODEL` (`gpt-4o-mini-transcribe`), `TRANSCRIPTION_MAX_AUDIO_BYTES` (10 485 760; at most 26 214 400), `TRANSCRIPTION_MAX_AUDIO_SECONDS` (120; at most 1 800), `TRANSCRIPTION_TIMEOUT_SECONDS` (60), `TRANSCRIPTION_DOWNLOAD_TIMEOUT_SECONDS` (20), `TRANSCRIPTION_MAX_PER_WORKSPACE_PER_DAY` (200). Property `Settings.transcription_backend`.

**Job:** `transcribe_voice_note`, payload `{message_id}`, dedup key `transcribe_voice_note:{message_id}`, max attempts 3, backoff 10 / 60 / 300 s, timeout 180 s.

**Table:** `message_transcripts` (above), migration `0049` (`down_revision = 0048`).

**Reason codes** (`message_transcripts.reason_code`, also in the audit entry): `VOICE_URL_MISSING`, `VOICE_URL_REFUSED`, `VOICE_EXPIRED`, `VOICE_DOWNLOAD_FAILED`, `VOICE_TOO_LARGE`, `VOICE_TOO_LONG`, `VOICE_UNSUPPORTED_TYPE`, `VOICE_EMPTY_AUDIO`, `VOICE_NO_SPEECH`, `VOICE_TRANSCRIPTION_REJECTED`, `VOICE_TRANSCRIPTION_UNAVAILABLE`, `VOICE_QUOTA_EXCEEDED`, `VOICE_SOURCE_GONE`.

**Audit actions** (no text in metadata; added to `activity/groups.py` "messages", both language catalogs and the observability catalog): `message.transcribed`, `message.transcription_failed`.

**No API change.** No endpoint, schema or frontend change.

## 3. Files

Backend, new: `app/integrations/transcription/{__init__,base,errors,audio,fetch,fake,openai_provider}.py`, `app/inbox/transcription.py`, `app/inbox/transcripts.py`, `migrations/versions/20261116_0049_message_transcripts.py`.
Backend, changed: `app/core/config.py`, `app/core/db.py` (`CATEGORY_C_TABLES`), `app/inbox/{models,payloads,processing}.py`, `app/handlers.py`, `app/integrations/instagram/webhook_format.py`, `app/demo/{simulator.py,scripts/customer_messages.yaml}`, `app/retention/cleanup.py`, `app/operations/data_rights.py`, `app/memory/service.py`, `app/activity/groups.py`, `app/core/i18n/{en,tr}.json`, `pyproject.toml` (one import-linter ignore line; the D-01 line was not touched).
Tests, new: `tests/unit/integrations/test_transcription.py` (47), `tests/integration/inbox/test_voice_transcription.py` (31), `tests/integration/retention/test_transcript_retention.py` (3), `tests/isolation/test_message_transcripts_isolation.py` (5), `tests/contract/fixtures/meta/webhook_voice_note.json`.
Tests, changed: `tests/contract/test_instagram_provider_contract.py` (+2 tests, +1 fixture case), `tests/contract/fixtures/meta/README.md`, `tests/unit/core/test_rls_policies.py` (56 to 57 tenant tables), `tests/integration/retention/test_retention.py` (batch test expects one more session: the new transcript sweep; 21 to 22).
Docs: listed in section 1, plus this report.

## 4. Checks (exact)

Environment for every backend run: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= DEMO_TOOLS_ENABLED=true OPENAI_API_KEY=` and `TEST_DATABASE_URL` = the `.env` value with the database name swapped. Databases `agentnest_p2s01_test` and `agentnest_p2s01_{a,b,c,d}_test` ran as parallel shards; **all five were dropped** (verified: none left). The full ~3,550-test suite was **not** run serially, as instructed.

| Command (from `backend/`) | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 694 files already formatted |
| `uv run mypy app` | Success, 369 files (none of the 5 earlier pre-existing errors present; none added) |
| `uv run lint-imports` | 23 kept, 0 broken |
| (a) my new/changed files: `tests/unit/integrations/test_transcription.py`, `tests/integration/inbox/test_voice_transcription.py`, `tests/isolation/test_message_transcripts_isolation.py`, `tests/integration/retention` (incl. the new file), `tests/contract`, `tests/unit/test_activity_templates.py` | 47 / 31 / 5 / 42 / 140 (+13 skipped live probes) / 5 passed |
| (b) shard A: `tests/unit tests/isolation tests/security tests/contract` | 2054 passed, 13 skipped, **2 failed** (environment, see below) |
| (c) shard B: `tests/integration/inbox` | **367 passed** |
| shard C: `tests/integration/{retention,jobs,activity,demo,integrations,operations}` | **236 passed** |
| shard D: `tests/integration/agent`, `tests/e2e`, `tests/integration/test_*.py` | 371 passed, **1 failed** (environment, see below) |

The three failures are not caused by this change:
- `tests/unit/core/test_deployment_workflow_and_rollback.py::test_cli_migration_status_head_only_and_check_config` and `tests/security/test_invite_secrets.py::test_the_invite_token_is_never_logged_audited_notified_or_queued` fail only because I exported `DEMO_TOOLS_ENABLED=true` (the production-config check refuses it; the log-capture test is affected the same way). Re-run with `DEMO_TOOLS_ENABLED=false` both **pass** (1 and 2 passed).
- `tests/integration/test_health_and_errors.py::test_cors_allows_only_the_frontend_origin` fails with no `access-control-allow-origin` header; it is the same test listed as failing at HEAD in the Feature Phase 1 Session 05 report (it reads the `.env` CORS setting). I did not touch CORS and did not re-run it at a baseline worktree.

Not run: the other integration directories not touching inbox processing, retention, erasure or jobs (`ai`, `approvals`, `commands`, `content`, `identity`, `knowledge`, `notifications`, `policy`, `reporting`), `tests/browser`, and the frontend suites (no frontend change).

## 5. Invariant notes

- **INV-01:** `message_transcripts` has `workspace_id NOT NULL`, a composite FK to `messages`, forced RLS and a tenant policy. Isolation tests: fail-closed without tenant context, no cross-workspace read/update/delete/insert, a transcript cannot point at a foreign message, constraints hold. There is no API route yet, so no foreign-ID 404 test applies.
- **INV-03:** the transcript is untrusted customer speech, labelled `source = "transcript"` in the schema, never a fact, never written to `messages.text`, and not read by any prompt in this session (tested: no LLM call sees it, the draft is unchanged). Injection handling (`ai/injection.py`) applies when Session 02 feeds it to a draft; it is not wired here because there is no consumer yet.
- **INV-06:** unique row per message, job dedup key, a finished or erased row is skipped: a duplicate webhook plus a re-run job produce one provider call (tested).
- **INV-09:** `is_simulated` copied from the account; mock accounts never touch the network.
- **INV-10:** no key anywhere; the signed URL is not logged or put in a job payload, error or audit entry (payload is `{message_id}` only).
- **INV-12:** each success and failure writes an audit entry in the same transaction as the state change.
- **INV-13/14:** failures are typed, recoverable and visible (dead job); the fake provider needs no credentials.
- **INV-17:** retention and erasure null the words only (the sanctioned privacy write); the row and metadata stay.
- **No external call inside a DB transaction:** tested by wrapping the fetcher and the provider and counting open transactions (0 at both calls). Time comes from `Clock` (`job.clock`), including the quota window.

## 6. Deviations, limitations and unverified items

- **Voice only; no UI, no drafting** (as briefed). Session 02 must also add the deterministic approval-forcing policy rule; Session 01 only records the rule in `mvp-scope.md`.
- **One transcript per message** (first audio attachment). A message with several audio attachments transcribes only the first.
- **Related table instead of a message column** (the brief allowed either). Consequence: five erasure paths call `erase_transcripts` (retention, delete event, conversation erasure, customer erasure, account erasure). Conversation erasure that deletes the messages removes the transcripts through the FK cascade.
- **Added beyond the brief:** a per-workspace daily cap (`TRANSCRIPTION_MAX_PER_WORKSPACE_PER_DAY`), because the provider call is paid and triggered by customer input; audit actions for success and failure; transcript in the data-subject export.
- **Duration cap is best effort.** Instagram does not state the duration in the webhook. It is read from MP4/M4A and WAV containers before the provider call; for other containers the byte cap is the only pre-call bound, and a duration the provider reports afterwards (only `whisper-1` does) discards the text (`VOICE_TOO_LONG`), after the call has been paid for. `gpt-4o*-transcribe` models report no duration, so for those an unknown-container clip is bounded by bytes only.
- **Unverified, pending:** (1) the real Instagram voice-note payload (type and `payload.url` are in Meta's examples; the CDN hosts, container format, content type and URL expiry are not; the host allowlist in `fetch.py` is a guess to confirm on the first real voice note); (2) the transcription model ID (`gpt-4o-mini-transcribe` appears in the installed OpenAI SDK 3.31.0 docstring; not confirmed on OpenAI's model page); (3) the adapter has only run against a stubbed HTTP transport, never the real API; (4) **transcription quality on real Turkish voice notes: pending** (the offline fixtures prove plumbing, not accuracy); (5) OpenAI's data retention and training terms for the speech-to-text endpoint, and the 30-day sub-processor notice, are pending before real voice notes are sent.
- The retention batch test (`test_more_than_1000_rows_are_removed_in_batches_of_1000`) hard-codes how many sessions the cleanup opens; I changed it from 21 to 22 for the new sweep. The Session 05 report listed this test as failing at HEAD with other counts; it passes now.
- Line endings: `processing.py`, `data_rights.py` and `webhook_format.py` had CRLF in the working tree and keep it; `.gitattributes` normalises to LF, so diffs are unaffected. New files use LF.

## 7. Handoff to Session 02

- Read the transcript from `message_transcripts` (`status = 'succeeded'`, `text`, `language`, `source = 'transcript'`). The row exists as `pending` from the moment the message is stored, so the draft path can tell "transcript on its way" from "none will come" (`failed`).
- **Race to design for:** `draft_reply` is queued with the 8 s debounce and the transcription job runs right after the message is stored, so the draft can run before the transcript is ready. Session 02 should make the draft wait (reschedule while the row is `pending`, bounded by the job's retry window) or re-draft when the transcript lands. Today the draft job does not look at the row.
- `erase_transcripts` and `export_transcripts` live in `inbox/transcripts.py`; any new place that nulls `messages.text` should call the first.
- Fake fixtures for the Turkish eval cases (`disfluent_tr`, `price_question_tr`, ...) are in `integrations/transcription/fake.py`; add fixtures there for the 10 to 15 eval transcripts.
- Open questions for the owner: (a) confirm the first real voice note's host and content type before relying on the allowlist; (b) decide whether Session 02 keeps the audio for a player (the Session 02 brief mentions one "if the media is kept"; this session deliberately keeps none, which also avoids a raw-audio retention rule); (c) confirm OpenAI's speech-to-text data terms before enabling `TRANSCRIPTION_PROVIDER=openai` for a pilot.
