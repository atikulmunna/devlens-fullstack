"""DevLens change risk for a pull request: what the changes reach, as one PR comment.

In GitHub Actions (see action.yml) it reads the pull request from the event and posts or updates
its comment. Locally it prints the report:

    python pr-risk/pr_risk.py --base main --head HEAD
"""

import argparse
import json
import os
import posixpath
import subprocess
import sys
from pathlib import Path

# The analysis is DevLens's own (import graph, diff parsing, severity), all standard library, so
# the Action runs on a bare runner with nothing installed. These are the repo's sibling folders.
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "workers")]

from app.services.blast_radius import blast_radius_from_graph, importers_by_file
from app.services.dependency_graph import JS_EXTENSIONS, TS_CONFIG_NAMES, build_dependency_graph
from app.services.flag_severity import with_severity
from covering_tests import covering_tests
from diffing import detect_security_touches, parse_unified_diff, removed_checks
from file_kinds import is_test_path
from github_comment import CommentError, upsert_comment
from risk_report import MARKER, render_report

# Generated or vendored files this large are not worth parsing for imports.
MAX_FILE_BYTES = 512 * 1024


def git(repo_path: str, *args: str, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo_path, input=stdin, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.decode('utf-8', errors='ignore').strip()[:300]}")
    return result.stdout


def _in_import_graph(path: str) -> bool:
    return path.endswith((".py", *JS_EXTENSIONS)) or posixpath.basename(path) in TS_CONFIG_NAMES


def _read_blobs(repo_path: str, shas: list[str]) -> list[str]:
    """Blob contents in order, from one `git cat-file --batch` call."""
    if not shas:
        return []
    out = git(repo_path, "cat-file", "--batch", stdin="".join(f"{sha}\n" for sha in shas).encode())
    contents, offset = [], 0
    for _ in shas:
        header_end = out.index(b"\n", offset)
        size = int(out[offset:header_end].split()[2])
        start = header_end + 1
        contents.append(out[start : start + size].decode("utf-8", errors="ignore"))
        offset = start + size + 1
    return contents


def tree_rows(repo_path: str, sha: str, keep) -> list[dict]:
    """{file_path, content} for the files at `sha` that `keep(path)` accepts, as the import graph expects."""
    entries = []
    for record in git(repo_path, "ls-tree", "-r", "-l", "-z", sha).split(b"\0"):
        if not record:
            continue
        meta, path = record.decode("utf-8", errors="ignore").split("\t", 1)
        _mode, kind, blob, size = meta.split()
        if kind == "blob" and size.isdigit() and int(size) <= MAX_FILE_BYTES and keep(path):
            entries.append((path, blob))
    contents = _read_blobs(repo_path, [blob for _, blob in entries])
    return [{"file_path": path, "content": content} for (path, _), content in zip(entries, contents, strict=True)]


def analyze(repo_path: str, base: str, head: str) -> dict:
    """Compare the pull request's head with where it branched from, as GitHub's "Files changed" does."""
    fork_point = git(repo_path, "merge-base", base, head).decode().strip()
    diff = git(repo_path, "diff", "--unified=3", "--no-color", "--find-renames", fork_point, head).decode(
        "utf-8", errors="ignore"
    )
    changed_files = parse_unified_diff(diff)
    deleted = {entry["path"] for entry in changed_files if entry["status"] == "deleted"}

    # Deleted files are read from the fork point, so imports of them still resolve and show up.
    rows = tree_rows(repo_path, head, _in_import_graph)
    rows += tree_rows(repo_path, fork_point, lambda path: path in deleted and _in_import_graph(path))
    graph = build_dependency_graph(rows)

    importers = importers_by_file(graph)
    still_imported = {
        path: sorted(importers[path] - deleted) for path in deleted if importers.get(path, set()) - deleted
    }
    blast = blast_radius_from_graph(graph, [entry["path"] for entry in changed_files])
    present = [entry["path"] for entry in changed_files if entry["path"] not in deleted]
    return {
        "base_sha": fork_point,
        "head_sha": git(repo_path, "rev-parse", head).decode().strip(),
        "changed_files": changed_files,
        "flags": with_severity(detect_security_touches(changed_files)),
        "blast": blast,
        "still_imported": still_imported,
        "removed_checks": removed_checks(changed_files),
        "tests": covering_tests(graph, present, blast["impacted_files"], is_test_path),
    }


def _pull_request_event() -> dict | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not os.path.exists(event_path):
        return None
    with open(event_path, encoding="utf-8") as handle:
        pull = json.load(handle).get("pull_request")
    if not pull:
        return None
    return {"number": pull["number"], "base": pull["base"]["sha"], "head": pull["head"]["sha"]}


def _post(repo: str, pr_number: int, body: str) -> int:
    try:
        outcome = upsert_comment(
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            token=os.environ["GITHUB_TOKEN"],
            repo=repo,
            pr_number=pr_number,
            body=body,
            marker=MARKER,
        )
    except CommentError as exc:
        if exc.status in (403, 404):
            # A pull request from a fork gets a read-only token; the job summary still has the report.
            print(f"::warning::DevLens could not comment on #{pr_number} ({exc}). The report is in the job summary.")
            return 0
        print(f"::error::DevLens could not comment on #{pr_number}: {exc}")
        return 1
    print(f"DevLens change risk comment {outcome} on #{pr_number}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", help="base commit or branch (default: the pull request's base)")
    parser.add_argument("--head", help="head commit or branch (default: the pull request's head)")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/name, for links")
    parser.add_argument("--repo-path", default=".", help="the git checkout to read")
    parser.add_argument("--print", dest="print_only", action="store_true", help="print instead of commenting")
    args = parser.parse_args(argv)

    event = _pull_request_event()
    base = args.base or (event or {}).get("base")
    head = args.head or (event or {}).get("head")
    if not base or not head:
        parser.error("no pull request in GITHUB_EVENT_PATH; pass --base and --head")

    result = analyze(args.repo_path, base, head)
    body = render_report(repo=args.repo, devlens_url=os.environ.get("DEVLENS_URL", ""), **result)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(body)
    if event and not args.print_only and os.environ.get("GITHUB_TOKEN"):
        return _post(args.repo, event["number"], body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
