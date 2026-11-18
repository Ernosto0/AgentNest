# ADR-016: Localisation: three locale concepts, catalogs on both tiers

- **Status:** Accepted
- **Date:** 2026-10-15

## Context
Turkish-first, English later, one codebase. The original spec forbids scattered language checks. Text is produced in four places: the UI, server-rendered notifications (needed by Telegram and other channels where there is no frontend), LLM-generated customer replies and content, and fact rendering (money, hours). Turkish has specific formatting (`7.000 ₺`, decimal comma) and casing rules (`I`/`ı`, `İ`/`i`).

## Decision

### Three distinct locale concepts
| Concept | Stored on | Used for |
|---|---|---|
| **UI locale** | `users.ui_locale` (`tr` \| `en`; default from browser, then workspace) | Frontend strings, server-rendered notifications to that user |
| **Business locale** | `workspaces.default_locale`, `timezone` (IANA, e.g., `Europe/Istanbul`), `currency` (ISO 4217, e.g., `TRY`), `market` (`tr` \| `global`) | Fact rendering defaults, report dates and times, default reply language, onboarding templates and examples |
| **Reply language** | Per reply draft (`reply_drafts.language`) | Detected from the customer's message among `workspaces.reply_languages` (MVP: `tr`, `en`). Unsupported language → `human_required` (`LANGUAGE_UNSUPPORTED`). |

### Catalogs
- **Frontend:** `i18next` + `react-i18next`, JSON catalogs `frontend/src/i18n/locales/{tr,en}/*.json`, ICU-style plurals. All user-visible strings come from catalogs. A lint step fails on missing keys between `tr` and `en`.
- **Backend:** small JSON catalogs `backend/app/core/i18n/{tr,en}.json` for notifications, report templates, approval summaries and error messages. Lookup `t(key, locale, **params)`.
- **API errors** return stable `code` + `params`. The frontend renders localised messages from the code. The backend's localised `detail` is a fallback for non-web channels.

### Formatting
- Backend uses **Babel** (`format_currency(Decimal, "TRY", locale="tr_TR")` → `7.000,00 ₺`; a display style without decimals for whole amounts is configurable). Frontend uses `Intl.NumberFormat` / `Intl.DateTimeFormat`.
- All instants are stored in **UTC** (`timestamptz`). Conversion to the workspace timezone happens at the edges (UI, reports, schedule input). Schedule input from the UI is "local date + local time + workspace timezone" and is converted server-side, which handles DST correctly for non-Türkiye workspaces (Türkiye has no DST since 2016, but the code must not assume that).

### Parsing user-entered values
- Money parsing is locale-aware (`7.000` in `tr` = 7000; `7,000` in `en` = 7000; `7.000,50` in `tr` = 7000.50). Ambiguous input (e.g., `7.000` typed in an `en` workspace) **always produces a confirmation** showing the formatted value. The command interpretation output carries both the raw text and the normalised decimal string, and the deterministic parser re-checks it.
- Case-insensitive matching uses locale-aware normalisation (Turkish dotted/dotless I handled explicitly; never plain `.lower()` on Turkish text for matching).

### Content and market differences
- Market-specific onboarding templates (fact templates, example commands) are keyed by `market` + `business_category`, not by `if locale == "tr"` checks.
- LLM prompts are written in English with an explicit output-language parameter. Few-shot examples exist per language.

## Alternatives considered
- Translating on the frontend only: fails for Telegram and other channels and for server-rendered approval summaries.
- gettext `.po` files: heavier tooling than needed for the catalog size. JSON is shared in style with the frontend.

## Consequences
- Phase 1 sets up both catalogs and the lint check. Every later phase adds keys in both languages; Turkish is required, English is required.
- Tests include Turkish fixtures (money parsing, `İ/ı` matching, `tr_TR` rendering).

## Revisit when
- More UI languages are added. Consider a translation management workflow (Weblate/Crowdin) when contributors translate.


## Addendum 2026-11-18: customer reply languages (F-11, Session 10)

Reply languages are `tr, en, ru, de, ar`, independently of the unchanged `tr/en` UI and content/post locales. Detection is deterministic script and word-list evidence: foreign-script dominance at 0.5 of letters; Cyrillic/Arabic mixed with Latin at 0.2 escalates; a dominant Russian/Arabic script needs at least one word-score hit (distinctive Russian letters score two), with neighbouring-language exclusions. German uses noncolliding words, `ß` (+2), and `ä` (+1 only with a German word). Non-TR/EN Latin winners require runner-up evidence strictly below half their score; close foreign competitors and explicit bilingual greetings escalate. TR/EN retain the one-point margin. Low-confidence recognised foreign text is `other`, giving `LANGUAGE_UNSUPPORTED` under R4.

All claim patterns run for every reply locale. Arabic/Persian digits, decimal/thousands/percent separators and letter variants are folded; invisible bidi/format marks and Arabic vocalisation are removed with an index map, after trusted-span masking, preserving original issue offsets. Reply facts use Babel `ru_RU`, `de_DE`, `ar` (Western digits), with NBSP money spacing and LRM around Arabic time-range dashes. Owner fact text falls back to English, workspace fallback, then Turkish; it is not translated. The account-agent calendar path remains tr/en and fails closed for new languages. Spelled-out numeric claims remain outside validator coverage; live LLM quality, eval sets, settings UI and RTL display acceptance are pending Session 11.
