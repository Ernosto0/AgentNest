"""Unit test wrapper for the automated security review and scanner (P8-09)."""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.security_scan import SecurityScanner  # noqa: E402


def test_automated_security_scanner_runs_and_passes_all_checks() -> None:
    scanner = SecurityScanner(verbose=False)
    report = scanner.run_all()

    failures = [f for f in report.findings if f.status == "FAILED"]
    assert report.failed_checks == 0, f"Security scan detected failures: {failures}"
    assert report.passed_checks >= 12
    assert len(report.threat_coverage) == 27
    assert report.summary["critical_issues"] == 0
    assert report.summary["high_issues"] == 0
