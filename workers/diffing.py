"""Commit diff computation for commit-diff intelligence.

Parsing is pure and unit-testable; the git invocation is isolated so tests never shell out.
The default comparison is the head commit against its parent (head~1), which is robust and does
not depend on any prior analysis state.
"""

import re
import subprocess

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

# Patterns that suggest a change touches security-sensitive surface area.
_SECURITY_PATTERNS = [
    ("auth", re.compile(r"\bauth(?:enticat|oriz)?", re.IGNORECASE)),
    ("token", re.compile(r"\btokens?\b", re.IGNORECASE)),
    ("jwt", re.compile(r"\bjwt\b", re.IGNORECASE)),
    ("oauth", re.compile(r"\boauth\b", re.IGNORECASE)),
    ("password", re.compile(r"\bpass(?:word|wd)\b", re.IGNORECASE)),
    ("secret", re.compile(r"\bsecret\b", re.IGNORECASE)),
    ("credential", re.compile(r"\bcredential", re.IGNORECASE)),
    ("api_key", re.compile(r"\bapi[_-]?key\b", re.IGNORECASE)),
    ("env", re.compile(r"\.env\b|\bENV\[|os\.environ", re.IGNORECASE)),
    ("crypto", re.compile(r"\b(?:encrypt|decrypt|hash|hmac|bcrypt|sha256)\b", re.IGNORECASE)),
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

    flush()
    return files


def detect_security_touches(changed_files: list[dict]) -> list[dict]:
    """Flag changed files whose added content matches security-sensitive patterns."""
    flags: list[dict] = []
    for entry in changed_files:
        path = entry.get("path") or ""
        haystack = "\n".join(entry.get("added_lines") or [])
        combined = f"{path}\n{haystack}"
        matched = sorted({label for label, pattern in _SECURITY_PATTERNS if pattern.search(combined)})
        if matched:
            flags.append({"path": path, "categories": matched})
    return flags


def _run_git(args: list[str], cwd: str, timeout: int = 60) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
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
    except Exception:
        return None

    changed_files = parse_unified_diff(diff_text)
    if not changed_files:
        return None

    # Cap stored added-line content to keep rows bounded.
    for entry in changed_files:
        entry["added_lines"] = entry.get("added_lines", [])[:200]

    return {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "changed_files": changed_files,
        "security_flags": detect_security_touches(changed_files),
    }
