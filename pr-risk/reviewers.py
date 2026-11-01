"""Who knows the changed files, from git history: suggested reviewers. Pure: it reads `git log` text."""

import re

# One record per commit: a separator, "sha<US>name<US>email", then the files it touched, one per line.
LOG_FORMAT = "%x1e%H%x1f%aN%x1f%aE"
_NOREPLY_RE = re.compile(r"^(?:\d+\+)?([a-z0-9-]+)@users\.noreply\.github\.com$", re.IGNORECASE)


def parse_log(text: str) -> list[dict]:
    """Commits from `git log --format=LOG_FORMAT --name-only`, newest first."""
    commits = []
    for record in text.split("\x1e"):
        lines = [line for line in record.splitlines() if line.strip()]
        if not lines:
            continue
        sha, name, email = lines[0].split("\x1f")
        commits.append({"sha": sha, "name": name, "email": email.lower(), "files": lines[1:]})
    return commits


def noreply_login(email: str) -> str | None:
    """The account in a GitHub noreply address (`123+octo@users.noreply.github.com` is octo)."""
    match = _NOREPLY_RE.match(email)
    return match.group(1) if match else None


def _is_bot(commit: dict) -> bool:
    return "[bot]" in commit["name"].lower() or "[bot]" in commit["email"]


def suggest_reviewers(commits: list[dict], changed: set[str], exclude_emails: set[str], limit: int = 3) -> list[dict]:
    """People who changed the most of these files, then the most often; never the pull request's own authors."""
    people: dict[str, dict] = {}
    for commit in commits:
        touched = changed & set(commit["files"])
        if not touched or commit["email"] in exclude_emails or _is_bot(commit):
            continue
        # Commits come newest first, so the first one seen is the person's latest.
        person = people.setdefault(
            commit["email"],
            {
                "name": commit["name"],
                "email": commit["email"],
                "files": set(),
                "commits": 0,
                "latest_sha": commit["sha"],
            },
        )
        person["files"] |= touched
        person["commits"] += 1
    ranked = sorted(people.values(), key=lambda person: (-len(person["files"]), -person["commits"], person["name"]))
    return [{**person, "files": sorted(person["files"])} for person in ranked[:limit]]
