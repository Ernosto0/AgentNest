# Session 4: Content model, transitions and CRUD

**Plan:** `plan.md` §2 **G1, G2, G6, G7 (column only), G15**, §3 **P5-02**. **Depends on:** session 3. **Commit:** `P5-02: …`.

## Read first
`state-machines.md` §5 (and §6), `data-model.md` §3.6, `api-design.md` §2.7, `workflows.md` §E, `docs/invariants.md` (INV-17 published immutable), existing `approvals` and `jobs.queue` code, an existing transitions module (`commands/transitions.py`) as the style template.

## Build
- Migration **0009** `content_items`: data-model §3.6 plus `client_request_id` with `unique (workspace_id, created_by_user_id, client_request_id)`; composite FKs to the account, media and approval; index `(workspace_id, status, scheduled_at)`. Add the content-item FKs the plan lists on other tables.
- `content/models.py`, `schemas.py`, `views.py`.
- `content/transitions.apply(item, event, **ctx)`: the full §5 table **plus G1** (`draft → cancelled`, `pending_approval → cancelled`, `retry_scheduled → on_hold`, `publishing → on_hold (ACCOUNT_UNAVAILABLE)`). Conditional update on the expected status; audit every transition; anything else → `CONFLICT_STATE`. This is the only way status changes.
- `jobs.queue.cancel_queued(session, dedup_key)` helper.
- `content/service.create_draft` / `update`:
  - `expected_version` mismatch → `VERSION_CONFLICT`.
  - Any payload change → version+1, re-validate, replace `fact_references` (G6: references from values matching verified facts, the manual-reply matcher).
  - Edit from `pending_approval`/`scheduled`/`on_hold`/`rejected`/`failed` → `draft` + `cancel_for_subject(SUBJECT_EDITED)` + `cancel_queued` for the publish job.
  - `published` → 409.
- Routes: list with tab filters (G15 mapping), get, create, patch, validate. Register in `api/router.py`; add the import contracts (plan §1).
- `content/hooks.py` skeleton (startup-registered hook used later by cancel/hold to reach the ledger; no `operations` import).
- Docs: state-machines §5 (G1, G2), data-model §3.6 (G7 column), api-design §2.7.

## Done when
- Unit tests: every allowed transition and the key forbidden ones (incl. from `published`); published immutable (INV-17).
- Integration: AC-D6 edit-after-approval returns the item to `draft` and cancels the approval; `VERSION_CONFLICT`; tab filters; workspace isolation (foreign item id → 404).
- All backend checks green including `lint-imports`.
