# Session 8: Content impact handlers (fact change holds)

**Plan:** `plan.md` §2 **G14**, §3 **P5-07**. **Depends on:** session 7. **Commit:** `P5-07: …`.

## Read first
`workflows.md` §E (fact-change step) and the knowledge fact-change flow (Phase 3 `knowledge` impact handlers and the `ImpactHandler`/`Referrers` registry), `state-machines.md` §5, Phase 3 summary D7 (`knowledge.fact_changed` skips the changer).

## Build
`content/impact_handlers.py` `ContentItemReferrers` (`count` + `apply_change`), registered at startup via `app/handlers.py`:
- `scheduled` / `retry_scheduled` → `on_hold (FACT_CHANGED)`; cancel the approval; cancel the queued job and the waiting op (via `content/hooks.py`); emit `content.on_hold` (attention) to `content.approve` holders **including the changer** (G14, AC-C4).
- `pending_approval` → `draft` with `hold_reason=FACT_CHANGED`, approval cancelled.
- `draft` → `validation.stale = true`.
- `published` and `publishing` untouched (`publishing` is already in flight; document this).
- Sweep: items in those states whose caption or overlay contains the **old display string** count as referencing even without a `fact_references` row.
- Impact counts feed the command confirmation card (the fact-update confirmation already shows referrers; add the content count).
- Docs: workflows §E / §D impact text, observability (notification kind).

## Done when
- Tests: AC-C4 `test_fact_impact.py` (price change by command → scheduled post `on_hold`, approval cancelled, job gone, notification to the changer); pending → draft; draft → stale; published untouched; string-sweep catches a caption without a reference row; workspace isolation.
- Re-approve after hold fails validation if the caption still shows the old price (G2 behaviour, covered by one test).
- All checks green.
