#!/usr/bin/env python3
"""Administrative CLI script for evaluating operator alerts (Phase 8 Session 13, P8-07).

Usage:
    python scripts/evaluate_alerts.py [--email operator@example.com] [--json] [--no-resolve]

Evaluates all 8 canonical operational conditions independently of the background worker,
updates durable alert deduplication state in PostgreSQL, and optionally sends notification emails.

Exit codes:
    0 = Clean (no active alerts firing)
    1 = Critical alerts currently firing
    2 = Warning alerts currently firing (no criticals)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select  # noqa: E402

from app.core.clock import SystemClock  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import get_session_factory  # noqa: E402
from app.operations.models import OperatorAlertState  # noqa: E402
from app.operations.operator_alerts import evaluate_operator_alerts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate operator alert conditions and print status report."
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Override recipient email for alerts (defaults to OPERATOR_ALERT_EMAIL)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output evaluation report and active alerts as JSON",
    )
    parser.add_argument(
        "--no-resolve",
        action="store_true",
        help="Do not auto-resolve cleared alerts during this evaluation cycle",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print verbose alert metadata and details",
    )
    args = parser.parse_args()

    settings = get_settings()
    clock = SystemClock()
    factory = get_session_factory()

    with factory() as session:
        report = evaluate_operator_alerts(
            session,
            clock,
            settings,
            auto_resolve=not args.no_resolve,
            operator_email=args.email,
        )
        session.commit()

        # Query all active firing alert states to determine highest severity
        firing_states = session.scalars(
            select(OperatorAlertState).where(OperatorAlertState.status == "firing")
        ).all()

    has_critical = any(st.severity == "critical" for st in firing_states)
    has_warning = any(st.severity == "warning" for st in firing_states)

    if args.json:
        payload = {
            "evaluated_at": report.evaluated_at.isoformat(),
            "active_candidates_count": report.active_candidates_count,
            "new_alerts_fired": report.new_alerts_fired,
            "refired_alerts": report.refired_alerts,
            "resolved_alerts": report.resolved_alerts,
            "suppressed_in_cooldown": report.suppressed_in_cooldown,
            "delivery_failures": report.delivery_failures,
            "firing_alerts": [
                {
                    "alert_key": st.alert_key,
                    "category": st.category,
                    "severity": st.severity,
                    "summary": st.summary,
                    "first_triggered_at": st.first_triggered_at.isoformat(),
                    "last_notified_at": st.last_notified_at.isoformat(),
                    "notification_count": st.notification_count,
                    "details": st.details,
                }
                for st in firing_states
            ],
            "resolved_keys": report.resolved_keys,
        }
        print(json.dumps(payload, indent=2))
    else:
        status_label = "CRITICAL" if has_critical else ("WARNING" if has_warning else "HEALTHY")
        print("\n=======================================================")
        print(f" AgentNest Operator Alert Evaluation: [{status_label}]")
        print("=======================================================")
        print(f" Evaluated At:           {report.evaluated_at.isoformat()}")
        print(f" Active Conditions:      {report.active_candidates_count}")
        print(f" New Fired:              {report.new_alerts_fired}")
        print(f" Refired (post-cooldown):{report.refired_alerts}")
        print(f" Resolved:               {report.resolved_alerts}")
        print(f" Suppressed (cooldown):  {report.suppressed_in_cooldown}")
        print(f" Delivery Failures:      {report.delivery_failures}")
        print(f" Total Currently Firing: {len(firing_states)}")

        if firing_states:
            print("\n--- Active Firing Alerts ---")
            for st in firing_states:
                sev = f"[{st.severity.upper()}]"
                print(f" * {sev:<10} {st.alert_key}")
                print(f"   Summary:     {st.summary}")
                print(f"   First Seen:  {st.first_triggered_at.isoformat()}")
                last_ts = st.last_notified_at.isoformat()
                print(f"   Notified:    {st.notification_count} times (last: {last_ts})")
                if args.verbose and st.details:
                    print(f"   Details:     {json.dumps(st.details)}")
        else:
            print("\nNo operational alerts currently firing. All systems nominal.")

    if has_critical:
        return 1
    elif has_warning:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
