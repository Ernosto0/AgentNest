# Feature Phase 2, Session 03: Image description for the owner (F-03, part 3)

**Status:** Implemented and verified offline (backend and frontend checks, section 5). Not committed. Stopped for review.
**Baseline:** `main` at `20a0551`, plus the uncommitted Session 01 and 02 work, the orchestrator's `data_rights.py` fix and the D-01 `pyproject.toml` line, all left intact. Worked in the main tree.
**Migration:** `0050` (`20261116_0050_image_descriptions.py`, `down_revision = "0049"`).
**Live provider / real device:** none used. No key, no network. Whether the configured model accepts images, the adapter's image request, and the real Instagram image payload and CDN hosts are **unverified** (section 6).

## 1. What was built

### The flow
1. **Request** (`inbox/image_description.py::request_image_descriptions`, called from `inbox/processing.py::_on_customer_message`, next to the voice-note request). For the first `IMAGE_DESCRIPTION_MAX_PER_MESSAGE` (3) attachments of `type: "image"` it inserts a `pending` `message_image_descriptions` row and enqueues `describe_message_image` (an insert, no external call). An image with no URL is `failed` (`IMAGE_URL_MISSING`) at once. Echoes are never described; `IMAGE_DESCRIPTION_ENABLED=false` creates nothing.
2. **Job** `describe_message_image` (three phases like `transcribe_voice_note`): [T1] read the row, message, workspace locale and the 24 h count, close the transaction; download the image and run the `describe_image` task through `ai.run_task`, **no transaction open**; [T3] lock the row, re-check the message is still there and not deleted (else `IMAGE_SOURCE_GONE`, nothing stored), clean and bound the text, screen it with `ai/injection.py`, store, audit. Permanent failures are recorded and the job succeeds; transient ones retry (10/60/300 s, 3 attempts) and the `on_dead` hook records the failure, so a dead job stays visible.
3. **The conversation is not touched.** No draft is requested or woken, no handling or attention state changes, nothing is sent. A photo with no words stays `needs_human` with `ATTACHMENT_ONLY` (R11), exactly as before. A photo with a typed question is drafted from the typed words alone.

### The `describe_image` task (tool-less vision task)
- `ai/tasks/describe_image.py`, prompt `prompts/describe_image/v1.md`, schemas `DescribeImageInput` / `ImageDescription` in `ai/schemas.py`. Output: `looks_like` (`product | price_screenshot | location | other`), `description` (<= 500 chars), `visible_text` (<= 1 500 chars). One repair call on invalid output, like every task.
- The LLM abstraction gained **images**: `LLMImage` and `LLMMessage.images` (`integrations/llm/base.py`); the OpenAI adapter sends them as `input_image` data URLs in the one user turn (`store=false`, no tools). Nothing else about other tasks changed.
- `TaskDefinition.store_output` (new, default true; `ai/runner.py`): `describe_image` sets it false, so the validated output is **not** copied into `agent_runs.output`. The one stored copy of the words is the one retention and erasure reach. The run keeps status, usage, prompt version and a snapshot of sizes only.
- Fake model: reads fixture images only and returns the fixture's description in the workspace locale; a real picture raises `LLMConfigError` (it never invents what a photo shows).
- Model: `LLM_MODEL_DESCRIBE_IMAGE` (empty = default). Counts against the shared daily LLM budget and its own per-workspace daily cap.

### Image download (`app/integrations/vision/`)
No provider interface (describing is an LLM task); only the bytes. `HttpsImageFetcher` applies the voice-note rules (https only, no credentials, port 443, Instagram/Facebook CDN host allowlist reused from `transcription/fetch.py`, public addresses only, no redirects, no cookies or proxy, **no Authorization header**, size cap by `Content-Length` and while streaming, content type and signature check, total deadline, URL never logged). Accepts JPEG, PNG, WebP (an animated GIF is refused; a declared type that disagrees with the signature is refused). `FixtureImageFetcher` serves `mock-image://<fixture>` for mock accounts (fixtures `price_screenshot_tr`, `product_photo`, `location_pin`, `blurry`, `injection_text`; failures `expired`, `unreachable`, `oversize`, `notimage`). `override_vision(...)` for tests.

