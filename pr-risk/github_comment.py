"""Create or update the one DevLens comment on a pull request (GitHub REST, standard library only)."""

import json
import urllib.error
import urllib.request

MAX_PAGES = 10


class CommentError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API {status}: {message}")
        self.status = status


def _request(api_url: str, token: str, method: str, path: str, body: dict | None = None, opener=None):
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with (opener or urllib.request.urlopen)(request, timeout=30) as response:
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise CommentError(exc.code, detail) from exc


def _find_existing(api_url: str, token: str, repo: str, pr_number: int, marker: str, opener) -> int | None:
    """Our earlier comment: written by a bot and carrying the marker (a person quoting it does not count)."""
    for page in range(1, MAX_PAGES + 1):
        comments = _request(
            api_url, token, "GET", f"/repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}", opener=opener
        )
        for comment in comments:
            if marker in (comment.get("body") or "") and (comment.get("user") or {}).get("type") == "Bot":
                return comment["id"]
        if len(comments) < 100:
            return None
    return None


def upsert_comment(*, api_url: str, token: str, repo: str, pr_number: int, body: str, marker: str, opener=None) -> str:
    """Returns "updated" or "created". Raises CommentError when GitHub refuses (e.g. a read-only fork token)."""
    existing = _find_existing(api_url, token, repo, pr_number, marker, opener)
    if existing is not None:
        _request(api_url, token, "PATCH", f"/repos/{repo}/issues/comments/{existing}", {"body": body}, opener)
        return "updated"
    _request(api_url, token, "POST", f"/repos/{repo}/issues/{pr_number}/comments", {"body": body}, opener)
    return "created"
