# Feature Phase 4: Before Self-Service Launch

**Status:** Sessions 01 to 03 implemented and verified offline (2026-11-17); stopped for review; nothing is committed. Live Instagram behaviour is pending V-12, the website fetcher has only been exercised offline plus one manual public-site fetch, and the landing price is hidden until a price is settled. Close-out: [phase summary](../phase-summaries/features-phase-4-summary.md) and [s03-report.md](s03-report.md).
**Source:** [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4, step 4, plus D-06, which §4 left unplaced.
**Features:** F-09 (import facts from the Instagram profile and a website), D-06 (local package on the landing page).
**Sessions:** 3, in order.
**Related work outside this file:** self-service signup (P-10) and plans and quotas (P-11) are sessions 6–8 in [docs/review/sessions.md](../../review/sessions.md). Self-service launch needs both those and this phase. D-06 needs a settled TRY price (OQ-06 and the pricing document).

---

## 1. Plan

| Session | Feature | Scope | Main deliverables |
|:---:|---|---|---|
| 01 | F-09 | Import from the Instagram profile | Bio and recent captions turned into unverified candidates (contact buttons unavailable via documented API) |
| 02 | F-09 | Import from a website | SSRF-safe fetcher, HTML-to-text, candidates, onboarding UI for both imports |
| 03 | D-06 | Local package on the landing page, and phase close-out | Package section (Turkish, KVKK, TRY invoice, in-person setup), price display, phase summary |

## 2. Starting state

- Paste-to-extract exists: `backend/app/knowledge/extraction.py`, `POST /knowledge/extractions`, the AI task `backend/app/ai/tasks/extract_fact_candidates.py`, and the UI `frontend/src/features/knowledge/PasteExtractSheet.tsx`.
- `CANDIDATE_SOURCES` in `backend/app/knowledge/constants.py` already includes `instagram_profile`. Check whether anything produces it yet.
- Candidate review: `GET /fact-candidates`, `.../accept`, `.../reject`, and the UI `SuggestionsPage.tsx`.
- The Instagram provider abstraction is in `backend/app/integrations/instagram/` (`base.py`, `meta.py`, `mock.py`). The granted scopes include `instagram_business_basic`.
- The landing page is a separate Vite app in `landing/` (`src/copy.ts`, `App.tsx`), deployed as its own Railway service.
- "Website and profile import" is deferred in [mvp-scope.md](../../product/mvp-scope.md) §4.

## 3. Common working rules

Before each session, read [CLAUDE.md](../../../CLAUDE.md), [invariants.md](../../invariants.md), this file's common rules and the session brief, and the previous report in this folder.

1. **Preserve unrelated work.** Check `git status`, the migration head and uncommitted changes. Do not use `git stash`.
2. **Follow the invariants.** RLS, 404 for foreign IDs, no external calls in transactions, time from `Clock`, no secrets in logs.
3. **Imports never verify anything.** Every imported value is an unverified candidate with its source and a snippet as evidence. Only the owner verifies.
4. **Treat imported content as untrusted.** Imported text goes through injection handling before any model sees it.
5. **Update docs with contracts**, including `mvp-scope.md` and `docs/architecture/security-and-privacy.md` (SSRF).
6. **Ship both languages.**
7. **Do not commit, push or deploy** unless the user asks.

**Checks.** Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports && uv run pytest <paths>`. Frontend (and `landing/` for Session 03): `npm.cmd run lint && npm.cmd run typecheck && npm.cmd test && npm.cmd run i18n:check && npm.cmd run build`.

**Report.** Each session writes `sNN-report.md` in this folder.

---

## 4. Session briefs and prompts

### Session 01: Import from the Instagram profile (F-09, part 1)

**Goal.** Connecting the account produces a first set of fact candidates without the owner typing anything.

**Work**
- Update `mvp-scope.md` to move profile import (and, for Session 02, website import) out of Deferred.
- Add provider methods (meta and mock) that read the profile bio, website, contact fields and the last N captions with the existing grant. Confirm the fields in Meta docs and record them in `platform-capabilities.md`.
- Run an extraction job with source `instagram_profile` that reuses `extract_fact_candidates`. Each candidate keeps the snippet it came from. Deduplicate against existing facts and candidates.
- Trigger it once after the first account connection (idempotent), and from a "Re-import from Instagram" button.
- Captions often contain old prices. Label candidates from captions with the post date, and warn when the date is older than 90 days.
- Tests: mock provider fixtures, dedup, old-price warning, idempotency, isolation, and no auto-verification.

```text
Implement Feature Phase 4, Session 01 (import facts from the Instagram profile) from docs/implementation/features-phase-4-before-self-service/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's starting state and common rules, and the Session 01 brief first. Update mvp-scope.md, add provider methods (meta and mock) for bio, contact fields and recent captions, and run an idempotent extraction job with source instagram_profile that reuses extract_fact_candidates, keeps evidence snippets, deduplicates, and warns on old caption prices. Trigger it after first connection and from a re-import button. Nothing is ever auto-verified.

Run the checks, write s01-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 02: Import from a website (F-09, part 2)

**Goal.** The owner gives a website address and gets candidates to review, safely.

**Work**
- Build an SSRF-safe fetcher: `https` (and `http`) only; resolve DNS once and refuse private, loopback, link-local, metadata and reserved ranges for both IPv4 and IPv6; pin the resolved IP for the connection; at most 3 redirects, each re-checked; size cap (for example 2 MB); timeout; HTML content types only; no cookies or credentials. Put it in a shared module with thorough unit tests, including DNS rebinding and redirect-to-private cases.
- Fetch the home page and up to a few same-host pages that look relevant (prices, contact, about). Convert HTML to text, then run the same extraction with source `website` (add it to `CANDIDATE_SOURCES` with a migration if the check constraint needs it).
- Rate-limit per workspace, and audit each fetch (URL host only).
- Onboarding UI: an "Import from Instagram or website" step in `CreateWorkspaceWizard` and on the Knowledge page, with progress, and then the existing Suggestions review.
- Document the fetcher in `security-and-privacy.md` and the threat model.

```text
Implement Feature Phase 4, Session 02 (import facts from a website) from docs/implementation/features-phase-4-before-self-service/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 02 brief, s01-report.md and docs/operations/security-review-and-threat-model.md first. Build an SSRF-safe fetcher (blocked private, metadata and reserved ranges for IPv4 and IPv6, pinned IP, re-checked redirects, size and time caps) with thorough tests, extract candidates from a few same-host pages with source "website", rate-limit and audit, and add the import step to onboarding and the Knowledge page. Document it in the security docs.

Run the backend and frontend checks, write s02-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 03: Local package on the landing page, and phase close-out (D-06)

**Goal.** The landing page states the local offer clearly. The phase is closed.

**Gate.** Ask the user for the settled TRY price and tier names before writing them. If pricing is not settled, build the section with the price block behind a config value that is hidden when empty, and say so in the report.

**Work**
- Add a package section to `landing/src/` (copy in `copy.ts`, TR first, EN second) covering a Turkish interface and replies, KVKK documents ready (link to the privacy pages), a TRY invoice, in-person or video setup, and the verified-price guarantee from Phase 1.
- Every claim must be true at the time of writing. Check each one against the code and `docs/legal/`. Coordinate with P-19 (pricing document promises) in [pre-launch-problems.md](../../review/pre-launch-problems.md).
- Match the landing page's existing visual language, and check phone width.
- Phase close-out: run all checks (backend, frontend, landing), write `docs/implementation/phase-summaries/features-phase-4-summary.md`, and update `roadmap.md`. State whether P-10 and P-11 are done, since self-service launch depends on them.

```text
Implement Feature Phase 4, Session 03 (local package on the landing page and phase close-out) from docs/implementation/features-phase-4-before-self-service/sessions.md.

Read CLAUDE.md, the file's common rules, the Session 03 brief, s02-report.md, docs/product/pricing-and-unit-economics.md and P-19 in docs/review/pre-launch-problems.md first. Ask me for the settled TRY price before writing it; if there is none, hide the price block behind an empty config value. Add a TR-first package section to landing/ (Turkish product, KVKK documents, TRY invoice, in-person setup, verified-price guarantee), with every claim checked against the code and the legal docs.

Then close the phase: run all checks, write s03-report.md and docs/implementation/phase-summaries/features-phase-4-summary.md (including P-10 and P-11 status), update roadmap.md, and stop for review. Preserve unrelated work. Do not commit, push or deploy.
```
