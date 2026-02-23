from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisResult, Repository, ShareToken, User
from app.services.share_tokens import create_share_token
from app.services.tokens import create_access_token


def _seed_user_repo_result(db_session: Session) -> tuple[User, Repository]:
    user = User(
        id=uuid4(),
        github_id=900000050,
        username="share-user",
        email="share@test.dev",
        avatar_url=None,
    )
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/share-repo",
        full_name="test-owner/share-repo",
        owner="test-owner",
        name="share-repo",
        default_branch="main",
        latest_commit_sha="sha-share",
    )
    result = AnalysisResult(
        id=uuid4(),
        repo_id=repo.id,
        job_id=None,
        architecture_summary="Architecture summary",
        quality_score=79,
        language_breakdown={"Python": 100},
        contributor_stats={"top": []},
        tech_debt_flags={"todo_count": 0},
        file_tree={"children": []},
    )
    db_session.add(user)
    db_session.add(repo)
    db_session.flush()
    db_session.add(result)
    db_session.commit()
    return user, repo


def test_create_share_link_and_resolve_public_payload(client, db_session: Session) -> None:
    user, repo = _seed_user_repo_result(db_session)
    access = create_access_token(user.id)

    create_response = client.post(
        f"/api/v1/export/{repo.id}/share",
        json={},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["share_id"]
    assert create_payload["share_token"]
    assert "/share/" in create_payload["share_url"]

    share_row = db_session.execute(select(ShareToken).where(ShareToken.id == UUID(create_payload["share_id"]))).scalar_one()
    assert share_row.repo_id == repo.id
    assert share_row.user_id == user.id

    resolve_response = client.get(f"/api/v1/share/{create_payload['share_token']}")
    assert resolve_response.status_code == 200
    resolve_payload = resolve_response.json()
    assert resolve_payload["repo_id"] == str(repo.id)
    assert resolve_payload["repository"]["full_name"] == "test-owner/share-repo"
    assert resolve_payload["analysis"]["quality_score"] == 79
    assert "email" not in resolve_payload["repository"]
    assert "user_id" not in resolve_payload


def test_revoke_share_link_invalidates_token(client, db_session: Session) -> None:
    user, repo = _seed_user_repo_result(db_session)
    share_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    token = create_share_token(repo_id=repo.id, share_id=share_id, expires_at=expires_at)
    db_session.add(
        ShareToken(
            id=share_id,
            repo_id=repo.id,
            user_id=user.id,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    db_session.commit()

    access = create_access_token(user.id)
    revoke_response = client.delete(
        f"/api/v1/export/share/{share_id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert revoke_response.status_code == 204

    resolve_response = client.get(f"/api/v1/share/{token}")
    assert resolve_response.status_code == 401
    assert resolve_response.json()["error"]["code"] == "UNAUTHORIZED"
    assert resolve_response.json()["error"]["message"] == "Share token revoked"


def test_share_token_expired_returns_auth_error(client, db_session: Session) -> None:
    user, repo = _seed_user_repo_result(db_session)
    share_id = uuid4()
    expires_at = datetime.now(UTC) - timedelta(minutes=1)
    token = create_share_token(repo_id=repo.id, share_id=share_id, expires_at=expires_at)
    db_session.add(
        ShareToken(
            id=share_id,
            repo_id=repo.id,
            user_id=user.id,
            expires_at=expires_at,
            revoked_at=None,
        )
    )
    db_session.commit()

    resolve_response = client.get(f"/api/v1/share/{token}")
    assert resolve_response.status_code == 401
    assert resolve_response.json()["error"]["code"] == "UNAUTHORIZED"
    assert resolve_response.json()["error"]["message"] == "Share token expired"


def test_share_invalid_token_has_deterministic_auth_error(client) -> None:
    resolve_response = client.get("/api/v1/share/not-a-valid-token")
    assert resolve_response.status_code == 401
    payload = resolve_response.json()
    assert payload["error"]["code"] == "UNAUTHORIZED"
    assert payload["error"]["message"] == "Invalid share token"
