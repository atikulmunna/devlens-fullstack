import base64
import json
import time

import pytest
from fastapi import HTTPException

from app.services import github_oauth
from app.services import github_repos


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | list | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.request = None
        self.content = b"1" if payload is not None else b""

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, *_args, **_kwargs):
        return self.responses.pop(0)

    def get(self, *_args, **_kwargs):
        return self.responses.pop(0)


def test_oauth_state_generate_and_validate() -> None:
    state = github_oauth.generate_oauth_state("/dashboard")
    payload = github_oauth.validate_oauth_state(state)
    assert payload["next"] == "/dashboard"


def test_oauth_state_rejects_expired() -> None:
    body = {"iat": int(time.time()) - github_oauth.STATE_TTL_SECONDS - 1, "next": "/profile"}
    payload = base64.urlsafe_b64encode(json.dumps(body).encode("utf-8")).decode("utf-8").rstrip("=")
    signature = github_oauth._sign_payload(payload)
    with pytest.raises(HTTPException) as exc:
        github_oauth.validate_oauth_state(f"{payload}.{signature}")
    assert exc.value.status_code == 400


def test_exchange_code_for_access_token(monkeypatch) -> None:
    monkeypatch.setattr(github_oauth.httpx, "Client", lambda **_kwargs: FakeClient([FakeResponse(200, {"access_token": "abc"})]))
    assert github_oauth.exchange_code_for_access_token("code") == "abc"


def test_fetch_github_user_with_email_fallback(monkeypatch) -> None:
    responses = [
        FakeResponse(200, {"id": 1, "login": "octo", "email": None}),
        FakeResponse(200, [{"email": "octo@example.com", "primary": True, "verified": True}]),
    ]
    monkeypatch.setattr(github_oauth.httpx, "Client", lambda **_kwargs: FakeClient(responses))
    user = github_oauth.fetch_github_user("token")
    assert user["email"] == "octo@example.com"


def test_normalize_github_repo_url() -> None:
    assert github_repos.normalize_github_repo_url("https://github.com/a/b.git") == "https://github.com/a/b"
    with pytest.raises(HTTPException):
        github_repos.normalize_github_repo_url("https://example.com/a/b")


def test_resolve_public_repo_snapshot(monkeypatch) -> None:
    responses = [
        FakeResponse(
            200,
            {
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
                "name": "repo",
                "default_branch": "main",
                "description": "desc",
                "stargazers_count": 1,
                "forks_count": 2,
                "language": "Python",
                "size": 100,
            },
        ),
        FakeResponse(200, {"sha": "abc123"}),
    ]
    monkeypatch.setattr(github_repos.httpx, "Client", lambda **_kwargs: FakeClient(responses))
    snapshot = github_repos.resolve_public_repo_snapshot("https://github.com/owner/repo")
    assert snapshot["full_name"] == "owner/repo"
    assert snapshot["commit_sha"] == "abc123"
