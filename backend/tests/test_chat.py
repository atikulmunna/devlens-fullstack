import json
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

import app.api.v1.chat as chat_module
from app.db.models import AnalysisResult, ChatMessage, ChatSession, CodeChunk, Repository, User
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
    monkeypatch.setattr(
        chat_module,
        "synthesize_grounded_answer_stream",
        lambda **_kwargs: iter(["JWT refresh is handled in src/auth/jwt.py."]),
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

    rows = (
        db_session.execute(
            select(ChatMessage).where(ChatMessage.session_id == UUID(session_id)).order_by(ChatMessage.created_at.asc())
        )
        .scalars()
        .all()
    )
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


def test_chat_language_question_answers_from_the_analysis_breakdown(client, db_session: Session, monkeypatch) -> None:
    user, repo, chunk_id = _seed_user_and_repo(db_session)
    db_session.add(
        AnalysisResult(
            id=uuid4(),
            repo_id=repo.id,
            language_breakdown={"py": 60.0, "rst": 25.0, "sh": 0.4, "yaml": 14.6},
        )
    )
    db_session.commit()
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers)
    session_id = created.json()["session_id"]

    calls: list[dict] = []
    monkeypatch.setattr(chat_module, "hybrid_search_chunks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(chat_module, "synthesize_grounded_answer_stream", _recording_synthesizer(calls))

    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "what are the languages used?"},
        headers=headers,
    )
    assert stream.status_code == 200
    assert "Python" in stream.text
    assert "Shell" in stream.text
    assert "reStructuredText" not in stream.text
    assert calls == []
    assert '"no_citation": true' in stream.text


def test_chat_response_hydrates_content_when_missing_from_results(client, db_session: Session, monkeypatch) -> None:
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
    captured: dict = {}

    def fake_stream(**kwargs):
        captured.update(kwargs)
        return iter(["Refresh logic appears in src/auth/jwt.py with token verification steps."])

    monkeypatch.setattr(chat_module, "synthesize_grounded_answer_stream", fake_stream)

    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "where is jwt refresh logic?"},
        headers=headers,
    )
    assert stream.status_code == 200
    assert '"anchor": "src/auth/jwt.py#L10-L30"' in stream.text
    assert '"no_citation": false' in stream.text
    # The LLM must receive the chunk's code, which retrieval results do not carry.
    assert [context["content"] for context in captured["contexts"]] == ["jwt refresh token logic"]

    assistant = db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == UUID(session_id), ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
    ).scalar_one()
    assert "token verification steps" in assistant.content


def test_chat_stream_runs_llm_off_the_event_loop(
    client, db_session: Session, monkeypatch, running_on_event_loop
) -> None:
    user, repo, chunk_id = _seed_user_and_repo(db_session)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
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
                "rerank_score": 0.71,
            }
        ],
    )
    llm_on_event_loop: list[bool] = []

    def fake_stream(**_kwargs):
        llm_on_event_loop.append(running_on_event_loop())
        yield "JWT refresh lives in src/auth/jwt.py."

    monkeypatch.setattr(chat_module, "synthesize_grounded_answer_stream", fake_stream)

    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "where is jwt refresh logic?"},
        headers=headers,
    )
    assert stream.status_code == 200
    assert "event: done" in stream.text
    # Blocking LLM I/O must run in a worker thread; on the event loop it freezes every request.
    assert llm_on_event_loop == [False]

    assistant = db_session.execute(
        select(ChatMessage).where(ChatMessage.session_id == UUID(session_id), ChatMessage.role == "assistant")
    ).scalar_one()
    assert assistant.content == "JWT refresh lives in src/auth/jwt.py."


def test_chat_falls_back_when_synthesizer_fails(client, db_session: Session, monkeypatch, caplog) -> None:
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

    def _boom(**_kwargs):
        raise chat_module.ChatSynthesisError("provider unavailable")

    monkeypatch.setattr(chat_module, "synthesize_grounded_answer_stream", _boom)

    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/message",
        json={"content": "explain token flow"},
        headers=headers,
    )
    assert stream.status_code == 200
    assert '"anchor": "src/auth/jwt.py#L10-L30"' in stream.text
    assert '"no_citation": false' in stream.text

    assistant = db_session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == UUID(session_id), ChatMessage.role == "assistant")
        .order_by(ChatMessage.created_at.desc())
    ).scalar_one()
    assert "Based on indexed code context" in assistant.content
    # The fallback is visible to the user; the reason must be visible to operators.
    assert f"Chat LLM synthesis failed for session {session_id}: provider unavailable" in caplog.text


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


