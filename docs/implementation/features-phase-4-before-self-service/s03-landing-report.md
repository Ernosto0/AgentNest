# Feature Phase 4, Session 03 (landing part): local package section (D-06)

- **Status:** done for the landing section. The phase close-out (summary, roadmap, P-10 and P-11 status) is not part of this report.
- **Baseline commit:** `e2fcc23`. No backend change, no migration.
- **Who wrote it:** Sonnet 5.5 directly (a front-end copy change of about 160 lines; Codex was not used).

## What was built

- A new section `#paket` ("Yerel paket" / "Local package") in `landing/src/App.tsx` (`LocalPackage`), placed between Trust and the FAQ, with a nav link "Paket" / "Package". Copy is the new `localPackage` block in `landing/src/copy.ts`, Turkish first and English second.
- Five cards in the page's existing card style (rounded-frame, `bg-canvas`, icon tile, `Badge` for status) and a sixth cell with the optional price and the "apply for the pilot" button (`#pilot`).
- `landing/src/config.ts` (new): two optional build-time values read from `import.meta.env`.
  - `VITE_PACKAGE_PRICE`: shown verbatim as the package price. **Empty by default; when empty no price (and no price label) is rendered.** **No TRY amount appears anywhere in the copy**, in either language. Pricing is not settled; the section is built so that setting the variable at build time is all that is needed once it is.
  - `VITE_APP_URL`: the web app's `https://` origin. The legal pages are routes of the app (`frontend/src/app/router.tsx`: `/privacy`, `/terms`, `/data-deletion`), not of the static landing site, so the links are drawn only when this is set; otherwise the three documents are named as plain chips.
- `vite-env.d.ts` types the two variables; `landing/README.md` documents them.

## Claims and evidence

| # | Claim on the page | Evidence | Verdict |
|---|---|---|---|
| 1 | The app opens in Turkish; English is selectable | `frontend/src/i18n/locales/tr` and `en`; `backend/app/identity/models.py` (`LOCALES = ("tr","en")`, `ui_locale` default `"tr"`) | True |
| 2 | Detects the customer's message language, drafts in Turkish or English | `backend/app/core/i18n/__init__.py` (`SUPPORTED_LOCALES = ("tr","en")`); `backend/app/inbox/language.py` (deterministic detection) | True |
| 3 | Does not answer a message in another language, leaves it to the owner | `backend/app/inbox/language.py` docstring and `drafting.py` (`language_unsupported` plan, conversation goes to a person, rule R4) | True |
| 4 | Privacy policy, terms and a data-deletion page are in the app | `frontend/src/app/router.tsx` lines 127-130; `features/legal/PrivacyPolicyPage.tsx`, `TermsPage.tsx`, `DataDeletionInfoPage.tsx` | True (links need `VITE_APP_URL`) |
| 5 | We hand over the KVKK information-notice template and a draft DPA during setup | `docs/operations/pilot-onboarding-checklist.md` §1 ("Operator delivers `kvkk-aydinlatma-metni-template.md` and `dpa-template.md` to owner for review"); `docs/legal/kvkk-aydinlatma-metni-template.md`, `docs/legal/dpa-template.md` | True |
| 6 | These documents have not been through a lawyer's review; the owner's own lawyer should approve before publishing | Every file in `docs/legal/` carries `PENDING_COUNSEL_REVIEW`; the KVKK template itself says the business must have its lawyer approve it; OQ-04, OQ-12, OQ-13 in `docs/research/open-questions.md` | True. This is why the card says "prepared" with a "Draft, awaiting legal review" badge and not "ready" |
| 7 | The pilot is free and nothing is charged automatically | `docs/product/pricing-and-unit-economics.md` §3.1 (pilot 0 TRY, no card) and the banner "Billing does not exist in the code"; existing FAQ answer on the landing page | True |
| 8 | Paid-period billing will be in TRY; arrangement (e-archive invoice, transfer or payment link) agreed before start | `pricing-and-unit-economics.md` §6 stage 1 (manual E-Arsiv invoice, EFT/Havale or iyzico/PayTR link); OQ-06 ("pilots are invoiced manually") | **Softened, marked "Planned".** No invoicing process or code exists today, and the legal entity that would invoice is still open (OQ-05). The card therefore says "will be", not "is" |
| 9 | Setup in person (for now around Burdur and Antalya) or by video, about 30 minutes; prices and hours entered together; tried with real customer questions | `docs/operations/pilot-onboarding-checklist.md` (header: "in person or via video call"; §2.2 entering facts; the live test); `pricing-and-unit-economics.md` §3.1 and §3.3 (30 minutes, in-person visits in Burdur/Antalya) | True as a founder-run service; it is not a code feature. The city limit is deliberately stated |
| 10 | Prices, hours, dates and phone numbers in a reply come only from verified facts | INV-02 (`docs/invariants.md`); `backend/app/knowledge/claims.py` (MONEY, PERCENT, TIME, DATE, PHONE, EMAIL, URL, NUMBER); `backend/app/knowledge/render.py`; Feature Phase 1 summary §2.3 | True for the drafting pipeline (legacy and account agent template replies) |
| 11 | A draft with a value not in the facts is not sent, the conversation is left to the owner | `backend/app/inbox/drafting.py` `plan_with`: after one regeneration a failing draft returns `grounding_failed` / `render_failed` with no `text` (only a marked suggestion); policy sends it to a person | True. Phrased as "is not sent", not "can never happen" |
| 12 | The app shows which fact each value came from and when it was verified | Feature Phase 1 summary §2.3 (`app/knowledge/sources.py`, `ReplyDraft.facts_used[].verified_at`, `FactsUsed` in inbox draft and approval views) | True |
| 13 | The daily summary shows how many unverified values were sent | Feature Phase 1 summary §2.3 (metric `unverified_values_sent`, report card, Telegram summary lines) | True. Limitation kept out of the copy: it counts replies and reads the stored validator result, so after the text-retention window the number can be 0 because the evidence is gone (summary §6) |
| 14 | Keeping the facts correct and current is the owner's responsibility | The guarantee is provenance, not truth (INV-02; summary §6 "labels are current labels") | True; added so the guarantee is not read stronger than the code |

