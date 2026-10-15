# ADR-019: One codebase; hosted-only features as optional modules; license undecided

- **Status:** Provisional (license pending [OQ-02](../../research/open-questions.md))
- **Date:** 2026-10-15

## Context
The product is planned as an open-source core plus a hosted SaaS. The paid offering should earn money by reducing operational burden (managed hosting, assisted onboarding, managed integrations, backups, support), not by crippling self-hosting. The original spec names Apache-2.0 as a candidate without weighing it against the business model.

## Decisions taken now
1. **One repository and one codebase** for the core. No "community edition" fork.
2. **Hosted-only capabilities** (billing, plan limits, multi-tenant operator console, managed backups tooling) are **not built in the MVP**. When built, they live in clearly separated optional modules (`app/hosted/…`) enabled by configuration, or in a separate private repository that depends on the core. The choice is deferred until the license is chosen.
3. **Local development never requires paid services.** Every external integration has a mock or fake: Instagram (`mock`), LLM (`fake`), storage (`local`), owner channels (web). See [local-development.md](../../operations/local-development.md).
4. **Meta App credentials belong to the operator.** A self-hoster must create their own Meta app and complete App Review for their own use. The hosted SaaS uses the founder's reviewed app, which is a real value of the hosted offering, and the docs must state it honestly.
5. **Until the license is decided:** no LICENSE file, repository private, **no external contributions accepted**. Once outside code is merged, relicensing requires every contributor's consent unless a CLA was signed.

## License options (trade-offs for OQ-02)

| Option | Allows | Implication for the hosted business | Adoption |
|---|---|---|---|
| **Apache-2.0** (permissive) | Anyone may use, modify, and **host commercially without sharing changes**. Includes a patent grant. | A competitor (or Meta agency) can run a hosted clone. The moat is execution, Meta App Review status, local support and brand. | Highest; most corporate-friendly. |
| **MIT** | As Apache, without the explicit patent grant. | Same as Apache. | High. |
| **AGPL-3.0** (network copyleft) | Use and modification allowed. **Anyone offering it as a network service must publish their modifications** under the AGPL. | Discourages closed hosted forks. The founder (as copyright holder) can still offer the hosted SaaS and dual-license. Some companies prohibit AGPL use. | Lower among companies; fine for individuals and self-hosters. |
| **Source-available** (BUSL/FSL, "fair source") | Self-hosting allowed; **competing hosted use prohibited** for a period, then converts to open source. | Strongest protection for the SaaS. | **Not OSI open source.** It conflicts with the "open-source core" positioning and may reduce community trust. |

**Engineering-relevant notes (not legal advice):**
- Dependency licenses must be compatible with the chosen license. All planned dependencies (FastAPI, SQLAlchemy, Pydantic, React, etc.) are permissive (MIT/BSD/Apache), which is compatible with all options above.
- If AGPL or dual licensing is chosen, adopt a **CLA** (or require contributions under a license grant that allows relicensing) **before** accepting the first external contribution.
- The DCO alone does not grant relicensing rights.

## Consequences
- Contribution guidelines, `CODE_OF_CONDUCT.md` and `SECURITY.md` are written in Phase 8, after OQ-02.
- Docs keep the hosted/self-host distinction explicit wherever a feature depends on the operator's Meta app.

## Revisit when
- OQ-02 is decided. Update this ADR's status to Accepted with the chosen license, and add the LICENSE file.