def _ask(client, db_session: Session, monkeypatch, question: str, synthesize, extra_chunks: tuple = ()) -> str:
    """Send one question against a single retrieved chunk and return the SSE text.

    `extra_chunks` are (file_path, content) rows stored for the repo but not retrieved.
    """
    user, repo, chunk_id = _seed_user_and_repo(db_session)
    for file_path, content in extra_chunks:
        db_session.add(
            CodeChunk(
                id=uuid4(),
                repo_id=repo.id,
                file_path=file_path,
                start_line=1,
                end_line=5,
                content=content,
                language="md",
            )
        )
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    session_id = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers).json()[
        "session_id"
    ]
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
                "rerank_score": 0.71,
            }
        ],
    )
    monkeypatch.setattr(chat_module, "synthesize_grounded_answer_stream", synthesize)
    response = client.post(f"/api/v1/chat/sessions/{session_id}/message", json={"content": question}, headers=headers)
    assert response.status_code == 200
    return response.text


def _recording_synthesizer(calls: list[dict], answer: str = "From the model."):
    def synthesize(**kwargs):
        calls.append(kwargs)
        return iter([answer])

    return synthesize


def test_summary_question_is_answered_by_the_model_in_summary_mode(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []

    text = _ask(
        client, db_session, monkeypatch, "Summarize this repository", _recording_synthesizer(calls, "- Signs tokens.")
    )

    assert len(calls) == 1
    assert calls[0]["mode"] == "summary"
    assert calls[0]["contexts"][0]["content"] == "jwt refresh token logic"
    assert "Signs tokens." in text
    # The old template answer is gone.
    assert "Purpose:" not in text
    assert "Output formats" not in text


def test_regular_question_uses_answer_mode(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []

    _ask(client, db_session, monkeypatch, "Where is the refresh token checked?", _recording_synthesizer(calls))

    assert calls[0]["mode"] == "answer"


def test_stack_trace_question_is_not_answered_with_languages(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []

    text = _ask(
        client, db_session, monkeypatch, "Where does this stack trace come from?", _recording_synthesizer(calls)
    )

    assert len(calls) == 1
    assert "appears to" not in text


def test_summary_falls_back_to_snippets_when_the_model_fails(client, db_session: Session, monkeypatch) -> None:
    def failing(**_kwargs):
        raise chat_module.ChatSynthesisError("provider unavailable")

    text = _ask(client, db_session, monkeypatch, "Give me an overview", failing)

    assert "src/auth/jwt.py:10" in text
    assert "Purpose:" not in text


def test_language_question_matches_phrases_not_bare_words() -> None:
    assert chat_module._language_question("What language is this written in?")
    assert chat_module._language_question("Which languages does it use?")
    assert chat_module._language_question("What is the tech stack?")
    assert not chat_module._language_question("Where does this stack trace come from?")
    assert not chat_module._language_question("How does it call the language model?")


def test_language_answer_counts_code_only_and_ranks_by_share() -> None:
    answer = chat_module._language_answer({"py": 62.4, "rst": 22.6, "md": 3.3, "sh": 2.0, "makefile": 0.6, "toml": 4.6})

    assert answer == (
        "The code is mostly Python (96%), with Shell (3%), Makefile (under 1%). Shares are by size of the indexed code."
    )


def test_language_answer_single_language_and_missing_breakdown() -> None:
    assert chat_module._language_answer({"ts": 70, "tsx": 20, "json": 10}) == "The code is written in TypeScript."
    assert chat_module._language_answer({"md": 100}) is None
    assert chat_module._language_answer(None) is None


def test_language_question_without_a_breakdown_goes_to_the_model(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []

    _ask(client, db_session, monkeypatch, "What language is this written in?", _recording_synthesizer(calls))

    assert len(calls) == 1


def test_stale_vector_hits_are_not_sent_to_the_model(client, db_session: Session, monkeypatch) -> None:
    user, repo, chunk_id = _seed_user_and_repo(db_session)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    session_id = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers).json()[
        "session_id"
    ]
    stale = {"chunk_id": str(uuid4()), "file_path": "src/gone.py", "start_line": 1, "end_line": 9, "rerank_score": 0.9}
    real = {"chunk_id": chunk_id, "file_path": "src/auth/jwt.py", "start_line": 10, "end_line": 30, "rerank_score": 0.7}
    monkeypatch.setattr(chat_module, "hybrid_search_chunks", lambda *_args, **_kwargs: [stale, real])
    calls: list[dict] = []
    monkeypatch.setattr(chat_module, "synthesize_grounded_answer_stream", _recording_synthesizer(calls))

    client.post(
        f"/api/v1/chat/sessions/{session_id}/message", json={"content": "how are tokens refreshed?"}, headers=headers
    )

    assert [context["file_path"] for context in calls[0]["contexts"]] == ["src/auth/jwt.py"]


README_CHUNKS = (("README.md", "# chat-repo Signs and refreshes tokens."), ("docs/README.md", "Docs build notes."))


def test_summary_puts_the_root_readme_first(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []

    _ask(client, db_session, monkeypatch, "Give me a high-level overview", _recording_synthesizer(calls), README_CHUNKS)

    paths = [context["file_path"] for context in calls[0]["contexts"]]
    assert paths == ["README.md", "src/auth/jwt.py"]


def test_regular_question_does_not_add_the_readme(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []
    _ask(client, db_session, monkeypatch, "Where are tokens refreshed?", _recording_synthesizer(calls), README_CHUNKS)

    assert [context["file_path"] for context in calls[0]["contexts"]] == ["src/auth/jwt.py"]


def test_every_context_is_a_numbered_citation_flagged_by_use(client, db_session: Session, monkeypatch) -> None:
    calls: list[dict] = []

    text = _ask(
        client,
        db_session,
        monkeypatch,
        "Give me an overview",
        _recording_synthesizer(calls, "Signs tokens [2]."),
        README_CHUNKS,
    )

    done = json.loads(text.split("event: done\ndata: ", 1)[1].split("\n", 1)[0])
    assert [(c["ref"], c["file_path"], c["cited"]) for c in done["citations"]] == [
        (1, "README.md", False),
        (2, "src/auth/jwt.py", True),
    ]
    assert done["no_citation"] is False


def test_follow_up_question_sends_earlier_turns_as_history(client, db_session: Session, monkeypatch) -> None:
    user, repo, chunk_id = _seed_user_and_repo(db_session)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    session_id = client.post("/api/v1/chat/sessions", json={"repo_id": str(repo.id)}, headers=headers).json()[
        "session_id"
    ]
    hit = {"chunk_id": chunk_id, "file_path": "src/auth/jwt.py", "start_line": 10, "end_line": 30, "rerank_score": 0.7}
    monkeypatch.setattr(chat_module, "hybrid_search_chunks", lambda *_args, **_kwargs: [hit])
    calls: list[dict] = []
    monkeypatch.setattr(
        chat_module, "synthesize_grounded_answer_stream", _recording_synthesizer(calls, "In jwt.py [1].")
    )

    for question in ["Where are tokens refreshed?", "And how long do they last?"]:
        client.post(f"/api/v1/chat/sessions/{session_id}/message", json={"content": question}, headers=headers)

    assert calls[0]["history"] == []
    assert calls[1]["history"] == [
        {"role": "user", "content": "Where are tokens refreshed?"},
        {"role": "assistant", "content": "In jwt.py [1]."},
    ]


def test_history_is_limited_to_the_most_recent_messages(db_session: Session) -> None:
    user, repo, _ = _seed_user_and_repo(db_session)
    session = ChatSession(id=uuid4(), repo_id=repo.id, user_id=user.id)
    db_session.add(session)
    db_session.flush()
    for n in range(10):
        db_session.add(
            ChatMessage(id=uuid4(), session_id=session.id, role="user" if n % 2 == 0 else "assistant", content=f"m{n}")
        )
        db_session.flush()
        db_session.execute(
            text("UPDATE chat_messages SET created_at = now() + make_interval(secs => :n) WHERE content = :c"),
            {"n": n, "c": f"m{n}"},
        )
    db_session.commit()

    history = chat_module._recent_history(db_session, session.id)

    assert [turn["content"] for turn in history] == ["m4", "m5", "m6", "m7", "m8", "m9"]
