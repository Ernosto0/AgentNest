# Session 06: Knowledge, grounding and personality

**Task:** P7.5-06. **Status:** Planned. **Prerequisite:** Session 05.
Read the [common session rules](phase-7.5-sessions.md) and phase sections 6, 8 and 13.

## Goal

Support free conversation and a persistent business voice with relevant, evidence-backed knowledge rather than a fixed intent-to-answer mapping.

## Read first

`app/knowledge/{claims,render,readiness,impact}.py`, business knowledge repositories and approved answers; `app/ai/tasks/draft_reply.py`, prompt assets and current eval fixtures; `app/inbox/{context,drafting}.py`.

## Build

1. Build scoped knowledge retrieval over usable facts, approved answers and permitted business material. Return source IDs/versions, validity and visibility. Add pagination/bounded retrieval rather than loading all customer histories.
2. Assemble context from the task, relevant turns, summary, business knowledge and versioned personality. Support TR/EN, mixed-topic requests, clarification and small talk without a mandatory existing FAQ match.
3. Add personality fields for tone/formality/length/emoji examples and channel style, with owner/manager editing and source auditing. Runtime authority remains separate.
4. Extend grounding to distinguish verified business claims from explicitly customer-attributed values, questions and one-off authoritative answers. Preserve renderer provenance and fact-change invalidation. Customer-supplied text cannot become a URL/price/policy source for business promises.
5. Validate public replies with public-only context/tool access. Add prompt-injection and forged-source handling for retrieved documents, customer messages and tool results. An invalid draft can be repaired once or become a useful clarification/owner question instead of silently inventing an answer.

## Verify and done when

Test multi-topic responses, questions outside the old intent set, missing prices with a valid greeting, customer-date clarification, unverified offers, stale facts and withheld prices. Test persona version changes and language consistency. Preserve critical-value validator adversarial cases and add source/visibility attacks. Author initial multi-turn datasets for several business categories; scripted fake tests prove mechanics while real-model quality remains Session 17 evidence.

## Handoff

Write `s06-report.md` with context/knowledge tool schemas, personality contract, allowed attribution rules and eval fixtures. AC75-01/03/05/12 have focused evidence; Session 07 must use this actual assembly/validation path for sending.