### Storage: new table `message_image_descriptions` (migration `0050`)
Columns: `id`, `workspace_id`, `message_id` (composite FK to `messages`, cascade; unique `(workspace_id, message_id, attachment_index)`), `attachment_index`, `status` (`pending|succeeded|failed`), `reason_code` (required exactly when failed), `source` (`image_description`, check-constrained), `looks_like` (checked set), `description`, `visible_text`, `injection_suspected`, `provider`, `model`, `media_type`, `image_bytes`, `agent_run_id` (no FK), `is_simulated`, `completed_at`, `erased_at`, timestamps. RLS enabled and forced, tenant policy, role grants like 0046/0048/0049. Added to `CATEGORY_C_TABLES` (58 tables). The same migration lets `agent_runs.task` hold `describe_image` (check constraint replaced; downgrade removes those rows first). The unique constraint has an explicit short name (the convention name would exceed 63 characters).

### Retention, erasure, privacy
- **The image is never stored** (memory only), so there is no raw-image retention rule.
- Description and visible text follow message text: `retention_cleanup` nulls them at 365 days of the message's age (`RetentionCounts.image_descriptions_nulled`, in the retention audit entry), keeps the row and metadata, sets `erased_at`. `inbox/image_erasure.py::erase_image_descriptions` runs on a provider delete event (`processing.py`), conversation erasure, customer erasure (`data_rights.py`), account erasure (`memory/service.py`); a `pending` row becomes `failed` (`IMAGE_SOURCE_GONE`) so a late job stores nothing. Conversation and customer exports include `image_descriptions` per message.
- **Docs:** `sub-processor-register.md` (OpenAI now also receives customer images; change record; 30-day notice and image-input retention/no-training confirmation **pending**), `privacy-policy.md` (section 4 item 3b, retention table), `kvkk-aydinlatma-metni-template.md`, `security-and-privacy.md`, `mvp-scope.md`, `environment-variables.md`, `.env.example`, `data-model.md`, `background-jobs.md`, `integrations.md`, `agent-runtime.md` (section 6a), `workflows.md` (R11 note), `api-design.md`, `observability.md`.

### Decision: no pre-filled suggested reply
Recorded as brief and orchestrator asked: **not pre-filled**, not even when the description matches a verified fact. The conversation stays `human_required` (`ATTACHMENT_ONLY`), the draft path never reads the table, and the draft model is not even called for an image-only message (tested). A picture is a weak basis for an answer, a price screenshot may be a competitor's, and nothing in the offline setup can measure accuracy. Revisit with measured quality.

### Untrusted text handling (INV-02, INV-03)
Description and visible text are customer content a model read. They are screened with `detect_injection` (match = `injection_suspected`, shown to the owner as a warning, nothing else changes), cleaned (control characters removed, bounded), shown as plain text (React-escaped, tested with an `<img onerror>` payload), never put in a prompt, never a fact (tested: no `business_facts` or fact candidate is created from a price in a screenshot; a later draft call contains none of the words), never an instruction. The prompt tells the model the same and forbids naming or identifying people.

## 2. New contracts

- **Settings** (`core/config.py`, documented in `environment-variables.md` and `.env.example`, parity tested): `IMAGE_DESCRIPTION_ENABLED` (true), `IMAGE_DESCRIPTION_MAX_BYTES` (5 242 880; <= 20 971 520), `IMAGE_DESCRIPTION_DOWNLOAD_TIMEOUT_SECONDS` (20), `IMAGE_DESCRIPTION_MAX_PER_MESSAGE` (3; 1 to 10), `IMAGE_DESCRIPTION_MAX_PER_WORKSPACE_PER_DAY` (100), `LLM_MODEL_DESCRIBE_IMAGE` (empty = default; task override `describe_image`).
- **Job:** `describe_message_image`, payload `{message_id, attachment_index}`, dedup key `describe_message_image:{message_id}:{attachment_index}`, 3 attempts, backoff 10/60/300 s, lease 240 s.
- **Table / migration:** `message_image_descriptions`, `0050`; `agent_runs.task` gains `describe_image`.
- **LLM task and prompt:** `describe_image` v1. `LLMImage`, `LLMMessage.images`, `TaskDefinition.store_output`.
- **API (patched into `frontend/openapi.json`, only `ImageDescriptionOut` and `MessageOut` changed; `schema.d.ts` regenerated, +67 lines):** `MessageOut.image_descriptions: ImageDescriptionOut[]` = `{attachment_index, status, looks_like|null, description|null, visible_text|null, injection_suspected, reason_code|null}`. No path changed, no image URL added.
- **Reason codes:** `IMAGE_URL_MISSING`, `IMAGE_URL_REFUSED`, `IMAGE_EXPIRED`, `IMAGE_DOWNLOAD_FAILED`, `IMAGE_TOO_LARGE`, `IMAGE_UNSUPPORTED_TYPE`, `IMAGE_EMPTY`, `IMAGE_DESCRIPTION_REJECTED`, `IMAGE_DESCRIPTION_UNAVAILABLE`, `IMAGE_QUOTA_EXCEEDED`, `IMAGE_SOURCE_GONE`.
- **Audit actions** (no text; in `activity/groups.py`, both language catalogs, observability): `message.image_described`, `message.image_description_failed`.
- **Retention counter:** `RetentionCounts.image_descriptions_nulled`.
- **Demo:** `photo_only` now uses `mock-image://product_photo`; new `price_screenshot` script; `simulator.image_attachment(fixture)`.
- **UI strings** (tr and en, `convo.imageDescription.*`, 11 reason strings, 4 kinds): the block is titled "What the customer sent (automatic)" / "Müşterinin gönderdiği (otomatik)".

