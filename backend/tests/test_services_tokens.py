from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import share_tokens
from app.services import tokens


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    access = tokens.create_access_token(user_id)
    payload = tokens.decode_access_token(access)
    assert payload["sub"] == str(user_id)
    assert payload["typ"] == "access"


def test_decode_access_token_rejects_invalid_value() -> None:
    with pytest.raises(HTTPException) as exc:
        tokens.decode_access_token("not-a-token")
    assert exc.value.status_code == 401


def test_refresh_helpers() -> None:
    refresh = tokens.issue_refresh_token()
    assert isinstance(refresh, str) and len(refresh) > 20
    digest = tokens.hash_refresh_token(refresh)
    assert len(digest) == 64
    assert tokens.new_refresh_token_id()
    assert tokens.refresh_expiry() > datetime.now(UTC)


def test_share_token_round_trip() -> None:
    repo_id = uuid4()
    share_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=1)
    token = share_tokens.create_share_token(repo_id, share_id, expires_at)
    payload = share_tokens.decode_share_token(token)
    assert payload["sub"] == str(repo_id)
    assert payload["jti"] == str(share_id)
    assert payload["typ"] == "share"


def test_share_token_expiry_bounds(monkeypatch) -> None:
    monkeypatch.setattr(share_tokens.settings, "share_token_ttl_days", 7)
    assert share_tokens.share_token_expiry() > datetime.now(UTC)
    with pytest.raises(HTTPException):
        share_tokens.share_token_expiry(0)
    with pytest.raises(HTTPException):
        share_tokens.share_token_expiry(31)
