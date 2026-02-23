from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

import app.api.v1.chat as chat_module
from app.db.models import ChatMessage, Repository, User
from app.services.tokens import create_access_token


def _seed_user_and_repo(db_session: Session) -> tuple[User, Repository, str]:
    user = User(
        id=uuid4(),
        github_id=900000120,
        username="chat-user",
        email="chat@test.dev",
        avatar_url=None,
    )
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/chat-repo",
        full_name="test-owner/chat-repo",
        owner="test-owner",
        name="chat-repo",
        default_branch="main",
        latest_commit_sha="sha-chat",
    )
    db_session.add(user)
    db_session.add(repo)
    db_session.flush()
    chunk_id = str(uuid4())
    db_session.execute(
        text(
            """
            INSERT INTO code_chunks (id, repo_id, file_path, start_line, end_line, content, language, qdrant_point_id)
            VALUES (CAST(:id AS uuid), CAST(:repo_id AS uuid), :file_path, :start_line, :end_line, :content, :language, NULL)
            """
        ),
        {
            "id": chunk_id,
            "repo_id": str(repo.id),
            "file_path": "src/auth/jwt.py",
            "start_line": 10,
            "end_line": 30,
            "content": "jwt refresh token logic",
            "language": "py",
        },
    )
    db_session.commit()
    return user, repo, chunk_id


def test_chat_session_create_get_delete(client, db_session: Session) -> None:
    user, repo, _ = _seed_user_and_repo(db_session)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    fetched = client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session_id
    assert fetched.json()["messages"] == []

    deleted = client.delete(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 204

    missing = client.get(f"/api/v1/chat/sessions/{session_id}", headers=headers)
    assert missing.status_code == 404


def test_chat_message_stream_persists_assistant_with_citations(client, db_session: Session, monkeypatch) -> None:
    user, repo, chunk_id = _seed_user_and_repo(db_session)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    session_id = created.json()["session_id"]

    monkeypatch.setattr(
        chat_module,
        "hybrid_search_chunks",
        lambda *_args, **_kwargs: [
            {
                "chunk_id": chunk_id,
                "file_path": "src/auth/jwt.py",
                "start_line": 10,
                "end_line": 30,
                "language": "py",
                "dense_score": 0.8,
                "lexical_score": 0.4,
                "rerank_score": 0.71,
            }
        ],
    )

    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "where is jwt refresh logic?", "top_k": 5},
        headers=headers,
    )
    assert stream.status_code == 200
    assert "event: delta" in stream.text
    assert "event: done" in stream.text
    assert '"no_citation": false' in stream.text

    rows = db_session.execute(
        select(ChatMessage).where(ChatMessage.session_id == UUID(session_id)).order_by(ChatMessage.created_at.asc())
    ).scalars().all()
    assert len(rows) == 2
    assert rows[0].role == "user"
    assert rows[1].role == "assistant"
    assert rows[1].source_citations
    assert rows[1].source_citations["no_citation"] is False
    assert rows[1].source_citations["citations"]
    assert rows[1].source_citations["citations"][0]["anchor"].startswith("src/auth/jwt.py#L")


def test_chat_message_stream_no_citation_flag_when_no_results(client, db_session: Session, monkeypatch) -> None:
    user, repo, _ = _seed_user_and_repo(db_session)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    session_id = created.json()["session_id"]

    monkeypatch.setattr(chat_module, "hybrid_search_chunks", lambda *_args, **_kwargs: [])
    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "unknown topic"},
        headers=headers,
    )
    assert stream.status_code == 200
    assert '"no_citation": true' in stream.text

    assistant = db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == UUID(session_id), ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
    ).scalar_one()
    assert assistant.source_citations["no_citation"] is True


def test_chat_sessions_list_filtered_by_repo(client, db_session: Session) -> None:
    user, repo, _ = _seed_user_and_repo(db_session)
    other_repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/chat-repo-2",
        full_name="test-owner/chat-repo-2",
        owner="test-owner",
        name="chat-repo-2",
        default_branch="main",
        latest_commit_sha="sha-chat-2",
    )
    db_session.add(other_repo)
    db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    s1 = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    s2 = client.post("/api/v1/chat/sessions", json={"repo_id": str(other_repo.id)}, headers=headers)
    assert s1.status_code == 200
    assert s2.status_code == 200

    listed = client.get(f"/api/v1/chat/sessions?repo_id={repo.id}", headers=headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["repo_id"] == str(repo.id)


def test_chat_suggested_questions(client, db_session: Session) -> None:
    user, repo, _ = _seed_user_and_repo(db_session)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(f"/api/v1/chat/repos/{repo.id}/suggestions?limit=4", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["repo_id"] == str(repo.id)
    assert len(payload["suggestions"]) == 4
    assert any("auth" in item.lower() or "token" in item.lower() for item in payload["suggestions"])
