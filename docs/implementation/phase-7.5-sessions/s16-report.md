# Session 16 report: Meta capability adapters

**Status: externally pending; independent offline scaffold implemented and verified.**
R75-01 through R75-06 remain unresolved. No new real comment capability is enabled.
G7.5-D and AC75-23 are not passed. No live account request, mutation, paid evaluation,
deployment, commit or push occurred.

## Baseline and scope

`main`, `156e734d2e46f9503a285a07a6cf5954de23c7c2`. Session 14/15 changes were
already in progress in the shared worktree and preserved. The commander explicitly
released independent Session 16 offline work while Session 15 completed its integration
prerequisite. This does not declare ordered integration acceptance complete.
No schema migration, generated API change, consent expansion or subscription change.

## Implementation and evidence

- `SyntheticMetaCommentProvider` requires an exact `httpx.MockTransport` and is never
  constructed by the runtime registry. It exercises provisional read/pagination,
  public reply, hide/unhide/delete and private-reply transport shapes using the existing
  fixed host, Bearer token handling, bounded cursors and typed errors.
- Source/media/account ownership checks precede mutation; private expiry and future
  timestamps reject. Seven days remains only the existing conservative mock assumption.
  Recipient identity is accepted only if explicitly returned, never inferred by handle.
- No remote idempotency is claimed for local operation keys. Lookup returns no evidence;
  an acknowledgement does not fabricate independent verified moderation state.
  Missing/malformed mutation success, timeout, gateway failure and a generic transient
  API flag produce unknown outcomes. Definitive rate/auth/permission rejection retains
  its typed meaning. The application operation ledger remains the execution boundary.
- The production Meta adapter rejects comment reads/effects/lookups. OAuth explicitly
  projects `comment_read`, `comment_reply`, `comment_moderate`, `comment_private_reply`
  false even with returned `instagram_business_manage_comments`. Requested scopes and
  canonical `/me` identity, encryption, reconnect and disconnect behavior are preserved.
  The real webhook parser continues rejecting synthetic comment events.
- `comments_synthetic_v1.json` is explicitly hand-authored on 2026-10-29, provisional
  v1, not a recording. Existing fixture provenance remains intact.
- The opt-in harness has exact media/comment target inputs and a separately selected
  effect. Its new cases remain evidence-gated off even with credentials. It never
  chooses arbitrary customer comments or automatically retries a mutation.
- Updated integrations, platform research, local-development and diagnostic-input docs.
  [Dated research evidence](../../research/meta-comments-session16.md) records inaccessible
  moderation/private URLs and HTTP 429 messaging/webhook pages, assumptions and remaining
  founder checks. No fresh primary contract text or authentic fixture was obtained.

| Capability | Offline evidence | Real status |
|---|---|---|
| Comment/media reads and pagination | Synthetic owner/source checks, malformed/loop/host safety | Disabled; R75-01/02/06 pending |
| Public reply | Synthetic request/ID and uncertainty taxonomy | Disabled; R75-01/03/06 pending |
| Hide/unhide/delete | Synthetic success shape; malformed response unknown, no invented readback | Disabled; R75-01/03/06 pending |
| Private reply | Synthetic source/deadline/response identity/timeout tests | Disabled; R75-01/04/05/06 pending |
| Real comment webhook/DM identity | Existing real parser stays closed | R75-02/05 pending |

## Verification

Windows PowerShell, Python 3.12 via `python -m uv`; synthetic HTTP transports only.
Both required live credential inputs were explicitly blanked for the test command.

From `backend/`:

```powershell
$env:META_LIVE_ACCESS_TOKEN = ''
$env:META_LIVE_IG_USER_ID = ''
python -m uv run pytest tests/unit/integrations/test_meta_comments.py tests/unit/integrations/test_meta_provider.py tests/unit/integrations/test_oauth_client.py tests/unit/integrations/test_meta_live_safety.py tests/contract/test_meta_live.py -q --tb=short
```

**214 passed, 10 intentionally skipped live probes**, final rerun 1.14 seconds. This includes
existing Meta transport/OAuth regressions, production capability refusal without
network requests, actual-grant closure, ownership, pagination, malformed reads/acks,
rate/permission errors, uncertainty, deadline expiry and harness safety. Initial run
had one synthetic handler dispatch error (198 passed/1 failed); corrected fixture
routing and clean reruns supersede it. No test result is live acceptance.

Final combined worktree checks passed: `python -m uv run ruff check .`,
`python -m uv run ruff format --check .` (560 files),
`python -m uv run mypy app evals` (297 source files), and
`python -m uv run lint-imports` (19 contracts kept, zero broken).
Targeted `mypy app/integrations/instagram` also passed, 13 source files.
Earlier combined checks caught Session 15 in-progress Ruff handler ordering,
`work_views` typing and a domain-to-API import chain; the owning agent corrected
them, and these clean final runs supersede those failures.
`git diff --check` passed (line-ending advisories only).

The operator ran `uv run pytest tests/integration/integrations/test_oauth.py -q --tb=short --maxfail=1`
inside the Python 3.12 test container, with both live credential inputs blank and
`TEST_DATABASE_URL` pointing to the separate disposable `agentnest_s16_backend_test`.
**19 passed** in 15.31 seconds, including the changed exact-capability-map assertion.
Full backend/frontend/E2E and real-model quality gates remain Session 17 work.

## Acceptance and handoff

Offline evidence supports AC75-16 uncertainty handling and AC75-19 adapter source
ownership checks; it does not prove full application acceptance or cross-surface
identity. AC75-11 and AC75-23 retain primary/live dependencies. Migration head remains
`0030`. No existing account is activated or granted authority.

Resume with readable official contracts and authenticated sanitized evidence per R75
item, then review endpoints/fields, actual grants/access/account types, pagination,
native changes, readback and errors. Replace provisional assumptions before enabling
real methods or expanding consent/subscriptions. Use separately authorized founder-owned
disposable targets. Session 18 must verify through application operations; a direct
adapter probe cannot substitute for that workflow or a phone owner walkthrough.

## Operator handoff

Offline implementation and final statics passed operator review, including the
OAuth database integration regression above. New real capabilities stay externally pending and disabled;
this report does not mark the requested live adapter capability set complete.
The operator removed the dedicated Session 16 test database after verification.
