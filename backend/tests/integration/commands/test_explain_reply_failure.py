"""``query.explain_failure`` about a reply that did not go out (plan H6): the newest of a post in
trouble and a failed ``send_reply`` operation, within seven days, explained from the error catalog
with what, when and the next step, and a link to the conversation."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.integrations.instagram.models import SocialAccount
from app.operations.models import Operation
from tests.factories import create_workspace
from tests.helpers.content import connect_account, make_item
from tests.helpers.reporting import Builder
from tests.integration.commands.conftest import CommandEnv

LAST_ERROR = "son hata neydi?"


def _builder(cmd: CommandEnv) -> Builder:
    account = cmd.env.session.scalar(select(SocialAccount))
    if account is None:
        account = connect_account(cmd.env)
    return Builder(
        cmd.env.session, cmd.env.workspace, cmd.env.owner.user, simulated=True, account=account
    )


def failed_reply(
    cmd: CommandEnv,
    *,
    code: str | None = "OUTCOME_UNCONFIRMED",
    status: str = "failed",
    completed_at: datetime | None = None,
    operation_type: str = "send_reply",
    detail: str | None = None,
) -> tuple[Operation, Any]:
    """A reply draft in a conversation and the operation that tried to send it."""
    builder = _builder(cmd)
    now = cmd.env.clock.now()
    conversation = builder.conversation(now - timedelta(hours=3))
    inbound = builder.message(conversation, "inbound", now - timedelta(hours=2))
    draft = builder.draft(
        conversation,
        inbound,
        source="owner",
        decision="approval_required",
        status="failed",
        created_at=now - timedelta(hours=1),
    )
    operation = Operation(
        workspace_id=cmd.env.workspace.id,
        operation_type=operation_type,
        idempotency_key=f"{operation_type}:{draft.id}",
        subject_type="reply_draft",
        subject_id=draft.id,
        social_account_id=builder.account.id,
        provider_kind="mock",
        status=status,
        attempts=2,
        last_error_code=code,
        last_error_detail=detail,
        provider_ref={"recipient_id": "customer-123"},
        result={"raw": "provider payload"},
        completed_at=completed_at or now - timedelta(minutes=30),
        is_simulated=True,
    )
    cmd.env.session.add(operation)
    cmd.env.session.commit()
    return operation, conversation


def failed_post(cmd: CommandEnv, *, updated_at: datetime, code: str = "MEDIA_REJECTED") -> Any:
    connect_account_if_missing(cmd)
    item = make_item(
        cmd.env, status="failed", title="Haftalık program", last_error_code=code, is_simulated=True
    )
    item.updated_at = updated_at
    cmd.env.session.commit()
    return item


def connect_account_if_missing(cmd: CommandEnv) -> None:
    if cmd.env.session.scalar(select(SocialAccount)) is None:
        connect_account(cmd.env)


def test_an_unconfirmed_reply_is_explained_with_what_when_and_next(cmd: CommandEnv) -> None:
    operation, conversation = failed_reply(cmd, detail="provider said: token abc123 expired")
    command = cmd.run(cmd.env.owner, LAST_ERROR)

    assert command["status"] == "completed"
    assert command["result"]["message_key"] == "command.reply_failure"
    assert command["result"]["params"] == {
        "status": "failed",
        "error_code": "OUTCOME_UNCONFIRMED",
        "what": "Yanıtın müşteriye ulaşıp ulaşmadığını doğrulayamadık.",
        "next": "Yeniden göndermeden önce Instagram'daki konuşmayı kontrol edin.",
        "retryable": False,
        "when": "15 Oca 14:30",  # 11:30 UTC, shown in the workspace time zone (INV-19)
        "is_simulated": True,  # INV-09
    }
    assert command["result"]["links"] == [{"target": "inbox", "id": str(conversation.id)}]
    # Nothing the provider said, and no identifiers of the call, reach the answer.
    body = str(command)
    assert "abc123" not in body and "customer-123" not in body and "provider payload" not in body
    assert str(operation.id) not in body


def test_the_explanation_follows_the_users_language_and_time(cmd: CommandEnv) -> None:
    cmd.env.owner.user.ui_locale = "en"
    cmd.env.session.commit()
    failed_reply(cmd)
    params = cmd.run(cmd.env.owner, "what was the last error")["result"]["params"]
    assert params["what"] == "We could not confirm that the reply reached the customer."
    assert params["next"] == "Check the conversation in Instagram before sending it again."
    assert params["when"] == "15 Jan 14:30"


def test_other_codes_use_the_shared_error_texts_and_unknown_ones_a_generic_text(
    cmd: CommandEnv,
) -> None:
    operation, _ = failed_reply(cmd, code="MESSAGING_WINDOW_CLOSED")
    params = cmd.run(cmd.env.owner, LAST_ERROR)["result"]["params"]
    assert params["what"].startswith("Instagram, müşterinin son mesajından sonra")
    assert params["error_code"] == "MESSAGING_WINDOW_CLOSED" and params["retryable"] is None

    operation.last_error_code = "SOMETHING_NEW"
    cmd.env.session.commit()
    generic = cmd.run(cmd.env.owner, LAST_ERROR)["result"]["params"]
    assert generic["what"] == "Bir işlem tamamlanamadı."
    assert generic["retryable"] is None


def test_the_newest_of_a_post_and_a_reply_wins(cmd: CommandEnv) -> None:
    now = cmd.env.clock.now()
    failed_reply(cmd, completed_at=now - timedelta(hours=2))
    post = failed_post(cmd, updated_at=now - timedelta(hours=5))
    assert cmd.run(cmd.env.owner, LAST_ERROR)["result"]["message_key"] == "command.reply_failure"

    post.updated_at = now - timedelta(minutes=10)  # the post failed after the reply did
    cmd.env.session.commit()
    command = cmd.run(cmd.env.owner, LAST_ERROR)
    assert command["result"]["message_key"] == "command.content_failure"
    assert command["result"]["links"] == [{"target": "content", "id": str(post.id)}]
    assert command["result"]["params"]["when"] == "15 Oca 14:50"


def test_a_failed_post_is_explained_with_when(cmd: CommandEnv) -> None:
    post = failed_post(cmd, updated_at=cmd.env.clock.now() - timedelta(hours=1))
    command = cmd.run(cmd.env.owner, LAST_ERROR)
    params = command["result"]["params"]
    assert command["result"]["message_key"] == "command.content_failure"
    assert (params["error_code"], params["when"]) == ("MEDIA_REJECTED", "15 Oca 14:00")
    assert params["what"] == "Instagram görseli işleyemedi."
    assert command["result"]["links"] == [{"target": "content", "id": str(post.id)}]


def test_only_the_last_seven_days_count(cmd: CommandEnv) -> None:
    now = cmd.env.clock.now()
    failed_reply(cmd, completed_at=now - timedelta(days=7, minutes=1))
    failed_post(cmd, updated_at=now - timedelta(days=8))
    assert cmd.run(cmd.env.owner, LAST_ERROR)["result"]["message_key"] == "command.no_failure"

    recent, _ = failed_reply(cmd, completed_at=now - timedelta(days=6, hours=23))
    command = cmd.run(cmd.env.owner, LAST_ERROR)
    assert command["result"]["message_key"] == "command.reply_failure"
    assert recent.completed_at is not None


def test_a_reply_that_did_not_fail_is_not_a_failure(cmd: CommandEnv) -> None:
    for status in ("succeeded", "retry_wait", "outcome_unknown", "cancelled", "in_progress"):
        failed_reply(cmd, status=status, code=None)
    failed_reply(cmd, operation_type="publish_content")  # a post's trouble is read from the post
    command = cmd.run(cmd.env.owner, LAST_ERROR)
    assert command["result"]["message_key"] == "command.no_failure"


def test_no_failure_is_still_an_answer(cmd: CommandEnv) -> None:
    command = cmd.run(cmd.env.owner, LAST_ERROR)
    assert command["status"] == "completed" and command["error_code"] is None
    assert command["result"]["message_key"] == "command.no_failure"


def test_a_failed_reply_of_another_workspace_is_never_explained(cmd: CommandEnv) -> None:
    other = create_workspace(cmd.env.session, name="Other", slug="other")
    foreign = Builder(cmd.env.session, other, cmd.env.owner.user)
    conversation = foreign.conversation(cmd.env.clock.now() - timedelta(hours=3))
    inbound = foreign.message(conversation, "inbound", cmd.env.clock.now() - timedelta(hours=2))
    draft = foreign.draft(
        conversation,
        inbound,
        source="owner",
        decision="approval_required",
        status="failed",
        created_at=cmd.env.clock.now() - timedelta(hours=1),
    )
    cmd.env.session.add(
        Operation(
            workspace_id=other.id,
            operation_type="send_reply",
            idempotency_key=f"send_reply:{draft.id}",
            subject_type="reply_draft",
            subject_id=uuid.uuid4(),
            social_account_id=foreign.account.id,
            provider_kind="mock",
            status="failed",
            last_error_code="OUTCOME_UNCONFIRMED",
            completed_at=cmd.env.clock.now() - timedelta(minutes=5),
            is_simulated=True,
        )
    )
    cmd.env.session.commit()
    command = cmd.run(cmd.env.owner, LAST_ERROR)
    assert command["result"]["message_key"] == "command.no_failure"


def test_staff_may_ask_what_went_wrong(cmd: CommandEnv) -> None:
    failed_reply(cmd)
    command = cmd.run(cmd.env.staff, LAST_ERROR)
    assert command["status"] == "completed"
    assert command["result"]["message_key"] == "command.reply_failure"
