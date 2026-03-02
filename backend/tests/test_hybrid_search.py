from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
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


def _seed_chunk(db_session: Session, repo_id: str, chunk_id: str, file_path: str, content: str) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO code_chunks (id, repo_id, file_path, start_line, end_line, content, language, qdrant_point_id)
            VALUES (CAST(:id AS uuid), CAST(:repo_id AS uuid), :file_path, 1, 5, :content, 'py', NULL)
            """
        ),
        {"id": chunk_id, "repo_id": repo_id, "file_path": file_path, "content": content},
    )
    db_session.commit()


def test_hybrid_search_flag_off_keeps_deterministic_ranking(db_session: Session, monkeypatch) -> None:
    repo = _seed_repo(db_session)
    c1 = str(uuid4())
    c2 = str(uuid4())
    monkeypatch.setattr(retrieval_hybrid.settings, "reranker_enabled", False)
    monkeypatch.setattr(
        retrieval_hybrid,
        "lexical_search_chunks",
        lambda *_args, **_kwargs: [
            {"chunk_id": c1, "file_path": "src/a.py", "start_line": 1, "end_line": 10, "language": "py", "score": 0.9},
            {"chunk_id": c2, "file_path": "src/b.py", "start_line": 1, "end_line": 10, "language": "py", "score": 0.2},
        ],
    )
    monkeypatch.setattr(retrieval_hybrid, "dense_search_qdrant", lambda *_args, **_kwargs: [])
    called = {"value": False}

    def fake_apply(*_args, **_kwargs):
        called["value"] = True
        return []

    monkeypatch.setattr(retrieval_hybrid, "_apply_cross_encoder_rerank", fake_apply)
    results = retrieval_hybrid.hybrid_search_chunks(db_session, repo.id, "auth token", limit=2)
    assert called["value"] is False
    assert [row["chunk_id"] for row in results] == [c1, c2]


def test_hybrid_search_flag_on_applies_cross_encoder_order(db_session: Session, monkeypatch) -> None:
    repo = _seed_repo(db_session)
    c1 = str(uuid4())
    c2 = str(uuid4())
    _seed_chunk(db_session, str(repo.id), c1, "src/a.py", "auth token create")
    _seed_chunk(db_session, str(repo.id), c2, "src/b.py", "refresh token validate")

    monkeypatch.setattr(retrieval_hybrid.settings, "reranker_enabled", True)
    monkeypatch.setattr(retrieval_hybrid.settings, "reranker_model", "test-model")
    monkeypatch.setattr(retrieval_hybrid.settings, "reranker_candidate_limit", 10)
    monkeypatch.setattr(
        retrieval_hybrid,
        "lexical_search_chunks",
        lambda *_args, **_kwargs: [
            {"chunk_id": c1, "file_path": "src/a.py", "start_line": 1, "end_line": 10, "language": "py", "score": 0.9},
            {"chunk_id": c2, "file_path": "src/b.py", "start_line": 1, "end_line": 10, "language": "py", "score": 0.3},
        ],
    )
    monkeypatch.setattr(retrieval_hybrid, "dense_search_qdrant", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        retrieval_hybrid,
        "rerank_candidates",
        lambda *_args, **_kwargs: {c1: 0.1, c2: 0.99},
    )

    results = retrieval_hybrid.hybrid_search_chunks(db_session, repo.id, "refresh token", limit=2)
    assert [row["chunk_id"] for row in results] == [c2, c1]
    assert results[0]["rerank_score"] == 0.99


def test_hybrid_search_reranker_failure_falls_back_to_deterministic(db_session: Session, monkeypatch) -> None:
    repo = _seed_repo(db_session)
    c1 = str(uuid4())
    c2 = str(uuid4())
    _seed_chunk(db_session, str(repo.id), c1, "src/a.py", "auth token create")
    _seed_chunk(db_session, str(repo.id), c2, "src/b.py", "refresh token validate")

    monkeypatch.setattr(retrieval_hybrid.settings, "reranker_enabled", True)
    monkeypatch.setattr(retrieval_hybrid.settings, "reranker_model", "test-model")
    monkeypatch.setattr(
        retrieval_hybrid,
        "lexical_search_chunks",
        lambda *_args, **_kwargs: [
            {"chunk_id": c1, "file_path": "src/a.py", "start_line": 1, "end_line": 10, "language": "py", "score": 0.9},
            {"chunk_id": c2, "file_path": "src/b.py", "start_line": 1, "end_line": 10, "language": "py", "score": 0.1},
        ],
    )
    monkeypatch.setattr(retrieval_hybrid, "dense_search_qdrant", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        retrieval_hybrid,
        "rerank_candidates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("reranker down")),
    )

    results = retrieval_hybrid.hybrid_search_chunks(db_session, repo.id, "auth token", limit=2)
    assert [row["chunk_id"] for row in results] == [c1, c2]
