# Dependency Auditing and Vulnerability Management Runbook

- **Scope:** Automated auditing of backend and frontend third-party dependencies (`pip-audit` and `npm audit`), remediation lifecycles, and exception governance (Phase 8 Session 12, Task `P8-06`).
- **Enforcement:** Enforced in `.github/workflows/ci.yml` on every pull request and push to `main`.

---

## 1. Overview

AgentNest enforces automated software composition analysis (SCA) to detect known Common Vulnerabilities and Exposures (CVEs) and GitHub Security Advisories (GHSAs) before code merges:
- **Backend (Python):** Audited via `pip-audit` against the official PyPI vulnerability database / OSV.
- **Frontend (TypeScript / React):** Audited via `npm audit --audit-level=moderate` against npm advisory database.

---

## 2. CI Automation and Thresholds

### 2.1 Backend CI Step (`backend`)
```yaml
- name: Dependency audit (pip-audit)
  run: uv run pip-audit
```
Fails the CI build if any package in `uv.lock` has a published advisory with a CVSS score above baseline or known exploitable vulnerabilities.

### 2.2 Frontend CI Step (`frontend`)
```yaml
- name: Dependency audit (npm audit)
  run: npm audit --audit-level=moderate
  working-directory: frontend
```
Fails the CI build if any package in `package-lock.json` has a `moderate`, `high`, or `critical` advisory.

---

## 3. Remediation Lifecycles and SLA

| Severity | Target SLA | Required Action |
|---|---|---|
| **Critical** | Within 24 hours | Immediate patch or dependency replacement; emergency hotfix deploy if in production. |
| **High** | Within 7 days | Update package version in `backend/pyproject.toml` or `frontend/package.json`, run `uv lock` or `npm update`, test, and merge. |
| **Moderate** | Within 30 days | Update package during regular sprint maintenance cycle. |
| **Low / Informational** | Next scheduled update | Review during routine monthly dependency refresh. |

---

## 4. Exception Policy & Governance

If a vulnerability cannot be immediately patched (e.g. upstream fix is not yet released, or the advisory is a false positive for AgentNest's usage), an explicit documented exception may be granted.

### 4.1 Exception Rules
1. **Ownership:** Every exception must be approved by the Lead Engineer.
2. **Justification:** Must document why the vulnerable code path is not reachable or how surrounding controls (e.g. input validation, isolation) mitigate the risk.
3. **Hard Expiry:** Max **30 days**. Exceptions automatically expire, and CI checks must resume failing if not re-evaluated or patched.

### 4.2 Exception Register

| CVE / GHSA ID | Package & Version | Severity | Justification & Mitigations | Exception Owner | Expiry Date | Status |
|---|---|---|---|---|---|---|
| *(None currently active)* | — | — | All dependencies clean as of Phase 8 Session 15 baseline (minimatch ^11.0.4 override applied) | Engineering Lead | 2026-12-03 | Active |

---

## 5. Local Developer Verification

Developers can run audits locally before pushing:

### Backend
```powershell
cd backend
uv run pip-audit
```

### Frontend
```powershell
cd frontend
npm.cmd audit
```

