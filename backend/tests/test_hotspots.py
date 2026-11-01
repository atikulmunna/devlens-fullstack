from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AnalysisResult, CodeChunk, Repository
from app.services.hotspots import rank_hotspots


def _graph(edges: list[tuple[str, str]], nodes: tuple[str, ...]) -> dict:
    return {
        "nodes": [{"id": path} for path in nodes],
        "edges": [{"source": source, "target": target} for source, target in edges],
    }


GRAPH = _graph(
    [("app/a.py", "app/core.py"), ("app/b.py", "app/core.py"), ("app/c.py", "app/core.py"), ("web/x.ts", "web/api.ts")],
    nodes=("app/core.py", "app/a.py", "app/b.py", "app/c.py", "app/busy.py", "web/api.ts", "web/x.ts", "README.md"),
)


def test_ranked_by_changes_times_reach() -> None:
    churn = {"app/core.py": 4, "app/busy.py": 9, "web/api.ts": 5, "app/once.py": 1}
    ranked = rank_hotspots(churn, GRAPH)
    # core: 4 x (1 + 3) = 16; web/api: 5 x 2 = 10; busy: 9 x 1 = 9.
    assert [(h["path"], h["changes"], h["importers"], h["score"]) for h in ranked] == [
        ("app/core.py", 4, 3, 16),
        ("web/api.ts", 5, 1, 10),
        ("app/busy.py", 9, 0, 9),
    ]


def test_non_code_files_and_single_changes_are_not_hotspots() -> None:
    churn = {"README.md": 30, "uv.lock": 12, "app/a.py": 1}
    assert rank_hotspots(churn, GRAPH) == []


def test_the_list_is_capped() -> None:
    churn = {path: 2 for path in ("app/a.py", "app/b.py", "app/c.py")}
    assert len(rank_hotspots(churn, GRAPH, limit=2)) == 2


def _repo(db_session: Session, debt: dict | None) -> Repository:
    name = f"hot-{uuid4().hex[:8]}"
    repo = Repository(
        id=uuid4(),
        github_url=f"https://github.com/test-owner/{name}",
        full_name=f"test-owner/{name}",
        owner="test-owner",
        name=name,
        default_branch="main",
    )
    db_session.add(repo)
    db_session.flush()
    files = {"app/core.py": "X = 1\n", "app/a.py": "from app.core import X\n", "app/b.py": "from app.core import X\n"}
    db_session.add_all(
        CodeChunk(
            id=uuid4(),
            repo_id=repo.id,
            file_path=path,
            start_line=1,
            end_line=1,
            content=content,
            language="python",
        )
        for path, content in files.items()
    )
    if debt is not None:
        db_session.add(AnalysisResult(id=uuid4(), repo_id=repo.id, job_id=None, tech_debt_flags=debt))
    db_session.commit()
    return repo


def test_endpoint_ranks_the_analysis_churn_over_the_import_graph(client, db_session: Session) -> None:
    repo = _repo(db_session, {"churn_days": 365, "churn": {"app/core.py": 3, "app/a.py": 5}})

    payload = client.get(f"/api/v1/repos/{repo.id}/hotspots").json()

    assert payload["measured"] is True and payload["window_days"] == 365
    assert payload["hotspots"] == [
        {"path": "app/core.py", "changes": 3, "importers": 2, "score": 9},
        {"path": "app/a.py", "changes": 5, "importers": 0, "score": 5},
    ]


def test_endpoint_says_when_history_was_not_measured(client, db_session: Session) -> None:
    older = _repo(db_session, {"measured": True, "long_function_count": 0})
    assert client.get(f"/api/v1/repos/{older.id}/hotspots").json() == {
        "measured": False,
        "window_days": None,
        "hotspots": [],
    }
    unanalyzed = _repo(db_session, None)
    assert client.get(f"/api/v1/repos/{unanalyzed.id}/hotspots").json()["measured"] is False
    assert client.get(f"/api/v1/repos/{uuid4()}/hotspots").status_code == 404
