"""Conversation erasure with a stored draft and its approval (regression, found in Feature Phase 2
Session 02). A draft and its message reference each other and a draft references its approval;
erasure used to write NULL into the NOT NULL ``covers_through_message_id`` instead of breaking
those links, so any conversation with a draft could not be erased."""

from sqlalchemy import select

from app.approvals.models import Approval
from app.inbox.models import Conversation, Message, ReplyDraft
from app.operations import data_rights
from tests.integration.inbox.conftest import InboxEnv


def test_a_conversation_with_a_draft_awaiting_approval_can_be_erased(inbox: InboxEnv) -> None:
    inbox.deliver_and_process("Aylık üyelik ne kadar?")
    draft = inbox.make_draft("pending_approval")
    approval_id = inbox.approval_of(draft).id
    # The message side of the draft <-> message cycle, as a sent reply has it.
    inbox.messages()[-1].reply_draft_id = draft.id
    inbox.session.commit()
    conversation_id = inbox.conversation().id
    ctx = inbox.env.ctx(inbox.env.owner)

    data_rights.erase_conversation(inbox.session, inbox.clock, ctx, conversation_id)
    inbox.session.commit()
    inbox.session.expire_all()

    assert inbox.session.scalars(select(ReplyDraft)).all() == []
    assert inbox.session.scalars(select(Message)).all() == []
    assert inbox.session.get(Approval, approval_id) is None
    assert inbox.session.get(Conversation, conversation_id) is None
