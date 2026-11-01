import json
import subprocess
from pathlib import Path

import pytest

import pr_risk
from github_api import GitHubError


def _git(repo: Path, *args: str, who: str = "Test") -> str:
    result = subprocess.run(
        ["git", "-c", f"user.name={who}", "-c", f"user.email={who.lower()}@example.com", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for path, content in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """main: a small package that Alice also worked on; feature (by Test): drops a token check and
    deletes a module something still imports."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _write(
        tmp_path,
        {
            "app/__init__.py": "",
            "app/auth.py": "def login(user):\n    if not verify_token(user):\n        raise PermissionError()\n",
            "app/views.py": "from app.auth import login\n",
            "app/api.py": "from app.views import login\n",
            "app/old.py": "X = 1\n",
            "app/uses_old.py": "from app.old import X\n",
            "tests/test_views.py": "from app.views import login\n",
            "README.md": "Set API_KEY before running.\n",
        },
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    with (tmp_path / "app/auth.py").open("a", encoding="utf-8") as handle:
        handle.write("# owner: accounts team\n")
    _git(tmp_path, "commit", "-q", "-am", "note the owner", who="Alice")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _write(tmp_path, {"app/auth.py": "def login(user):\n    return user\n", "README.md": "Set API_KEY and SECRET.\n"})
    (tmp_path / "app/old.py").unlink()
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "feature")
    return tmp_path


def test_analyze_reports_reach_removed_checks_and_deleted_imports(repo: Path) -> None:
    result = pr_risk.analyze(str(repo), "main", "feature")

    assert result["base_sha"] == _git(repo, "rev-parse", "main")
    assert result["head_sha"] == _git(repo, "rev-parse", "feature")
    assert {entry["path"] for entry in result["changed_files"]} == {"app/auth.py", "app/old.py", "README.md"}
    # Removing the token check rates high (the path counts too); the README only talks about keys.
    assert result["flags"] == [{"path": "app/auth.py", "categories": ["auth", "removed: token"], "severity": "high"}]
    assert result["blast"]["impacted_by_depth"] == [
        ["app/uses_old.py", "app/views.py"],
        ["app/api.py", "tests/test_views.py"],
    ]
    assert result["still_imported"] == {"app/old.py": ["app/uses_old.py"]}
    # The test reaches app/auth.py through app/views.py, so nothing changed is untested.
    assert result["tests"] == {"tests_to_run": ["tests/test_views.py"], "untested": []}
    assert result["removed_checks"] == [
        {"path": "app/auth.py", "line": 2, "kind": "auth check", "text": "if not verify_token(user):"}
    ]
    # Test wrote the pull request, so only Alice is suggested.
    assert result["reviewers"] == [
        {
            "name": "Alice",
            "email": "alice@example.com",
            "files": ["app/auth.py"],
            "commits": 1,
            "latest_sha": _git(repo, "rev-parse", "main"),
        }
    ]


def test_compares_against_the_fork_point_not_the_moved_base(repo: Path) -> None:
    # main moves on after the branch was cut; that change is not part of the pull request.
    _git(repo, "checkout", "-q", "main")
    _write(repo, {"app/later.py": "SECRET = 'x'\n"})
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "later on main")

    result = pr_risk.analyze(str(repo), "main", "feature")
    assert "app/later.py" not in {entry["path"] for entry in result["changed_files"]}


def test_main_prints_the_report_outside_a_pull_request(repo: Path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    code = pr_risk.main(["--repo-path", str(repo), "--repo", "acme/shop", "--base", "main", "--head", "feature"])

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("<!-- devlens-pr-risk -->")
    assert "#### Deleted but still imported" in out


def _pull_request_env(repo: Path, tmp_path: Path, monkeypatch, author: str = "test-gh") -> Path:
    event = tmp_path / "event.json"
    base, head = _git(repo, "rev-parse", "main"), _git(repo, "rev-parse", "feature")
    pull = {"number": 12, "base": {"sha": base}, "head": {"sha": head}, "user": {"login": author}}
    event.write_text(json.dumps({"pull_request": pull}))
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    # GitHub matches Alice's commit email to her account; no network in tests.
    monkeypatch.setattr(pr_risk, "commit_login", lambda **_kwargs: "alice-gh")
    return summary


def test_reviewers_link_to_their_account_and_never_include_the_author(repo: Path, tmp_path, monkeypatch) -> None:
    posted = {}
    monkeypatch.setattr(pr_risk, "upsert_comment", lambda **kwargs: posted.update(kwargs) or "created")

    _pull_request_env(repo, tmp_path, monkeypatch)
    pr_risk.main(["--repo-path", str(repo), "--repo", "acme/shop"])
    assert "- [alice-gh](https://github.com/alice-gh): 1 of the changed files, 1 commit" in posted["body"]

    # Alice opening the pull request herself: she is not suggested to herself.
    _pull_request_env(repo, tmp_path, monkeypatch, author="Alice-GH")
    pr_risk.main(["--repo-path", str(repo), "--repo", "acme/shop"])
    assert "#### Suggested reviewers" not in posted["body"]


def test_in_a_pull_request_it_comments_and_fills_the_job_summary(repo: Path, tmp_path: Path, monkeypatch) -> None:
    summary = _pull_request_env(repo, tmp_path, monkeypatch)
    posted = {}
    monkeypatch.setattr(pr_risk, "upsert_comment", lambda **kwargs: posted.update(kwargs) or "created")

    assert pr_risk.main(["--repo-path", str(repo), "--repo", "acme/shop"]) == 0
    assert posted["pr_number"] == 12 and posted["repo"] == "acme/shop" and posted["token"] == "t0ken"
    assert summary.read_text(encoding="utf-8") == posted["body"]


def test_a_read_only_fork_token_leaves_the_report_in_the_summary(repo: Path, tmp_path: Path, monkeypatch, capsys):
    summary = _pull_request_env(repo, tmp_path, monkeypatch)

    def refuse(**_kwargs):
        raise GitHubError(403, "Resource not accessible by integration")

    monkeypatch.setattr(pr_risk, "upsert_comment", refuse)
    assert pr_risk.main(["--repo-path", str(repo), "--repo", "acme/shop"]) == 0
    assert "::warning::" in capsys.readouterr().out
    assert summary.read_text(encoding="utf-8").startswith("<!-- devlens-pr-risk -->")
