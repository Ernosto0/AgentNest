# Feature Phase 3: After App Review

**Status:** Planned. Nothing in this file is implemented yet.
**Source:** [pre-launch-feature-recommendations.md](../../review/pre-launch-feature-recommendations.md) §4, step 3.
**Features:** F-05 (comment-to-DM on real accounts), F-07 (story and post template images).
**Sessions:** 4. Track A (sessions 01–02) and Track B (sessions 03–04) are independent. Track B can start before App Review finishes.
**Gate for Track A:** the comment permission has been granted in Meta App Review, or at least is available in development mode on a test account. P-05 in [docs/review/sessions.md](../../review/sessions.md) (session 2 there) may already have added the OAuth scope; check its status line in [pre-launch-problems.md](../../review/pre-launch-problems.md) first.

---

## 1. Plan

| Session | Feature | Scope | Main deliverables |
|:---:|---|---|---|
| 01 | F-05 | Close the research items and request the permission | R75-01 to R75-06 answered or explicitly carried forward, comment scope in OAuth, capability mapping, App Review package |
| 02 | F-05 | Enable on real accounts | Capability flag per account, verified-answer private reply, live probe harness, rollout runbook |
| 03 | F-07 | Template image renderer | Workspace brand settings, 3–4 deterministic Pillow templates filled from verified facts |
| 04 | F-07 | Template images in the content flow, and phase close-out | Template picker in content creation, price-change hold applied to images, phase summary |

## 2. Starting state

- OAuth scopes are in `backend/app/integrations/instagram/oauth.py` (`SCOPES`). There is no comment scope, and the capability map at around line 70 has no comment capability.
- Comment handling is built and tested against the mock provider: `backend/app/comments/` (`private_reply.py`, `service.py`, `reservations.py`), `backend/app/operations/private_reply.py`, `public_comments.py`, `manual_comments.py`, `backend/app/integrations/instagram/meta_comments.py`.
- The research items R75-01 to R75-06 are described in `docs/implementation/phase-7.5-sessions/` (s01, s10, s11) and `docs/architecture/integrations.md`.
- `docs/operations/meta-app-review-package.md` and `docs/operations/account-agent-rollout.md` exist.
- Content types are `feed_image` and `story_image` only (`backend/app/content/models.py`). The price-change hold logic is in `backend/app/content/impact_handlers.py` and `backend/app/knowledge/impact.py`.
- Pillow is already a backend dependency. The workspace model has no brand colour or logo fields.
- "Real-account comment automation" and "Story/post image generation" are deferred in [mvp-scope.md](../../product/mvp-scope.md) §4. Each track's first session updates that document.

## 3. Common working rules

Before each session, read [CLAUDE.md](../../../CLAUDE.md), [invariants.md](../../invariants.md), this file's common rules and the session brief, and the previous report in this folder.

1. **Preserve unrelated work.** Check `git status`, the migration head and uncommitted changes first. Do not use `git stash`.
2. **Follow the invariants.** RLS on new tenant tables. External effects only through the `operations` ledger, with reconciliation before retry. Never auto-resend an ambiguous message. No external calls in transactions. Time from `Clock`.
3. **Check capabilities against what Meta granted.** A feature is enabled only when the account's `granted_scopes` include the permission and the capability flag is on. Mock behaviour never counts as live evidence.
4. **Keep facts the only source.** Prices and other values in private replies and template images come only from verified facts.
5. **Update docs with contracts**, including `mvp-scope.md`, `integrations.md`, `platform-capabilities.md`, the App Review package and the env var docs.
6. **Ship both languages.**
7. **Report truthfully.** Live comment results are "pending" until recorded on a real account, with evidence stored the way earlier phases stored it.
8. **Do not commit, push, submit App Review or send live messages** unless the user asks.

**Checks.** Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run lint-imports && uv run pytest <paths>`. Frontend: `npm.cmd run lint && npm.cmd run typecheck && npm.cmd test && npm.cmd run i18n:check && npm.cmd run build`.

**Report.** Each session writes `sNN-report.md` in this folder.

---

## 4. Session briefs and prompts

### Session 01: Close the research items and request the permission (F-05, part 1)

**Goal.** Everything needed for comment-to-DM on a real account is known, requested and documented.

**Work**
- Read R75-01 to R75-06. For each, record the answer with a source (Meta docs URL and date, or a test on the dev-mode account), or mark it "carried forward" with the reason. Write them in `docs/research/platform-capabilities.md`.
- Check P-05's status. If the scope is not added yet, add the comment-management permission to `SCOPES`, add a `comments` or `private_reply` capability to the capability map, and make sure existing connected accounts show "reconnect to enable comments", without breaking them.
- Update `meta-app-review-package.md` with the permission, the use-case description, the screencast script and the test steps.
- Update `mvp-scope.md` to move real-account comment automation out of Deferred, with its gate.
- Tests: capability mapping with and without the scope, and the reconnect prompt state.

```text
Implement Feature Phase 3, Session 01 (close comment research and request the permission) from docs/implementation/features-phase-3-after-app-review/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's starting state and common rules, the Session 01 brief, P-05 in docs/review/pre-launch-problems.md, and the R75 items in docs/implementation/phase-7.5-sessions/ first. Answer or explicitly carry forward R75-01 to R75-06 with sources, add the comment permission and capability if P-05 has not, show a reconnect prompt for existing accounts, and update the App Review package and mvp-scope.md.

