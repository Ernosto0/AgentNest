"""The account agent calendar path remains restricted to Turkish/English."""

import pytest

from app.agent.context import assemble
from tests.integration.agent.test_context_grounding import scenario


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("ru", "Привет, сколько стоит номер?"),
        ("de", "Wie viel kostet ein Zimmer?"),
        ("ar", "مرحبا كم سعر الغرفة؟"),
    ],
)
def test_account_agent_fails_closed(db_session, clock, language, text):
    context, workspace, message = scenario(db_session, clock)
    workspace.reply_languages = ["tr", "en", language]
    message.text = text
    db_session.flush()
    assert assemble(db_session, clock, context).language is None
