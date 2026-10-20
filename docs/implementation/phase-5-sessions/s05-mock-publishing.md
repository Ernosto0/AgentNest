# Session 5: Mock publishing (containers, publish, quota, failure modes)

**Plan:** `plan.md` §2 **G3, G4, G18**, §3 **P5-05**. **Depends on:** session 4 (migration numbering: this session adds 0010 and 0011). **Commit:** `P5-05: …`.

## Read first
`integrations.md` §3.2, §3.3, §3.6, `ADR-011`, `ADR-015`, `backend/app/integrations/instagram/{base,mock,models,registry}.py`, the existing provider contract tests, `demo/dev_router.py`, `unit/test_side_effect_calls.py`.

## Build
- Migration **0010** `sim_containers`, `sim_published_media` (`unique(container_id)`).
- `MockInstagramProvider` receives a `MediaStorage` from the registry (G3). Methods:
  - `create_media_container`: reads the JPEG via storage and checks magic bytes; status `IN_PROGRESS`, `ready_at = now + SIM_CONTAINER_DELAY_SECONDS`, `expires_at = now + 24 h`. Stories use `ContainerSpec(STORIES, caption=None)` (G5).
  - `get_container_status`: `IN_PROGRESS` → `FINISHED` after the delay; `EXPIRED` after 24 h; `PUBLISHED`; `ERROR`.
  - `publish_container`: requires `FINISHED`; duplicate publish is a DB error → `ProviderInvalidRequest`.
  - `get_media`: permalink `https://instagram.example/sim/{id}`.
  - `get_publishing_quota`: last 24 h against `PUBLISH_DAILY_LIMIT`.
  - Failure modes (G18): `create_container` `invalid_media` → `ProviderInvalidRequest(MEDIA_REJECTED)`; `container_status` `invalid_media` → `ERROR`; `publish` `timeout_after_success` publishes then raises `ProviderOutcomeUnknown`; `transient`, `rate_limited`, `auth_revoked` apply to all three.
  - New settings `SIM_CONTAINER_DELAY_SECONDS` (2), `PUBLISH_DAILY_LIMIT` (50).
- Migration **0011** (G4): `MOCK_CAPABILITIES = {messaging, publish_feed_image, publish_story_image}`; rewrite existing mock rows; update frontend capability labels if present.
- Dev panel: failure-rule operations gain `create_container`, `container_status`, `publish`. Read-only `GET /dev/workspaces/{ws}/simulator/published` listing `sim_published_media`.
- Contract tests: replace the `NotImplementedError` assertions with the real lifecycle, double publish, expiry and each failure mode. Time via `FrozenClock`.
- Docs: integrations §3.2/§3.3 (G3, G4, G18), environment-variables, `.env.example`.

## Done when
- Contract tests cover: lifecycle IN_PROGRESS→FINISHED→PUBLISHED, publish before FINISHED rejected, double publish rejected, expiry after 24 h, quota counts, all five failure modes on the three operations.
- `test_side_effect_calls.py` still passes (side-effect calls only from allowed modules).
- Existing mock-account rows migrated; all checks green.