Run the checks, write s01-report.md in the same folder, and stop. Preserve unrelated work. Do not commit, push or submit App Review.
```

---

### Session 02: Enable on real accounts (F-05, part 2)

**Goal.** On an account that has the permission and the flag, a comment like "price?" gets a private reply with the verified answer.

**Depends on.** Session 01, plus the permission available on at least a dev-mode test account.

**Work**
- Wire the real Meta provider for comment webhooks and private replies in `meta_comments.py`, using what Session 01 confirmed. Keep the mock path unchanged.
- Add a per-account capability flag (default off) and an owner setting to turn it on. Show the permission state in Connections.
- The private reply uses the existing draft and claim-validator path, so the verified price goes in through a placeholder. Approval is required by default, and the delegation ladder applies.
- Enforce Meta's one-private-reply-per-comment and time-window rules deterministically, with reason codes, and test them.
- Add an optional live probe harness (pytest marker, skipped without credentials), like the Telegram one.
- Add a rollout section to `account-agent-rollout.md`.

```text
Implement Feature Phase 3, Session 02 (comment-to-DM on real accounts) from docs/implementation/features-phase-3-after-app-review/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 02 brief and s01-report.md first. Wire the real Meta comment webhook and private-reply path behind a per-account flag that is off by default, use the existing draft, claim-validator and approval path for the verified answer, enforce Meta's private-reply limits deterministically, add a skipped-by-default live probe harness, and document the rollout.

Run the checks, write s02-report.md in the same folder (live results marked pending unless actually recorded), and stop. Preserve unrelated work. Do not commit, push or send live messages.
```

---

### Session 03: Template image renderer (F-07, part 1)

**Goal.** The server can render simple branded cards from verified facts.

**Work**
- Update `mvp-scope.md` to move template cards (not AI image generation) out of Deferred.
- Add workspace brand settings in a migration: a primary and an accent colour, and a logo media ID, using the existing media storage. Add an API and a small Settings UI.
- Add a renderer module (for example `backend/app/content/templates/`) with 3–4 deterministic templates: price card, opening hours card, "this week's classes" or services list, and a simple announcement. Use Pillow with bundled open-licence fonts that support Turkish characters, at 1080×1920 for stories and 1080×1350 for feed.
- Templates take typed inputs. Fact-backed fields reference fact keys, not raw values. Rendering resolves the facts at render time and records which fact versions it used.
- Output goes through the existing media validation and storage.
- Tests: golden-image or hash tests per template, Turkish characters, long text wrapping and truncation, a missing fact (render refused with a reason), and isolation.

```text
Implement Feature Phase 3, Session 03 (template image renderer) from docs/implementation/features-phase-3-after-app-review/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules and the Session 03 brief first. Update mvp-scope.md, add workspace brand settings (colours, logo) with a migration, API and Settings UI, and build 3–4 deterministic Pillow templates (story and feed sizes, Turkish-capable fonts) whose fact-backed fields resolve verified facts at render time and record the fact versions used. Output goes through existing media validation and storage.

Run the backend and frontend checks, write s03-report.md in the same folder, and stop. Preserve unrelated work. Do not commit or push.
```

---

### Session 04: Template images in the content flow, and phase close-out (F-07, part 2)

**Goal.** The daily story prompt can produce a ready image, and a price change holds it like any other content.

**Work**
- Add "Make an image from a template" next to Upload in content creation and on the Today screen story prompt. Show a live preview, then save as a normal draft with media.
- Link the content item to the fact versions it used, so `impact_handlers.py` holds the scheduled item when one of those facts changes. Offer "re-render with the new value", which creates a new version that needs approval again.
- Add a command: "make a price card for monthly membership".
- Phase close-out: run all checks, write `docs/implementation/phase-summaries/features-phase-3-summary.md`, and update `roadmap.md`. Comment live evidence stays pending unless recorded.

```text
Implement Feature Phase 3, Session 04 (template images in the content flow and phase close-out) from docs/implementation/features-phase-3-after-app-review/sessions.md.

Read CLAUDE.md, docs/invariants.md, the file's common rules, the Session 04 brief and s03-report.md first. Add a template picker with preview to content creation and the Today story prompt, link rendered content to the fact versions it used so price changes hold it, offer a re-render that needs approval again, and add a "make a price card" command.

Then close the phase: run all checks, write s04-report.md and docs/implementation/phase-summaries/features-phase-3-summary.md, update roadmap.md, and stop for review. Preserve unrelated work. Do not commit or push.
```
