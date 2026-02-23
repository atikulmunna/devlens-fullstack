from uuid import uuid4

from fastapi import HTTPException, status
import app.api.v1.repos as repos_module


def _assert_error_envelope(payload: dict):
    assert 'error' in payload
    assert isinstance(payload['error'], dict)
    assert 'code' in payload['error']
    assert 'message' in payload['error']
    assert 'details' in payload['error']


def test_error_envelope_bad_request(client):
    response = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://example.com/not-github'},
        headers={'X-Forwarded-For': f'203.0.113.{uuid4().int % 200 + 1}'},
    )
    assert response.status_code == 400
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'BAD_REQUEST'


def test_error_envelope_unauthorized(client):
    response = client.get('/api/v1/auth/me')
    assert response.status_code == 401
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'UNAUTHORIZED'


def test_error_envelope_forbidden(client):
    response = client.delete(
        '/api/v1/auth/logout',
        headers={'origin': 'http://evil.example', 'x-csrf-token': 'x'},
        cookies={'devlens_refresh_token': 'abc', 'devlens_csrf_token': 'x'},
    )
    assert response.status_code == 403
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'FORBIDDEN'


def test_error_envelope_not_found(client):
    response = client.get('/api/v1/does-not-exist')
    assert response.status_code == 404
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'NOT_FOUND'


def test_error_envelope_validation_error(client):
    # Missing required github_url field
    response = client.post(
        '/api/v1/repos/analyze',
        json={},
        headers={'X-Forwarded-For': f'198.51.100.{uuid4().int % 200 + 1}'},
    )
    assert response.status_code == 422
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'VALIDATION_ERROR'
    assert 'errors' in payload['error']['details']


def test_error_envelope_upstream_error_mapping(client, monkeypatch):
    monkeypatch.setattr(
        repos_module,
        'resolve_public_repo_snapshot',
        lambda _url: (_ for _ in ()).throw(
            HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='Failed to fetch repository metadata')
        ),
    )
    response = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://github.com/test-owner/test-repo'},
        headers={'X-Forwarded-For': f'192.0.2.{uuid4().int % 200 + 1}'},
    )
    assert response.status_code == 502
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'UPSTREAM_ERROR'


def test_error_envelope_internal_error_mapping(client, monkeypatch):
    monkeypatch.setattr(
        repos_module,
        'resolve_public_repo_snapshot',
        lambda _url: (_ for _ in ()).throw(
            HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Unexpected server error')
        ),
    )
    response = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://github.com/test-owner/test-repo'},
        headers={'X-Forwarded-For': f'203.0.113.{uuid4().int % 200 + 1}'},
    )
    assert response.status_code == 500
    payload = response.json()
    _assert_error_envelope(payload)
    assert payload['error']['code'] == 'INTERNAL_ERROR'
