import subprocess
from pathlib import Path

import pytest

import churn


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ['git', '-c', 'user.name=T', '-c', 'user.email=t@example.com', *args], cwd=repo, check=True, capture_output=True
    )


def _commit(repo: Path, files: dict[str, str], message: str) -> None:
    for path, content in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(content, encoding='utf-8')
    _git(repo, 'add', '-A')
    _git(repo, 'commit', '-q', '-m', message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, 'init', '-q', '-b', 'main')
    _commit(tmp_path, {'app/core.py': '1', 'app/util.py': '1', 'gone.py': '1'}, 'one')
    _commit(tmp_path, {'app/core.py': '2'}, 'two')
    _commit(tmp_path, {'app/core.py': '3', 'app/util.py': '2'}, 'three')
    (tmp_path / 'gone.py').unlink()
    _commit(tmp_path, {}, 'remove gone.py')
    return tmp_path


def test_counts_commits_per_file_that_still_exists(repo: Path) -> None:
    # gone.py changed twice (added, removed) but is not in HEAD, so it cannot be a hotspot.
    assert churn.file_churn(str(repo)) == {'app/core.py': 3, 'app/util.py': 2}


def test_count_changes_keeps_the_busiest_files(monkeypatch) -> None:
    monkeypatch.setattr(churn, 'MAX_CHURN_FILES', 2)
    log = '\n'.join(['a.py', 'b.py', 'a.py', 'c.py', '', 'a.py', 'b.py', 'old.py'])
    assert churn.count_changes(log, {'a.py', 'b.py', 'c.py'}) == {'a.py': 3, 'b.py': 2}


def test_deepen_history_asks_git_for_the_window(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(churn, 'run_git', lambda args, cwd, timeout: calls.append((args, cwd, timeout)) or '')
    churn.deepen_history('/tmp/repo', 'abc123', days=365, timeout=90)
    ((args, cwd, timeout),) = calls
    assert (
        args[:2] == ['fetch', '--quiet'] and args[2].startswith('--shallow-since=') and args[3:] == ['origin', 'abc123']
    )
    assert (cwd, timeout) == ('/tmp/repo', 90)
