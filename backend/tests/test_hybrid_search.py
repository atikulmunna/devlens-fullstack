from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

import app.api.v1.repos as repos_module
from app.db.models import Repository
from app.services import retrieval_hybrid


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, captured: dict, payload: dict, status_code: int = 200):
        self.captured = captured
        self.payload = payload
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, json):
        self.captured["url"] = url
        self.captured["json"] = json
        return FakeResponse(self.status_code, self.payload)


def _seed_repo(db_session: Session) -> Repository:
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/hybrid-repo",
        full_name="test-owner/hybrid-repo",
        owner="test-owner",
        name="hybrid-repo",
        default_branch="main",
        latest_commit_sha="sha-hybrid",
    )
    db_session.add(repo)
    db_session.commit()
    return repo


def test_dense_search_qdrant_includes_repo_filter(monkeypatch) -> None:
    captured = {}
    payload = {
        "result": [
            {
                "score": 0.9,
                "payload": {"chunk_id": str(uuid4()), "repo_id": "r1", "file_path": "a.py"},
            }
        ]
    }
    monkeypatch.setattr(retrieval_hybrid.httpx, "Client", lambda **_kwargs: FakeClient(captured, payload))

    results = retrieval_hybrid.dense_search_qdrant("repo-1", "auth token", 5)
    assert len(results) == 1
    qfilter = captured["json"]["filter"]["must"][0]
    assert qfilter["key"] == "repo_id"
    assert qfilter["match"]["value"] == "repo-1"


def test_dense_search_qdrant_requires_repo_id() -> None:
    with pytest.raises(HTTPException) as exc:
        retrieval_hybrid.dense_search_qdrant("", "query", 5)
    assert exc.value.status_code == 400


def test_hybrid_endpoint_returns_results(client, db_session: Session, monkeypatch) -> None:
    repo = _seed_repo(db_session)
    monkeypatch.setattr(
        repos_module,
        "hybrid_search_chunks",
        lambda *_args, **_kwargs: [
            {
                "chunk_id": str(uuid4()),
                "file_path": "src/auth/jwt.py",
                "start_line": 1,
                "end_line": 20,
                "language": "py",
                "dense_score": 0.8,
                "lexical_score": 0.5,
                "rerank_score": 0.72,
            }
        ],
    )

    response = client.get(f"/api/v1/repos/{repo.id}/search/hybrid", params={"q": "jwt refresh", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["repo_id"] == str(repo.id)
    assert payload["total"] == 1
    assert payload["results"][0]["rerank_score"] == 0.72


def test_hybrid_endpoint_404(client) -> None:
    response = client.get(f"/api/v1/repos/{uuid4()}/search/hybrid", params={"q": "jwt"})
    assert response.status_code == 404
