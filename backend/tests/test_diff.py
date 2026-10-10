from uuid import uuid4

from sqlalchemy.orm import Session

import app.api.v1.diff as diff_module
from app.db.models import CommitDiff, Repository, User
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
