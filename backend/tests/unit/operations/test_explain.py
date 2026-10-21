"""What an operation's outcome means in plain language (plan H6): the text chain and the
statuses that need one. No database: an ``Operation`` is only constructed."""

import uuid

import pytest

from app.core.errors import ERROR_CATALOG
from app.core.i18n import catalog_keys
from app.operations.explain import explain, failure_code
from app.operations.models import Operation


def operation(
    status: str, code: str | None = None, operation_type: str = "send_reply"
) -> Operation:
    return Operation(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        operation_type=operation_type,
        idempotency_key=f"k:{uuid.uuid4()}",
        subject_type="reply_draft",
        subject_id=uuid.uuid4(),
        social_account_id=uuid.uuid4(),
        provider_kind="mock",
        status=status,
        last_error_code=code,
    )


@pytest.mark.parametrize("status", ["pending", "in_progress", "succeeded", "cancelled"])
def test_an_operation_that_is_not_in_trouble_has_nothing_to_explain(status: str) -> None:
    assert explain(operation(status, "PROVIDER_UNAVAILABLE"), "tr") is None
    assert failure_code(operation(status, "PROVIDER_UNAVAILABLE")) is None


def test_a_reply_has_texts_of_its_own_where_the_shared_ones_talk_about_posts() -> None:
    reply = explain(operation("failed", "OUTCOME_UNCONFIRMED"), "en")
    post = explain(operation("failed", "OUTCOME_UNCONFIRMED", "publish_content"), "en")
    assert reply is not None and post is not None
    assert reply.what == "We could not confirm that the reply reached the customer."
    assert post.what == "We could not confirm whether it was published."
    assert reply.retryable is False and reply.code == "OUTCOME_UNCONFIRMED"


def test_a_shared_catalog_text_is_used_when_the_operation_type_has_none() -> None:
    found = explain(operation("failed", "PROVIDER_RATE_LIMITED"), "en")
    assert found is not None
    assert found.what == "Instagram asked us to slow down."
    assert found.retryable is True


def test_a_code_without_text_falls_back_to_a_generic_one_never_a_bare_code() -> None:
    found = explain(operation("failed", "SOMETHING_NEW"), "en")
    assert found is not None
    assert found.what == "An operation could not be completed."
    assert "SOMETHING_NEW" not in found.what + found.next
    assert found.retryable is None
    no_code = explain(operation("failed", None), "tr")
    assert no_code is not None and no_code.code is None and no_code.what


def test_an_unknown_outcome_reads_as_still_checking() -> None:
    found = explain(operation("outcome_unknown"), "en")
    assert found is not None and found.code == "OUTCOME_UNKNOWN"
    assert found.what == "We are still checking whether the reply reached the customer."


def test_a_waiting_retry_is_explained_by_its_last_error() -> None:
    found = explain(operation("retry_wait", "PROVIDER_UNAVAILABLE"), "en")
    assert found is not None and found.next == "We will try again automatically."


@pytest.mark.parametrize("locale", ["tr", "en"])
def test_every_error_code_a_reply_can_fail_with_has_text(locale: str) -> None:
    keys = catalog_keys(locale)
    for code in (
        "MESSAGING_WINDOW_CLOSED",
        "ACCOUNT_NOT_CONNECTED",
        "ACCOUNT_NEEDS_REAUTH",
        "CAPABILITY_MISSING",
        "PROVIDER_UNAVAILABLE",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_REJECTED",
        "OUTCOME_UNKNOWN",
        "OUTCOME_UNCONFIRMED",
    ):
        assert code in ERROR_CATALOG
        assert f"operation.send_reply.{code}.what" in keys or f"errors.{code}.what" in keys, code
    assert "operation.unknown.what" in keys and "operation.unknown.next" in keys
