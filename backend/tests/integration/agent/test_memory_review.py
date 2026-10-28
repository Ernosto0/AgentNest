"""Operator privacy checks across source read models."""

import pytest
from sqlalchemy import select

from app.inbox.models import Conversation
from app.inbox.views import conversation_out, message_out
from app.memory.models import CustomerMemory
from tests.integration.agent.test_context_grounding import scenario
from tests.integration.agent.test_memory import learn, prepared


def test_deleted_source_has_no_inbox_preview_text_or_attachments(db_session, clock):
    _, _, source = scenario(db_session, clock)
    source.text = "PRIVATE-DELETED-CUSTOMER-PREFERENCE"
    source.attachments = [{"type": "image", "url": "https://private.invalid/customer.jpg"}]
    source.is_deleted = True
    db_session.flush()
    conversation = db_session.get(Conversation, source.conversation_id)
    assert conversation_out(conversation, source).last_message_preview is None
    output = message_out(source)
    assert output.text is None and output.attachments == []


def test_memory_write_requires_stable_provider_source_identity(db_session, clock):
    context, _, source = prepared(db_session, clock)
    source.external_message_id = None
    db_session.flush()
    with pytest.raises(ValueError, match="evidenced customer statement"):
        learn(db_session, clock, context, source)
    assert not db_session.scalars(select(CustomerMemory)).all()
