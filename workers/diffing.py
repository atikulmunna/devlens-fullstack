"""Commit diff computation for commit-diff intelligence.

Parsing is pure and unit-testable; the git invocation is isolated so tests never shell out.
The default comparison is the head commit against its parent (head~1), which is robust and does
not depend on any prior analysis state.
"""

import logging
import re
import subprocess

from file_kinds import is_test_path

logger = logging.getLogger(__name__)

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
# Stored line content per file and side, to keep rows bounded.
MAX_STORED_LINES = 200
# Hunk lines (with context) kept for the diff viewer, per file and per commit.
MAX_HUNK_LINES_PER_FILE = 300
MAX_HUNK_LINES_PER_DIFF = 3000


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
    old_no = new_no = 0

    def flush() -> None:
        if current is not None:
            files.append(current)

    def keep(line: dict) -> None:
        """Record a hunk line for the viewer, until the file's cap."""
        if current["hunk_line_count"] >= MAX_HUNK_LINES_PER_FILE:
            current["truncated"] = True
            return
        current["hunks"][-1]["lines"].append(line)
        current["hunk_line_count"] += 1

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
                "hunk_line_count": 0,
                "truncated": False,
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
                old_no = int(hunk.group(1))
                start = new_no = int(hunk.group(2))
                count = int(hunk.group(3)) if hunk.group(3) is not None else 1
                end = start + max(count, 1) - 1
                current["hunks"].append({"start": start, "end": end, "old_start": old_no, "lines": []})
        elif line.startswith("+") and not line.startswith("+++"):
            current["added"] += 1
            current["added_lines"].append(line[1:])
            if current["hunks"]:
                keep({"kind": "+", "text": line[1:], "new": new_no})
                new_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            current["removed"] += 1
            current["removed_lines"].append(line[1:])
            if current["hunks"]:
                keep({"kind": "-", "text": line[1:], "old": old_no})
                old_no += 1
        elif line.startswith(" ") and current["hunks"]:
            keep({"kind": " ", "text": line[1:], "old": old_no, "new": new_no})
            old_no += 1
            new_no += 1

    flush()
    return files


# A reference to a variable (`${JWT_SECRET}`, Caddy's `{$GATE_SECRET}`, `process.env.API_KEY`,
# `os.environ["TOKEN"]`, `os.getenv("TOKEN")`) passes a secret along without containing one.
_ENV_REFERENCE_RE = re.compile(
    r"\$\{[A-Za-z_]\w*\}|\{\$[A-Za-z_]\w*\}|process\.env\.[A-Za-z_]\w*"
    r"|os\.(?:environ(?:\.get)?|getenv)\s*[\[(]\s*['\"][A-Za-z_]\w*['\"]\s*[\])]?"
)
# `NAME: ${NAME}` or `NAME=${NAME}` hands a variable through under its own name.
_PASS_THROUGH_RE = re.compile(r"^\s*[\w.-]+\s*[:=]\s*['\"]?(?:\$\{\w+\}|\{\$\w+\})['\"]?\s*$")


def _security_labels(text: str) -> set[str]:
    labels: set[str] = set()
    kept = []
    for line in text.splitlines():
        stripped, references = _ENV_REFERENCE_RE.subn("", line)
        if references:
            labels.add("env")
            if _PASS_THROUGH_RE.match(line):
                continue
        kept.append(stripped)
    rest = "\n".join(kept)
    return labels | {label for label, pattern in _SECURITY_PATTERNS if pattern.search(rest)}


# Documentation describes secrets and sign-in, and stylesheets name classes like `.auth`, without
# either being a security change; flagging them buries the changes that are.
NOT_FLAGGED_EXTENSIONS = (".md", ".rst", ".txt", ".adoc", ".css", ".scss", ".sass", ".less")


def _never_flagged(path: str) -> bool:
    return path.lower().endswith(NOT_FLAGGED_EXTENSIONS)


def label_security_lines(changed_files: list[dict]) -> None:
    """Mark each added or removed hunk line that matches a security pattern, for the viewer."""
    for entry in changed_files:
        if _never_flagged(entry.get("path") or ""):
            continue
        for hunk in entry.get("hunks") or []:
            for line in hunk.get("lines") or []:
                if line["kind"] != " ":
                    labels = _security_labels(line["text"])
                    if labels:
                        line["labels"] = sorted(labels)


def _cap_hunk_lines(changed_files: list[dict]) -> None:
    """Keep the stored diff bounded: once the commit's line budget is spent, later files keep only counts."""
    budget = MAX_HUNK_LINES_PER_DIFF
    for entry in changed_files:
        count = entry.pop("hunk_line_count", 0)
        if count > budget:
            for hunk in entry.get("hunks") or []:
                hunk["lines"] = []
            entry["truncated"] = True
            budget = 0
        else:
            budget -= count


