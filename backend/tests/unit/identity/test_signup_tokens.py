from datetime import timedelta

import pytest

from app.core.errors import AppError
from app.identity.signup import VERIFICATION_TTL, issue_token, validate_token


def test_signed_tokens_are_random_purpose_bound_and_expiring(settings, clock):
    token = issue_token(settings, clock)
    assert token != issue_token(settings, clock)
    validate_token(settings, clock, token)
    other = settings.model_copy(update={"secret_key": type(settings.secret_key)("another-secret")})
    for bad in ("garbage", token + "x", token.replace(token.split(".")[0], "forged")):
        with pytest.raises(AppError):
            validate_token(settings, clock, bad)
    with pytest.raises(AppError):
        validate_token(other, clock, token)
    clock.advance(VERIFICATION_TTL - timedelta(seconds=1))
    validate_token(settings, clock, token)
    clock.advance(timedelta(seconds=1))
    with pytest.raises(AppError):
        validate_token(settings, clock, token)
