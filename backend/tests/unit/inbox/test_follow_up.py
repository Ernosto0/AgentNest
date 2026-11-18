import pytest
from pydantic import ValidationError

from app.identity.schemas import WorkspaceSettings, WorkspaceSettingsPatch
from app.inbox.follow_up import DEFAULT_TEXT
from app.knowledge.claims import validate_claims
from app.knowledge.render import render


@pytest.mark.parametrize("language", ["tr", "en"])
def test_neutral_default_is_grounded(language: str) -> None:
    result = render(DEFAULT_TEXT[language], [], language)
    assert result.ok
    assert validate_claims(result.text, result, language).passed


def test_defaults_and_generic_patch() -> None:
    settings = WorkspaceSettings()
    assert settings.follow_up_enabled is False
    assert settings.follow_up_hours == 6
    assert settings.follow_up_text.model_dump() == {"tr": "", "en": ""}
    with pytest.raises(ValidationError):
        WorkspaceSettingsPatch.model_validate({"follow_up_enabled": True})


@pytest.mark.parametrize("hours", [0, 21])
def test_hours_bounds(hours: int) -> None:
    with pytest.raises(ValidationError):
        WorkspaceSettings(follow_up_hours=hours)