## 3. Files

Backend, new: `app/integrations/vision/{__init__,base,errors,images,fetch,fake}.py`, `app/ai/tasks/describe_image.py`, `app/ai/prompts/describe_image/v1.md`, `app/inbox/image_description.py`, `app/inbox/image_erasure.py`, `migrations/versions/20261116_0050_image_descriptions.py`.
Backend, changed: `app/core/config.py`, `app/core/db.py`, `app/ai/{models,runner,schemas}.py`, `app/integrations/llm/{base,__init__,openai_provider}.py`, `app/inbox/{models,payloads,processing,schemas,views,router}.py`, `app/handlers.py`, `app/retention/cleanup.py`, `app/operations/data_rights.py`, `app/memory/service.py`, `app/activity/groups.py`, `app/core/i18n/{en,tr}.json`, `app/demo/{simulator.py,scripts/customer_messages.yaml}`. (`pyproject.toml` untouched: no new import-linter exception was needed.)
Tests, new: `tests/unit/integrations/test_vision.py` (40), `tests/integration/inbox/test_image_description.py` (41), `tests/integration/retention/test_image_description_retention.py` (4), `tests/isolation/test_message_image_descriptions_isolation.py` (6).
Tests, changed: `tests/unit/core/test_rls_policies.py` (57 to 58 tables), `tests/integration/retention/test_retention.py` (session count 3+19 to 3+20: the new sweep).
Frontend: new `src/features/inbox/ImageDescriptionBlock.tsx`; changed `openapi.json`, `src/api/schema.d.ts`, `src/features/inbox/{ConversationPage.tsx,inbox.test.tsx}` (+8 tests), `src/i18n/locales/{en,tr}/inbox.json`.
Docs: listed in section 1, plus this report.

## 4. Invariant notes

- **INV-01:** `workspace_id NOT NULL`, composite FK to `messages`, forced RLS, tenant policy; isolation tests (fail closed, no cross-workspace read/update/delete/insert, FK to a foreign message refused, constraints, read/export helpers with a foreign workspace). The data is read only through the conversation route (foreign ID is a 404, tested).
- **INV-02 / INV-03 / INV-04:** the words are never a fact, a candidate or an instruction; injection screened; no draft or send path reads them; the task has no tools and its output has no actionable field.
- **INV-06:** unique row per image, job dedup key, finished or erased rows skipped: a duplicate webhook plus a re-run job make one model call (tested).
- **INV-09:** `is_simulated` copied; mock accounts only read `mock-image://` fixtures.
- **INV-10:** no key; the signed URL is not in a payload, log, error or audit entry (tested for payload and audit).
- **INV-12:** each success and failure audits in the same transaction as the state change, without text.
- **INV-13/14:** typed, recoverable, visible failures; the fake model needs no credentials.
- **INV-17:** retention and erasure null the words only.
- **No external call inside a transaction:** tested by wrapping the fetcher and the model and counting open transactions (0 at both). Time comes from `Clock`.

## 5. Checks (exact)

Backend env for every run: `LLM_PROVIDER=fake INSTAGRAM_ENABLED_PROVIDERS=mock MEDIA_STORAGE_BACKEND=local SENTRY_DSN= OPENAI_API_KEY= PYTHONUTF8=1`, `TEST_DATABASE_URL` = the `.env` value with the database name `pivoris_p2s03_test` (and `_a_`, `_b_`, `_c_` for shards). `DEMO_TOOLS_ENABLED=true` only where stated. The full ~3,600-test suite was not run serially.

