"""The account agent supports five reply languages (tr, en, ru, de, ar).

Fails closed on unsupported languages.
"""

import pytest

from app.agent.context import assemble
from tests.integration.agent.test_context_grounding import scenario


@pytest.mark.parametrize(
    ("language", "text"),
    [
        ("tr", "Merhaba, fiyat ne kadar?"),
        ("en", "Hello, how much is this?"),
        ("ru", "Привет, сколько стоит номер?"),
        ("de", "Wie viel kostet ein Zimmer?"),
        ("ar", "مرحبا كم سعر الغرفة؟"),
    ],
)
def test_account_agent_supported_languages(db_session, clock, language, text):
    context, workspace, message = scenario(db_session, clock)
    workspace.reply_languages = ["tr", "en", "ru", "de", "ar"]
    message.text = text
    db_session.flush()
    assert assemble(db_session, clock, context).language == language


@pytest.mark.parametrize(
    "text",
    [
        "Bonjour, quel est le prix?",
        "Hola, cuánto cuesta la habitación?",
        "你好，请问价格是多少？",
    ],
)
def test_account_agent_unsupported_languages_fail_closed(db_session, clock, text):
    context, workspace, message = scenario(db_session, clock)
    workspace.reply_languages = ["tr", "en", "ru", "de", "ar"]
    message.text = text
    db_session.flush()
    assert assemble(db_session, clock, context).language is None
