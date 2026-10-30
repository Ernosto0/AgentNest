"""Run the database-backed, scripted account-agent journey gate."""

import pytest

JOURNEY_TESTS = (
    "tests/integration/agent/test_initial_journeys.py",
    "tests/integration/agent/test_owner_requests.py::test_missing_information_answer_runs_real_jobs_and_mock_ledger",
    "tests/integration/agent/test_dm.py::test_ask_uses_original_human_decision_and_off_never_sends",
    "tests/integration/agent/test_comments.py::test_account_isolation_public_broker_and_stale_cursor",
    "tests/integration/agent/test_public_actions.py::test_moderation_and_timeout_after_success_reconciles_without_resend",
    "tests/integration/agent/test_private_reply.py::test_public_then_private_are_separate_authorized_effects",
    "tests/integration/agent/test_private_reply.py::test_signed_customer_response_links_private_origin_only",
    "tests/integration/agent/test_owner_content.py::test_real_loop_clarifies_then_resumes",
)


def main() -> int:
    """Exercise durable paths with mock effects; this is not the real-model quality gate."""
    return pytest.main([*JOURNEY_TESTS, "-q", "--tb=short"])


if __name__ == "__main__":
    raise SystemExit(main())
