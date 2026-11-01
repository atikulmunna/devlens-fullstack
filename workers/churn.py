"""How often each file changed recently, from the clone's own git history (for hotspots).

The parse stage clones one commit deep, so the history is fetched first: just the window counted
here, and best-effort, like the commit diff. A file that changes often and that many others
import is where a change most often reaches far; the backend ranks those as hotspots.
"""

from collections import Counter
from datetime import UTC, datetime, timedelta

from diffing import run_git

CHURN_DAYS = 365
# Bounds the stored map; the busiest files are the ones that can be hotspots.
MAX_CHURN_FILES = 300


def deepen_history(repo_path: str, commit_sha: str, days: int, timeout: int) -> None:
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    run_git(["fetch", "--quiet", f"--shallow-since={since}", "origin", commit_sha], cwd=repo_path, timeout=timeout)


def count_changes(log_text: str, present: set[str]) -> dict[str, int]:
    """Commits per file from `git log --format= --name-only`, for files that still exist."""
    counts = Counter(line for line in log_text.splitlines() if line in present)
    return dict(counts.most_common(MAX_CHURN_FILES))


def file_churn(repo_path: str, days: int = CHURN_DAYS, timeout: int = 60) -> dict[str, int]:
    """Commits in the last `days` per file in HEAD (merges left out: they repeat their branch's changes)."""
    log = run_git(
        ["log", f"--since={days} days ago", "--no-merges", "--format=", "--name-only", "HEAD"],
        cwd=repo_path,
        timeout=timeout,
    )
    present = set(run_git(["ls-files"], cwd=repo_path, timeout=timeout).splitlines())
    return count_changes(log, present)
