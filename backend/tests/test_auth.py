from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import app.api.v1.auth as auth_module
from app.db.models import RefreshToken, User
from app.services.github_oauth import generate_oauth_state, validate_oauth_state
from app.services.tokens import hash_refresh_token, refresh_expiry


def test_auth_github_redirect_contains_valid_state(client: TestClient) -> None:
    response = client.get('/api/v1/auth/github', params={'next': '/profile'}, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers['location']
    assert location.startswith('https://github.com/login/oauth/authorize')
    assert 'client_id=' in location
    assert 'state=' in location

    state = location.split('state=', 1)[1]
    decoded = validate_oauth_state(state)
    assert decoded['next'] == '/profile'


def test_auth_callback_rejects_invalid_state(client: TestClient) -> None:
    response = client.get('/api/v1/auth/callback?code=dummy&state=bad')
    assert response.status_code == 400


def test_auth_callback_upserts_user_and_sets_refresh_cookie(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, 'exchange_code_for_access_token', lambda code: 'mock-token')
    monkeypatch.setattr(
        auth_module,
        'fetch_github_user',
        lambda token: {
            'id': 900000001,
            'login': 'oauth-test-user',
            'email': 'oauth@test.dev',
            'avatar_url': 'https://example.com/avatar.png',
        },
    )

    state = generate_oauth_state('/profile')
    response = client.get(f'/api/v1/auth/callback?code=dummy&state={state}', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['location'].endswith('/profile')
    assert 'devlens_refresh_token=' in response.headers.get('set-cookie', '')
    assert 'devlens_csrf_token=' in response.headers.get('set-cookie', '')

    user = db_session.execute(select(User).where(User.github_id == 900000001)).scalar_one()
    assert user.username == 'oauth-test-user'

    refresh_rows = db_session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id)).scalars().all()
    assert len(refresh_rows) == 1
    assert refresh_rows[0].revoked_at is None


def test_refresh_me_logout_flow(client: TestClient, db_session: Session) -> None:
    user = User(
        id=uuid4(),
        github_id=900000002,
        username='refresh-user',
        email='refresh@test.dev',
        avatar_url=None,
    )
    db_session.add(user)
    db_session.flush()

    raw_refresh = 'test-refresh-token-flow'
    db_session.add(
        RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=refresh_expiry(),
            revoked_at=None,
        )
    )
    db_session.commit()

    client.cookies.set('devlens_refresh_token', raw_refresh)
    client.cookies.set('devlens_csrf_token', 'csrf-token-1')
    refresh_response = client.post(
        '/api/v1/auth/refresh',
        headers={
            'origin': 'http://localhost:3000',
            'x-csrf-token': 'csrf-token-1',
        },
    )
    assert refresh_response.status_code == 200
    payload = refresh_response.json()
    assert payload['token_type'] == 'bearer'
    assert isinstance(payload['access_token'], str) and payload['access_token']

    me_response = client.get('/api/v1/auth/me', headers={'Authorization': f"Bearer {payload['access_token']}"})
    assert me_response.status_code == 200
    assert me_response.json()['username'] == 'refresh-user'

    new_csrf = refresh_response.cookies.get('devlens_csrf_token')
    client.cookies.set('devlens_csrf_token', new_csrf)
    logout_response = client.delete(
        '/api/v1/auth/logout',
        headers={
            'origin': 'http://localhost:3000',
            'x-csrf-token': new_csrf,
        },
    )
    assert logout_response.status_code == 204

    # Reusing rotated token after logout must fail.
    retry_response = client.post(
        '/api/v1/auth/refresh',
        headers={
            'origin': 'http://localhost:3000',
            'x-csrf-token': new_csrf,
        },
    )
    assert retry_response.status_code == 401


def test_refresh_rejects_expired_token(client: TestClient, db_session: Session) -> None:
    user = User(
        id=uuid4(),
        github_id=900000003,
        username='expired-user',
        email='expired@test.dev',
        avatar_url=None,
    )
    db_session.add(user)
    db_session.flush()

    raw_refresh = 'test-refresh-token-expired'
    db_session.add(
        RefreshToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC),
            revoked_at=None,
        )
    )
    db_session.commit()

    client.cookies.set('devlens_refresh_token', raw_refresh)
    client.cookies.set('devlens_csrf_token', 'csrf-token-expired')
    response = client.post(
        '/api/v1/auth/refresh',
        headers={
            'origin': 'http://localhost:3000',
            'x-csrf-token': 'csrf-token-expired',
        },
    )
    assert response.status_code == 401


def test_refresh_rejects_missing_csrf(client: TestClient) -> None:
    client.cookies.set('devlens_refresh_token', 'anything')
    response = client.post('/api/v1/auth/refresh', headers={'origin': 'http://localhost:3000'})
    assert response.status_code == 403


def test_logout_rejects_invalid_origin(client: TestClient) -> None:
    client.cookies.set('devlens_refresh_token', 'anything')
    client.cookies.set('devlens_csrf_token', 'csrf-token')
    response = client.delete(
        '/api/v1/auth/logout',
        headers={
            'origin': 'http://evil.example',
            'x-csrf-token': 'csrf-token',
        },
    )
    assert response.status_code == 403