def detect_security_touches(changed_files: list[dict]) -> list[dict]:
    """Flag changed files whose path or changed lines match security-sensitive patterns.

    Removed lines are flagged separately ("removed: auth"): deleting a check is as worth a look
    as adding one. Test files are marked, so their severity can stay low: their fixtures name
    tokens and passwords all the time.
    """
    flags: list[dict] = []
    for entry in changed_files:
        path = entry.get("path") or ""
        if _never_flagged(path):
            continue
        added = _security_labels(path + "\n" + "\n".join(entry.get("added_lines") or []))
        removed = _security_labels("\n".join(entry.get("removed_lines") or []))
        matched = sorted(added) + [f"removed: {label}" for label in sorted(removed)]
        if matched:
            flag = {"path": path, "categories": matched}
            if is_test_path(path):
                flag["test"] = True
            flags.append(flag)
    return flags


# Code that guards something. Removing one is the change most worth a reviewer's look, so each is
# reported with its file and line. Checked in order; the first kind that matches names the line.
_CHECK_PATTERNS = [
    (
        "permission check",
        re.compile(
            r"@\w*(?:permission|role|admin|staff)s?_required\b|\bhas_perms?\(|\bcheck_?permissions?\(|\bhasPermission\("
            r"|\bis_(?:admin|staff|superuser)\b|\braise\s+(?:PermissionDenied|Forbidden)"
            r"|\bstatus(?:_code)?\s*=\s*(?:status\.HTTP_)?403|\babort\(\s*403|\.status\(\s*403\s*\)",
            re.IGNORECASE,
        ),
    ),
    (
        "auth check",
        re.compile(
            r"@\w*(?:login|auth\w*)_required\b|@requires?_(?:auth|login)\w*"
            r"|Depends\(\s*(?:get_current_\w+|require_\w+|verify_\w+)|\bis_authenticated\b|\bisAuthenticated\("
            r"|\brequireAuth\b|\bensureAuth\w*|passport\.authenticate|\bverify_?token\w*\(|jwt\.verify\("
            r"|\braise\s+(?:Unauthorized|NotAuthenticated)"
            # 401 means "not signed in"; 403 (above) means "signed in, not allowed".
            r"|\bstatus(?:_code)?\s*=\s*(?:status\.HTTP_)?401|\babort\(\s*401|\.status\(\s*401\s*\)",
            re.IGNORECASE,
        ),
    ),
    ("CSRF protection", re.compile(r"csrf", re.IGNORECASE)),
    ("input validation", re.compile(r"\bvalidate\w*\(|\.is_valid\(\)|\bsanitize\w*\(|\bescape(?:_html)?\(", re.I)),
    ("rate limit", re.compile(r"\brate_?limit\w*|@limiter\.limit|\bthrottle\w*", re.IGNORECASE)),
]
_COMMENT_PREFIXES = ("#", "//", "/*", "*")


def _check_kind(text: str) -> str | None:
    for kind, pattern in _CHECK_PATTERNS:
        # Removing an exemption (csrf_exempt) adds protection back.
        if pattern.search(text) and not (kind == "CSRF protection" and "exempt" in text.lower()):
            return kind
    return None


def _hunk_lines(entry: dict, kind: str):
    for hunk in entry.get("hunks") or []:
        for line in hunk.get("lines") or []:
            if line["kind"] == kind:
                yield line


def removed_checks(changed_files: list[dict]) -> list[dict]:
    """Removed lines that guarded something, with the line number they had before the change.

    A line added back anywhere in the same change counts as moved, not removed; comments are skipped.
    """
    added_anywhere = {line["text"].strip() for entry in changed_files for line in _hunk_lines(entry, "+")}
    found = []
    for entry in changed_files:
        path = entry.get("old_path") or entry.get("path") or ""
        if _never_flagged(path):
            continue
        for line in _hunk_lines(entry, "-"):
            text = line["text"].strip()
            if not text or text.startswith(_COMMENT_PREFIXES) or text in added_anywhere:
                continue
            kind = _check_kind(text)
            if kind:
                found.append({"path": path, "line": line["old"], "kind": kind, "text": text})
    return found


def run_git(args: list[str], cwd: str, timeout: int = 60) -> str:
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
            run_git(["fetch", "--depth", "2", "origin", head_sha], cwd=repo_path, timeout=timeout)
        except Exception:
            pass  # already deep enough, or offline; try the diff anyway

        try:
            base_sha = run_git(["rev-parse", f"{head_sha}~1"], cwd=repo_path, timeout=timeout).strip()
        except Exception:
            return None  # no parent (initial commit) -> nothing to diff

        diff_text = run_git(
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
    _cap_hunk_lines(changed_files)
    label_security_lines(changed_files)

    return {
        "base_sha": base_sha,
        "head_sha": head_sha,
        "changed_files": changed_files,
        "security_flags": detect_security_touches(changed_files),
    }
