from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Repository


def _seed_repo_with_chunks(db_session: Session) -> Repository:
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/lexical-repo",
        full_name="test-owner/lexical-repo",
        owner="test-owner",
        name="lexical-repo",
        default_branch="main",
        latest_commit_sha="sha-lexical",
    )
    db_session.add(repo)
    db_session.flush()

    db_session.execute(
        text(
            """
            INSERT INTO code_chunks (id, repo_id, file_path, start_line, end_line, content, language, qdrant_point_id)
            VALUES (:id, :repo_id, :file_path, :start_line, :end_line, :content, :language, NULL)
            """
        ),
        [
            {
                "id": uuid4(),
                "repo_id": repo.id,
                "file_path": "src/payment/service.py",
                "start_line": 1,
                "end_line": 40,
                "content": "payment service validates invoices",
                "language": "py",
            },
            {
                "id": uuid4(),
                "repo_id": repo.id,
                "file_path": "src/auth/jwt.py",
                "start_line": 1,
                "end_line": 40,
                "content": "jwt token refresh flow",
                "language": "py",
            },
            {
                "id": uuid4(),
                "repo_id": repo.id,
                "file_path": "README.md",
                "start_line": 1,
                "end_line": 20,
                "content": "project setup and usage",
                "language": "md",
            },
        ],
    )
    db_session.commit()
    return repo


def test_lexical_search_returns_ranked_results(client, db_session: Session) -> None:
    repo = _seed_repo_with_chunks(db_session)

    response = client.get(f"/api/v1/repos/{repo.id}/search/lexical", params={"q": "payment service", "limit": 5})
    assert response.status_code == 200
    payload = response.json()

    assert payload["repo_id"] == str(repo.id)
    assert payload["total"] >= 1
    assert payload["results"][0]["file_path"] == "src/payment/service.py"
    assert payload["results"][0]["score"] > 0


def test_lexical_search_rejects_empty_query(client, db_session: Session) -> None:
    repo = _seed_repo_with_chunks(db_session)
    response = client.get(f"/api/v1/repos/{repo.id}/search/lexical", params={"q": "   "})
    assert response.status_code == 400


def test_lexical_search_404_for_missing_repo(client) -> None:
    response = client.get(f"/api/v1/repos/{uuid4()}/search/lexical", params={"q": "payment"})
    assert response.status_code == 404
