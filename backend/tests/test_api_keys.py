from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import User
from app.services.tokens import create_access_token


def _auth_headers(user_id):
    token = create_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def test_api_key_issue_list_revoke_flow(client, db_session: Session):
    user = User(
        id=uuid4(),
        github_id=900000111,
        username="apikey-user",
        email="apikey@test.dev",
        avatar_url=None,
    )
    db_session.add(user)
    db_session.commit()

    create = client.post(
        "/api/v1/auth/api-keys",
        json={"name": "ci-bot", "expires_in_days": 30},
        headers=_auth_headers(user.id),
    )
    assert create.status_code == 200
    payload = create.json()
    assert payload["api_key"].startswith("dlk_")
    assert payload["name"] == "ci-bot"
    assert payload["key_prefix"]
    assert len(payload["key_last4"]) == 4

    listed = client.get("/api/v1/auth/api-keys", headers=_auth_headers(user.id))
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert "api_key" not in items[0]
    assert items[0]["name"] == "ci-bot"

    revoke = client.delete(f"/api/v1/auth/api-keys/{payload['id']}", headers=_auth_headers(user.id))
    assert revoke.status_code == 204

    listed_after = client.get("/api/v1/auth/api-keys", headers=_auth_headers(user.id))
    assert listed_after.status_code == 200
    assert listed_after.json()["items"][0]["revoked_at"] is not None


def test_api_key_revoke_404_for_other_user(client, db_session: Session):
    owner = User(
        id=uuid4(),
        github_id=900000121,
        username="owner-user",
        email="owner@test.dev",
        avatar_url=None,
    )
    other = User(
        id=uuid4(),
        github_id=900000122,
        username="other-user",
        email="other@test.dev",
        avatar_url=None,
    )
    db_session.add(owner)
    db_session.add(other)
    db_session.commit()

    created = client.post(
        "/api/v1/auth/api-keys",
        json={"name": "owner-key"},
        headers=_auth_headers(owner.id),
    )
    key_id = created.json()["id"]

    forbidden_revoke = client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=_auth_headers(other.id))
    assert forbidden_revoke.status_code == 404
