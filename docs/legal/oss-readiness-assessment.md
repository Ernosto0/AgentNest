# Open-Source Readiness Assessment & Conditional Deferral (P8-11)

- **Document Reference:** `LEGAL-OSS-ASSESSMENT-V1`
- **Applicable Task:** `P8-11` (OSS Readiness)
- **Applicable ADR & Open Question:** [ADR-019](../../architecture/decisions/ADR-019-open-source-and-hosted-boundary.md) & [OQ-02](../../research/open-questions.md)
- **Status:** **CONDITIONALLY DEFERRED** (Repository remains private; no LICENSE file added)

---

## 1. Statutory Context & Governing Principles

In accordance with `docs/implementation/phase-8-sessions/phase-08-sessions.md` §Session 14 and ADR-019:
> *"Only after OQ-02 is resolved, add the chosen LICENSE, CONTRIBUTING with the decided CLA/DCO approach, CODE_OF_CONDUCT, SECURITY.md and issue templates. Otherwise record P8-11 as conditionally deferred and keep the repository private."*

### Current Status of OQ-02
- **Question:** Which license for the open-source core (Apache-2.0, AGPL-3.0, or another)?
- **Decision Owner:** Founder (with legal counsel).
- **Current State:** **UNRESOLVED / OPEN**.
- **Provisional Default:** **No LICENSE file. Repository private. No external contributions accepted.**

---

## 2. Decision Analysis for OQ-02 (Per ADR-019)

| License Option | Commercial Rights Granted | Hosted / SaaS Protection | Contribution / Governance Requirements |
|---|---|---|---|
| **Apache-2.0** *(Permissive)* | Anyone may use, modify, distribute, and commercially host closed instances. Includes explicit patent grant. | Low protection against commercial cloud clones; relies on brand, execution, and reviewed Meta App credentials. | Lightweight; simple DCO (Developer Certificate of Origin) is sufficient. Highest enterprise adoption. |
| **AGPL-3.0** *(Network Copyleft)* | Anyone may use and modify, but anyone offering the software as a network service must publish modifications under AGPL. | Moderate-to-high; discourages closed commercial SaaS forks. Founder can dual-license. | Strict; requires a **Contributor License Agreement (CLA)** before merging external code to retain commercial relicensing rights. |
| **Source-Available** *(BUSL / FSL)* | Free self-hosting for internal use; competing commercial hosting strictly prohibited for a period, converting to Apache/MIT later. | Maximum commercial protection for the founder's hosted business. | Not OSI-approved open source. May limit open-source community goodwill. |

---

## 3. Current Implementation Actions (Session 14)

1. **Repository Privacy Maintained:** The AgentNest repository remains strictly **private**. No public repository or mirror is authorized until `OQ-02` is formally decided.
2. **No LICENSE File Added:** In accordance with ADR-019 §Decisions Taken, no `LICENSE` file is created at the repository root. All rights remain reserved by the project owners.
3. **No External Contributions Accepted:** External pull requests, issues, or patches are not accepted, eliminating any risk of contributor copyright entanglement or relicensing gridlock.
4. **Dependency Compliance Verified:** All currently utilized runtime dependencies (FastAPI, SQLAlchemy, Pydantic, React, Tailwind, Vite) operate under permissive licenses (MIT, BSD-3, Apache-2.0) that remain compatible with whichever license is ultimately chosen for `OQ-02`.

---

## 4. Post-Decision Execution Roadmap (When OQ-02 Is Resolved)

As soon as legal counsel and the founder resolve `OQ-02`:

1. **License Artifact:** Add `LICENSE` file matching the chosen license (e.g., `LICENSE-APACHE` or `LICENSE-AGPL`).
2. **Contribution & Governance:**
   - If AGPL or dual-licensing is selected: Deploy a Contributor License Agreement (CLA) bot and create `CONTRIBUTING.md` requiring CLA execution before PR merge.
   - If Apache-2.0 is selected: Create `CONTRIBUTING.md` enforcing the Developer Certificate of Origin (DCO, `Signed-off-by`).
3. **Community & Security Standards:**
   - Add `CODE_OF_CONDUCT.md` based on the Contributor Covenant v2.1.
   - Add `SECURITY.md` defining vulnerability reporting channels (`security@agentnest.io`) and disclosure SLAs.
   - Add `.github/ISSUE_TEMPLATE/` (bug reports, feature proposals) and `.github/PULL_REQUEST_TEMPLATE.md`.
4. **Public Release:** Transition repository visibility from private to public.

