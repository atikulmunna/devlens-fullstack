from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import CodeChunk, Repository


def test_dependency_graph_returns_nodes_and_edges(client, db_session: Session):
    repo = Repository(
        id=uuid4(),
        github_url="https://github.com/test-owner/dep-graph",
        full_name="test-owner/dep-graph",
        owner="test-owner",
        name="dep-graph",
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()

    db_session.add_all(
        [
            CodeChunk(
                id=uuid4(),
                repo_id=repo.id,
                file_path="app/main.py",
                start_line=1,
                end_line=20,
                content="import app.utils\nfrom app.handlers import router\n",
                language="python",
            ),
            CodeChunk(
                id=uuid4(),
                repo_id=repo.id,
                file_path="app/utils.py",
                start_line=1,
                end_line=10,
                content="def helper():\n    return 1\n",
                language="python",
            ),
            CodeChunk(
                id=uuid4(),
                repo_id=repo.id,
                file_path="app/handlers.py",
                start_line=1,
                end_line=10,
                content="router = object()\n",
                language="python",
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/v1/repos/{repo.id}/dependency-graph")
    assert response.status_code == 200
    payload = response.json()
    assert payload["repo_id"] == str(repo.id)
    assert payload["stats"]["files_considered"] == 3
    assert payload["stats"]["edges_detected"] >= 2
    edge_pairs = {(edge["source"], edge["target"]) for edge in payload["edges"]}
    assert ("app/main.py", "app/utils.py") in edge_pairs
    assert ("app/main.py", "app/handlers.py") in edge_pairs


def test_dependency_graph_404_for_missing_repo(client):
    response = client.get(f"/api/v1/repos/{uuid4()}/dependency-graph")
    assert response.status_code == 404
