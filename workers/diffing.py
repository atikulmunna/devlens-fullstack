"""Commit diff computation for commit-diff intelligence.

Parsing is pure and unit-testable; the git invocation is isolated so tests never shell out.
The default comparison is the head commit against its parent (head~1), which is robust and does
not depend on any prior analysis state.
"""

import logging
import re
import subprocess

logger = logging.getLogger(__name__)

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
# Stored line content per file and side, to keep rows bounded.
MAX_STORED_LINES = 200


def _term(body: str, whole: bool = True) -> re.Pattern:
    """A case-insensitive term bounded by non-alphanumerics. Unlike \\b, an underscore counts as a
    boundary, so snake_case names like verify_token or client_secret match."""
    return re.compile(rf"(?<![a-z0-9]){body}" + (r"(?![a-z0-9])" if whole else ""), re.IGNORECASE)


# Patterns that suggest a change touches security-sensitive surface area.
_SECURITY_PATTERNS = [
    ("auth", _term(r"auth(?:enticat|oriz)?", whole=False)),
    ("token", _term(r"tokens?")),
    ("jwt", _term(r"jwt")),
    ("oauth", _term(r"oauth")),
    ("password", _term(r"pass(?:word|wd)s?")),
    ("secret", _term(r"secrets?")),
    ("credential", _term(r"credential", whole=False)),
    ("api_key", _term(r"api[_-]?keys?")),
    ("env", re.compile(r"\.env\b|\bENV\[|os\.environ", re.IGNORECASE)),
    ("crypto", _term(r"(?:encrypt|decrypt|hash|hmac|bcrypt|sha256)")),
]


def parse_unified_diff(diff_text: str) -> list[dict]:
    """Parse `git diff` unified output into per-file change records."""
    files: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        if current is not None:
            files.append(current)

    for line in diff_text.splitlines():
        header = _DIFF_GIT_RE.match(line)
        if header:
            flush()
            current = {
                "path": header.group(2),
                "old_path": header.group(1),
                "status": "modified",
                "added": 0,
                "removed": 0,
                "hunks": [],
                "added_lines": [],
                "removed_lines": [],
            }
            continue
        if current is None:
            continue

        if line.startswith("new file mode"):
            current["status"] = "added"
        elif line.startswith("deleted file mode"):
            current["status"] = "deleted"
        elif line.startswith("rename from") or line.startswith("rename to"):
            current["status"] = "renamed"
        elif line.startswith("+++ b/"):
            current["path"] = line[6:]
        elif line.startswith("@@"):
            hunk = _HUNK_RE.match(line)
            if hunk:
                start = int(hunk.group(1))
                count = int(hunk.group(2)) if hunk.group(2) is not None else 1
                end = start + max(count, 1) - 1
                current["hunks"].append({"start": start, "end": end})
        elif line.startswith("+") and not line.startswith("+++"):
            current["added"] += 1
            current["added_lines"].append(line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            current["removed"] += 1
            current["removed_lines"].append(line[1:])

    flush()
    return files


def _security_labels(text: str) -> set[str]:
    return {label for label, pattern in _SECURITY_PATTERNS if pattern.search(text)}


def detect_security_touches(changed_files: list[dict]) -> list[dict]:
    """Flag changed files whose path or changed lines match security-sensitive patterns.

    Removed lines are flagged separately ("removed: auth"): deleting a check is as worth a look
    as adding one.
    """
    flags: list[dict] = []
    for entry in changed_files:
        path = entry.get("path") or ""
        added = _security_labels(path + "\n" + "\n".join(entry.get("added_lines") or []))
        removed = _security_labels("\n".join(entry.get("removed_lines") or []))
        matched = sorted(added) + [f"removed: {label}" for label in sorted(removed)]
        if matched:
            flags.append({"path": path, "categories": matched})
    return flags


def _run_git(args: list[str], cwd: str, timeout: int = 60) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        # Carry git's own message: CalledProcessError alone would hide why the command failed.
        stderr = result.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"git {args[0]} exited {result.returncode}: {stderr[:300]}")
    return result.stdout.decode("utf-8", errors="ignore")


def compute_commit_diff(repo_path: str, head_sha: str, timeout: int = 60) -> dict | None:
    """Compute the diff introduced by head_sha vs its parent. Best-effort: returns None on failure."""
    try:
        # Deepen so the parent commit is available in the shallow clone.
        try:
            _run_git(["fetch", "--depth", "2", "origin", head_sha], cwd=repo_path, timeout=timeout)
        except Exception:
            pass  # already deep enough, or offline; try the diff anyway

        try:
            base_sha = _run_git(["rev-parse", f"{head_sha}~1"], cwd=repo_path, timeout=timeout).strip()
        except Exception:
            return None  # no parent (initial commit) -> nothing to diff

        diff_text = _run_git(
            ["diff", "--unified=3", "--no-color", base_sha, head_sha],
            cwd=repo_path,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("Commit diff for %s failed: %s", head_sha, exc)
        return None

    changed_files = parse_unified_diff(diff_text)
    if not changed_files:
        return None

    for entry in changed_files:
        entry["added_lines"] = entry.get("added_lines", [])[:MAX_STORED_LINES]
        entry["removed_lines"] = entry.get("removed_lines", [])[:MAX_STORED_LINES]

    return {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "changed_files": changed_files,
        "security_flags": detect_security_touches(changed_files),
    }
