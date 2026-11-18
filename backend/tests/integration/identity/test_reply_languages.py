"""Reply-language schema, dedupe and the migrated approved-answer constraint."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.knowledge.approved_answers import create_answer
from tests.factories import knowledge_ctx, login, workspace_with_members


def test_reply_languages_patch_dedupes_and_rejects_french(client, db_session):
    workspace, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    path = f"/api/v1/workspaces/{workspace.id}"
    response = client.patch(
        path, json={"reply_languages": ["ru", "de", "ar", "ru"]}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply_languages"] == ["ru", "de", "ar"]
    assert client.patch(path, json={"reply_languages": ["fr"]}, headers=headers).status_code == 422


@pytest.mark.parametrize("language", ["ru", "de", "ar"])
def test_approved_answers_new_languages_and_database_constraint(db_session, clock, language):
    workspace, users = workspace_with_members(db_session)
    ctx = knowledge_ctx(workspace, users["owner"], "owner")
    kwargs = {
        "title": "Welcome",
        "intent": "greeting",
        "example_questions": ["Hello"],
        "answer_template": "Welcome!",
    }
    answer = create_answer(db_session, clock, ctx, language=language, **kwargs)
    assert answer.language == language
    with pytest.raises(AppError):
        create_answer(db_session, clock, ctx, language="fr", **kwargs)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE approved_answers SET language = 'fr' WHERE id = :id"), {"id": answer.id}
        )


def test_the_disclosure_text_accepts_the_new_reply_languages(client, db_session):
    workspace, users = workspace_with_members(db_session)
    headers = login(client, users["owner"])
    path = f"/api/v1/workspaces/{workspace.id}"
    texts = {"ru": "Ответ подготовлен ассистентом.", "de": "Vom Assistenten.", "ar": "رد آلي."}
    response = client.patch(path, json={"settings": {"disclosure_text": texts}}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["settings"]["disclosure_text"] == {"tr": "", "en": "", **texts}
    unknown = client.patch(
        path, json={"settings": {"disclosure_text": {"fr": "x"}}}, headers=headers
    )
    assert unknown.status_code == 422
