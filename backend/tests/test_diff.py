import json
from uuid import uuid4

from sqlalchemy.orm import Session

import app.api.v1.diff as diff_module
from app.db.models import CodeChunk, CommitDiff, Repository, User
from app.services.chat_synthesizer import ChatSynthesisError
from app.services.tokens import create_access_token


def _seed_repo_with_diff(db_session: Session) -> tuple[User, Repository]:
    user = User(
        id=uuid4(),
        github_id=900000130,
        username="diff-user",
        email="diff@test.dev",
        avatar_url=None,
    )
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/diff-repo",
        full_name="test-owner/diff-repo",
        owner="test-owner",
        name="diff-repo",
        default_branch="main",
        latest_commit_sha="sha-head",
    )
    db_session.add(user)
    db_session.add(repo)
    db_session.flush()
    db_session.add(
        CommitDiff(
            id=uuid4(),
            repo_id=repo.id,
            base_sha="sha-base",
            head_sha="sha-head",
            changed_files=[
                {
                    "path": "src/auth.py",
                    "status": "modified",
                    "added": 1,
                    "removed": 0,
                    "hunks": [{"start": 3, "end": 3}],
                    "added_lines": ["token = issue_token(user)"],
                }
            ],
            security_flags=[{"path": "src/auth.py", "categories": ["auth", "token"]}],
        )
    )
    db_session.commit()
    return user, repo


def test_diff_ask_runs_llm_off_the_event_loop(
    client, db_session: Session, monkeypatch, running_on_event_loop
) -> None:
    user, repo = _seed_repo_with_diff(db_session)
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}
    llm_on_event_loop: list[bool] = []

    def fake_stream(**_kwargs):
        llm_on_event_loop.append(running_on_event_loop())
        yield "The commit touches token issuance in src/auth.py."

    monkeypatch.setattr(diff_module, "synthesize_grounded_answer_stream", fake_stream)

    response = client.post(f"/api/v1/repos/{repo.id}/diff/ask", json={"question": "Is this risky?"}, headers=headers)

    assert response.status_code == 200
    assert "token issuance" in response.text
    assert '"security_categories": ["auth", "token"]' in response.text
    # Blocking LLM I/O must run in a worker thread; on the event loop it freezes every request.
    assert llm_on_event_loop == [False]


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _seed_chunks(db_session: Session, repo: Repository, files: dict[str, str]) -> None:
    for path, content in files.items():
        db_session.add(
            CodeChunk(id=uuid4(), repo_id=repo.id, file_path=path, start_line=1, end_line=5, content=content, language="py")
        )
    db_session.commit()


def test_get_diff_returns_summary_flags_and_blast_radius(client, db_session: Session) -> None:
    user, repo = _seed_repo_with_diff(db_session)
    _seed_chunks(
        db_session,
        repo,
        {
            "src/auth.py": "def issue_token(user): ...",
            "src/api.py": "from src.auth import issue_token",
            "src/cli.py": "from src.api import main",
            "src/unrelated.py": "import os",
        },
    )

    response = client.get(f"/api/v1/repos/{repo.id}/diff", headers=_auth_headers(user))

    assert response.status_code == 200
    payload = response.json()
    assert (payload["base_sha"], payload["head_sha"]) == ("sha-base", "sha-head")
    assert payload["changed_files"] == [{"path": "src/auth.py", "status": "modified", "added": 1, "removed": 0, "hunks": 1}]
    assert payload["security_flags"] == [{"path": "src/auth.py", "categories": ["auth", "token"]}]
    assert payload["blast_radius"]["impacted_files"] == ["src/api.py", "src/cli.py"]


def test_get_diff_defaults_to_latest_and_filters_by_head(client, db_session: Session) -> None:
    user, repo = _seed_repo_with_diff(db_session)
    db_session.add(
        CommitDiff(id=uuid4(), repo_id=repo.id, base_sha="sha-head", head_sha="sha-newer", changed_files=[], security_flags=[])
    )
    db_session.commit()

    latest = client.get(f"/api/v1/repos/{repo.id}/diff", headers=_auth_headers(user))
    older = client.get(f"/api/v1/repos/{repo.id}/diff", params={"head": "sha-head"}, headers=_auth_headers(user))

    assert latest.json()["head_sha"] == "sha-newer"
    assert older.json()["head_sha"] == "sha-head"


