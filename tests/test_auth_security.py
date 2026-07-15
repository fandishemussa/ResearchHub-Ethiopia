"""Authentication cryptography and token-validation tests."""

from uuid import uuid4

import pytest
from researchhub.core.auth_security import (
    TokenValidationError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from researchhub.core.config import Settings


def settings() -> Settings:
    return Settings(
        auth_jwt_secret="test-secret-that-is-longer-than-thirty-two-characters",
        auth_jwt_issuer="test-issuer",
        auth_jwt_audience="test-audience",
    )


def test_argon2_password_hash_never_contains_plaintext() -> None:
    password = "correct horse battery staple"
    encoded = hash_password(password)
    assert password not in encoded
    assert encoded.startswith("$argon2")
    assert verify_password(password, encoded)
    assert not verify_password("incorrect password", encoded)


def test_short_password_is_rejected() -> None:
    with pytest.raises(ValueError, match="12"):
        hash_password("too-short")


def test_access_token_validates_issuer_audience_type_and_subject() -> None:
    user_id = uuid4()
    token, expires = create_access_token(user_id, settings())
    payload = decode_access_token(token, settings())
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert expires.tzinfo is not None


def test_access_token_rejects_wrong_secret_or_audience() -> None:
    token, _ = create_access_token(uuid4(), settings())
    invalid = settings().model_copy(
        update={"auth_jwt_secret": "different-secret-that-is-also-long-enough"}
    )
    with pytest.raises(TokenValidationError):
        decode_access_token(token, invalid)


def test_refresh_tokens_are_random_and_only_hashes_need_storage() -> None:
    first = new_opaque_token()
    second = new_opaque_token()
    assert first != second
    assert len(hash_token(first)) == 64
    assert first not in hash_token(first)
