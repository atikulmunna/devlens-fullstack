import asyncio
import os
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import delete
from sqlalchemy.orm import Session

# Ensure tests can run even outside docker-compose env injection.
ENV_DEFAULTS = {
    "APP_NAME": "DevLens Backend",
    "ENV": "test",
    "DATABASE_URL": "postgresql+psycopg://postgres:postgres@postgres:5432/devlens",
    "REDIS_URL": "redis://redis:6379/0",
    "QDRANT_URL": "http://qdrant:6333",
    "QDRANT_COLLECTION": "devlens_code_chunks",
    "GITHUB_CLIENT_ID": "test-client-id",
    "GITHUB_CLIENT_SECRET": "test-client-secret",
    "GITHUB_OAUTH_REDIRECT_URI": "http://localhost:8000/api/v1/auth/callback",
    "FRONTEND_URL": "http://localhost:3000",
    "JWT_SECRET": "test-secret",
    "JWT_ACCESS_TTL_MINUTES": "15",
    "JWT_REFRESH_TTL_DAYS": "7",
    "SHARE_TOKEN_TTL_DAYS": "7",
}

for key, value in ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)

from app.config import settings
from app.db.models import (
    AnalysisJob,
    AnalysisResult,
    ChatMessage,
    ChatSession,
    CodeChunk,
    CommitDiff,
    DeadLetterJob,
    RefreshToken,
    Repository,
    ShareToken,
    User,
)
from app.db.session import SessionLocal
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    # Rate-limit buckets live in Redis and outlive each test (and each run), so a suite with
    # many analyze calls would otherwise start returning 429 depending on order and history.
    redis_client = Redis.from_url(settings.redis_url)
    try:
        keys = list(redis_client.scan_iter(match="ratelimit:*"))
        if keys:
            redis_client.delete(*keys)
    finally:
        redis_client.close()


@pytest.fixture()
def running_on_event_loop() -> Callable[[], bool]:
    """Probe for fakes: True when called on the asyncio event loop thread, where blocking I/O stalls the server."""

    def probe() -> bool:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    return probe


@pytest.fixture()
def db_session() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def cleanup_test_users(db_session: Session):
    # Cleanup before and after each test for deterministic auth/repo tests.
    def purge_test_rows() -> None:
        test_repo_ids = db_session.query(Repository.id).filter(
            Repository.github_url.like("https://github.com/test-owner/%")
        )
        test_user_ids = db_session.query(User.id).filter(User.github_id >= 900000000)
        test_session_ids = db_session.query(ChatSession.id).filter(
            (ChatSession.repo_id.in_(test_repo_ids)) | (ChatSession.user_id.in_(test_user_ids))
        )

        db_session.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(test_session_ids)))
        db_session.execute(delete(ChatSession).where(ChatSession.id.in_(test_session_ids)))
        db_session.execute(delete(CodeChunk).where(CodeChunk.repo_id.in_(test_repo_ids)))
        db_session.execute(delete(CommitDiff).where(CommitDiff.repo_id.in_(test_repo_ids)))
        db_session.execute(delete(AnalysisResult).where(AnalysisResult.repo_id.in_(test_repo_ids)))
        db_session.execute(delete(DeadLetterJob).where(DeadLetterJob.repo_id.in_(test_repo_ids)))
        db_session.execute(delete(AnalysisJob).where(AnalysisJob.repo_id.in_(test_repo_ids)))
        db_session.execute(delete(ShareToken).where(ShareToken.repo_id.in_(test_repo_ids)))
        db_session.execute(delete(Repository).where(Repository.github_url.like("https://github.com/test-owner/%")))

        db_session.execute(delete(RefreshToken).where(RefreshToken.user_id.in_(test_user_ids)))
        db_session.execute(delete(ShareToken).where(ShareToken.user_id.in_(test_user_ids)))
        db_session.execute(delete(User).where(User.github_id >= 900000000))
        db_session.commit()

    purge_test_rows()

    yield

    db_session.rollback()
    purge_test_rows()