def test_get_diff_requires_auth(client, db_session: Session) -> None:
    _, repo = _seed_repo_with_diff(db_session)

    assert client.get(f"/api/v1/repos/{repo.id}/diff").status_code == 401


def test_get_diff_404_for_unknown_repo_and_missing_diff(client, db_session: Session) -> None:
    user, repo = _seed_repo_with_diff(db_session)
    db_session.query(CommitDiff).filter(CommitDiff.repo_id == repo.id).delete()
    db_session.commit()

    unknown = client.get(f"/api/v1/repos/{uuid4()}/diff", headers=_auth_headers(user))
    no_diff = client.get(f"/api/v1/repos/{repo.id}/diff", headers=_auth_headers(user))

    assert unknown.status_code == 404
    assert no_diff.status_code == 404
    assert no_diff.json()["error"]["message"] == "No commit diff available for this repository"


def test_diff_ask_falls_back_to_change_summary_when_llm_fails(client, db_session: Session, monkeypatch, caplog) -> None:
    user, repo = _seed_repo_with_diff(db_session)

    def failing_stream(**_kwargs):
        raise ChatSynthesisError("OpenRouter returned status 503")
        yield  # pragma: no cover - makes this a generator like the real synthesizer

    monkeypatch.setattr(diff_module, "synthesize_grounded_answer_stream", failing_stream)

    response = client.post(f"/api/v1/repos/{repo.id}/diff/ask", json={"question": "What changed?"}, headers=_auth_headers(user))

    assert response.status_code == 200
    events = [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]
    answer = "".join(event.get("token", "") for event in events)
    assert answer.strip() == "This commit (sha-head) changed: src/auth.py. Security-sensitive areas: auth, token."
    assert events[-1] == {"head_sha": "sha-head", "base_sha": "sha-base", "security_categories": ["auth", "token"]}
    assert "Diff LLM synthesis failed" in caplog.text and "status 503" in caplog.text


def test_diff_ask_rejects_blank_question_and_missing_diff(client, db_session: Session) -> None:
    user, repo = _seed_repo_with_diff(db_session)
    headers = _auth_headers(user)

    blank = client.post(f"/api/v1/repos/{repo.id}/diff/ask", json={"question": "   "}, headers=headers)
    db_session.query(CommitDiff).filter(CommitDiff.repo_id == repo.id).delete()
    db_session.commit()
    no_diff = client.post(f"/api/v1/repos/{repo.id}/diff/ask", json={"question": "What changed?"}, headers=headers)

    assert blank.status_code == 400
    assert no_diff.status_code == 404


def test_diff_contexts_show_removed_and_added_lines_in_diff_notation() -> None:
    entry = {
        "path": "app/views.py",
        "hunks": [{"start": 4, "end": 6}],
        "added_lines": ['    log.info("deleted")'],
        "removed_lines": ["    if not verify_token(request):", "        raise Forbidden()"],
    }

    context = diff_module._diff_contexts([entry])[0]

    assert context["content"].splitlines() == [
        "-    if not verify_token(request):",
        "-        raise Forbidden()",
        '+    log.info("deleted")',
    ]


def test_diff_contexts_accept_diffs_stored_before_removed_lines() -> None:
    entry = {"path": "a.py", "hunks": [], "added_lines": ["x = 1"]}

    assert diff_module._diff_contexts([entry])[0]["content"] == "+x = 1"


def test_files_named_in_the_question_come_first() -> None:
    files = [{"path": f"backend/app/m{n}.py"} for n in range(8)] + [{"path": "workers/embed_worker.py"}]

    ranked = diff_module._rank_for_question(files, "What did this commit remove from the embed worker?")

    assert ranked[0]["path"] == "workers/embed_worker.py"
    # Everything else keeps diff order.
    assert [f["path"] for f in ranked[1:]] == [f"backend/app/m{n}.py" for n in range(8)]
