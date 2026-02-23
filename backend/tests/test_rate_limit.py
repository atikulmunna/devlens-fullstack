from uuid import uuid4

from redis import Redis
from sqlalchemy.orm import Session

import app.api.v1.repos as repos_module
from app.config import settings
from app.db.models import Repository, User
from app.services.tokens import create_access_token


def _snapshot(commit_sha: str) -> dict:
    return {
        "github_url": "https://github.com/test-owner/rate-limit-repo",
        "full_name": "test-owner/rate-limit-repo",
        "owner": "test-owner",
        "name": "rate-limit-repo",
        "description": "Test repository",
        "stars": 10,
        "forks": 2,
        "language": "Python",
        "size_kb": 321,
        "default_branch": "main",
        "commit_sha": commit_sha,
    }


def _clear_rate_limit_keys() -> None:
    redis_client = Redis.from_url(settings.redis_url)
    keys = list(redis_client.scan_iter(match="ratelimit:*"))
    if keys:
        redis_client.delete(*keys)


def test_guest_rate_limit_for_analyze(client, monkeypatch) -> None:
    _clear_rate_limit_keys()
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 3600)
    monkeypatch.setattr(settings, "rate_limit_guest_per_window", 2)
    monkeypatch.setattr(settings, "rate_limit_auth_per_window", 50)
    monkeypatch.setattr(repos_module, "resolve_public_repo_snapshot", lambda _: _snapshot("sha-guest"))

    headers = {"X-Forwarded-For": "198.51.100.10"}
    r1 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**headers, "Idempotency-Key": "guest-1"},
    )
    r2 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**headers, "Idempotency-Key": "guest-2"},
    )
    r3 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**headers, "Idempotency-Key": "guest-3"},
    )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r2.headers["X-RateLimit-Remaining"] == "0"
    assert r3.headers["X-RateLimit-Remaining"] == "0"
    assert r3.headers["X-RateLimit-Limit"] == "2"
    assert r3.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in r3.headers


def test_auth_rate_limit_for_analyze(client, monkeypatch) -> None:
    _clear_rate_limit_keys()
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 3600)
    monkeypatch.setattr(settings, "rate_limit_guest_per_window", 2)
    monkeypatch.setattr(settings, "rate_limit_auth_per_window", 3)
    monkeypatch.setattr(repos_module, "resolve_public_repo_snapshot", lambda _: _snapshot("sha-auth"))

    token = create_access_token(uuid4())
    auth_headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": "198.51.100.11"}
    r1 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**auth_headers, "Idempotency-Key": "auth-1"},
    )
    r2 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**auth_headers, "Idempotency-Key": "auth-2"},
    )
    r3 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**auth_headers, "Idempotency-Key": "auth-3"},
    )
    r4 = client.post(
        "/api/v1/repos/analyze",
        json={"github_url": "https://github.com/test-owner/rate-limit-repo"},
        headers={**auth_headers, "Idempotency-Key": "auth-4"},
    )

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 200
    assert r4.status_code == 429
    assert r3.headers["X-RateLimit-Remaining"] == "0"
    assert r4.headers["X-RateLimit-Limit"] == "3"
    assert r4.json()["error"]["code"] == "RATE_LIMITED"


def _seed_chat_user_and_repo(db_session: Session) -> tuple[User, Repository]:
    user = User(
        id=uuid4(),
        github_id=900000901,
        username="rate-chat-user",
        email="rate-chat@test.dev",
        avatar_url=None,
    )
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/rate-chat-repo",
        full_name="test-owner/rate-chat-repo",
        owner="test-owner",
        name="rate-chat-repo",
        default_branch="main",
        latest_commit_sha="sha-rate-chat",
    )
    db_session.add(user)
    db_session.add(repo)
    db_session.commit()
    return user, repo


def test_auth_rate_limit_for_chat_session_create(client, db_session: Session, monkeypatch) -> None:
    _clear_rate_limit_keys()
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 3600)
    monkeypatch.setattr(settings, "rate_limit_guest_per_window", 2)
    monkeypatch.setattr(settings, "rate_limit_auth_per_window", 2)

    user, repo = _seed_chat_user_and_repo(db_session)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}", "X-Forwarded-For": "198.51.100.21"}

    r1 = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    r2 = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    r3 = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r2.headers["X-RateLimit-Remaining"] == "0"
    assert r3.headers["X-RateLimit-Limit"] == "2"
    assert r3.json()["error"]["code"] == "RATE_LIMITED"