Not claimed on purpose: that the guarantee was exercised with the real model (`gpt-6-luna` was never run live, so everything above is verified against code and offline tests only), that the documents are lawyer-approved, that a TRY invoice can be issued today, any price, WhatsApp owner control, or comment replies.

## Checks (from `landing/`, PowerShell `npm.cmd`)

- `npm.cmd run typecheck`: pass.
- `npm.cmd run build` (`tsc -b && vite build`): pass (27 modules; the `theme.js` "can't be bundled without type=module" notice is pre-existing).
- The landing app has no `lint`, `test` or `i18n:check` scripts, so none were run. TR/EN parity is enforced by the `Copy` type (both languages must provide `localPackage` with exactly five items).
- Playwright (from `C:\Users\ernos\AgentNest\frontend\node_modules`, read-only) against `vite preview`: no horizontal overflow at 390, 820, 1024 and 1280 px, light and dark, TR and EN. Screenshots are in the session scratchpad `...\scratchpad\s03\` (`noprice-*` = default build, `price-*` = build with a test price). With no variables the section has only the `#pilot` link and no price; with `VITE_PACKAGE_PRICE` and `VITE_APP_URL` set it shows the price cell and links the three documents to `<app>/privacy`, `/terms`, `/data-deletion`.
- Responsive classes: cards `grid gap-4 sm:grid-cols-2 lg:grid-cols-3` (one column at phone width); the price/CTA cell is `sm:col-span-2 lg:col-span-1`; badges wrap (`flex-wrap`); document chips `flex-wrap`, 36 px minimum height; the CTA is `min-h-13`. The nav fits five links at 1024 px.

## Decisions and open items for the owner

1. **Pricing not settled.** No amount in the copy. To show one, set `VITE_PACKAGE_PRICE` (for example in the Railway landing service) and rebuild; set tier names in the string too if wanted. The existing FAQ still says "12 ay sabit kurucu fiyati" without an amount (not touched).
2. **`VITE_APP_URL` must be set at deploy** for the privacy, terms and data-deletion links to appear. `docs/operations/meta-app-review-package.md` plans `https://agentnest.io/privacy` and `/data-deletion`, but whether that domain is live is not verifiable from the repo, so it is not hard-coded.
3. **Decide on the invoice card.** If the founder cannot issue a TRY invoice (entity per OQ-05), drop item 3 of `localPackage.items` in both languages (the icon array in `LocalPackage` is index-based, so remove the matching icon too).
4. **Legal review wording.** The KVKK card says the documents are "awaiting legal review"; update it when counsel signs off.
5. **P-19** (pricing document promises) was closed on 2026-11-16 and stays consistent: nothing here promises a Planned tier feature.

## Files

- `landing/src/App.tsx` (new `LocalPackage`, wired in after `Trust`)
- `landing/src/copy.ts` (type `Packaged`, `localPackage` TR and EN, nav link)
- `landing/src/config.ts` (new)
- `landing/src/vite-env.d.ts`
- `landing/README.md`
- `docs/implementation/features-phase-4-before-self-service/s03-landing-report.md` (this file)