| Command (from `backend/`) | Result |
|---|---|
| `uv run ruff check .` / `ruff format --check .` | All checks passed / 714 files already formatted |
| `uv run mypy app` | Success, 379 source files |
| `uv run lint-imports` | 23 kept, 0 broken |
| New tests: `tests/unit/integrations/test_vision.py`, `tests/integration/inbox/test_image_description.py`, `tests/integration/retention/test_image_description_retention.py`, `tests/isolation/test_message_image_descriptions_isolation.py` | 40 + 41 + 4 + 6, all pass |
| Shard A: `tests/unit tests/isolation tests/security tests/contract` | 2136 passed, 13 skipped, 4 failed, all environment (below); the 4 re-run: dev-route tests with `DEMO_TOOLS_ENABLED=true` 13 passed, `test_invite_secrets.py` alone 2 passed |
| Shard B: `DEMO_TOOLS_ENABLED=true tests/integration/inbox` | 436 passed, 1 failed (a test of mine, ordering on a frozen clock; fixed, then passed) |
| Shard C: `tests/integration/{retention,jobs,activity,operations,agent,ai,policy,approvals}` | 554 passed, 1 failed (`test_retention.py` session count, updated to 3+20; then 5 passed) |
| `DEMO_TOOLS_ENABLED=true tests/integration/{demo,integrations,knowledge,notifications}` | 267 passed |
| Frontend from PowerShell: `npm.cmd run lint` / `typecheck` / `i18n:check` / `test` / `build` | pass / pass / pass (en, tr, 2484 keys) / **52 files, 799 tests passed** (+8 new) / built |

Environment failures in shard A (not caused by this change): `tests/isolation/test_channel_links_isolation.py::test_channel_link_codes_tenant_scoping`, `test_phase6_isolation.py::test_the_dev_job_listing_of_a_never_shows_the_jobs_of_b` and `test_publishing_isolation.py::test_the_simulator_listing_of_a_never_shows_what_b_published` need `DEMO_TOOLS_ENABLED=true` (they pass with it); `tests/security/test_invite_secrets.py::...never_logged_audited_notified_or_queued` fails in the combined run (log-capture order dependence, as in the Session 01 and 02 reports) and passes alone.
Not run: `tests/e2e`, `tests/browser`, Playwright, `tests/integration/{commands,content,identity,reporting}`, top-level `tests/integration/test_*.py`, the eval harness (no image dataset was added).

### 5a. Remaining integration directories
`DEMO_TOOLS_ENABLED=true pytest tests/integration/demo tests/integration/integrations tests/integration/knowledge tests/integration/notifications`: **267 passed** (db `a`).

## 6. Deviations, limitations and unverified items

- **Not pre-filled** (decision above). The conversation, handling mode and attention are untouched.
- **Up to 3 images per message** are described (setting); later ones get no row and show only "Photo or file".
- **Images are not shown.** The picture is not stored and no image URL is added to the API, so "under the image" means under the "Photo or file" line; the owner opens the picture in Instagram.
- **Added beyond the brief:** per-workspace daily image cap and per-message cap, `IMAGE_DESCRIPTION_ENABLED`, `LLM_MODEL_DESCRIBE_IMAGE`, `store_output` on the runner (so the words have one erasable copy), audit actions, data-subject export.
- **Photo with typed text:** drafted from the text only, as before; the model does not see the picture. The description is not used, so a question "is this price right?" about a picture is answered (or escalated) without it. Left as is; a person approves in the usual way.
- **The account agent** (Phase 7.5) still sees `[attachment: image]` only and does not read descriptions.
- **Unverified, pending:** (1) the real Instagram image payload, CDN hosts and URL lifetime (the host allowlist is reused from voice notes and is a guess; messaging attachment URLs may also need a different host); (2) whether `gpt-6-luna` (the default) accepts image input, and the `input_image` request shape and strict structured output with an image: the adapter ran only against a stubbed transport, never the real API; (3) description quality on real Turkish screenshots and photos, and how often visible text is misread: **pending**, there is no image eval set; (4) OpenAI's data-retention and no-training terms for image inputs and the 30-day sub-processor notice, **pending before real customer images are sent**; (5) the model may still describe a person despite the prompt; the injection flag only catches known phrasings.
- Line endings: `processing.py` and `runner.py` keep CRLF; new files use LF.

## 7. Open questions for the owner

1. Should a later session pre-fill a suggested reply when a description matches a verified fact (needs an eval set with real screenshots first)?
2. Show the picture itself in the inbox (needs short-lived proxying of the signed Instagram URL, or storage with a retention rule)?
3. Should a typed message with a photo always go to a person, since the draft model cannot see the picture?
4. Confirm the first real image's host and content type, and the model that will be used for `LLM_MODEL_DESCRIBE_IMAGE`.
5. Is 3 images per message and 100 images per workspace per day right for a pilot?
