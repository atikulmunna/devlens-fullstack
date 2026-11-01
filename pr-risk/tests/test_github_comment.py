import io
import json
import urllib.error

import pytest

from github_comment import CommentError, upsert_comment

MARKER = "<!-- devlens-pr-risk -->"


class FakeGitHub:
    """Answers the comment API from a list of existing comments and records every call."""

    def __init__(self, comments: list[dict], fail_with: int | None = None):
        self.comments = comments
        self.fail_with = fail_with
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, request, timeout):
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), request.full_url, body))
        assert request.headers["Authorization"] == "Bearer t0ken"
        if self.fail_with and request.get_method() != "GET":
            raise urllib.error.HTTPError(request.full_url, self.fail_with, "no", {}, io.BytesIO(b'{"message":"no"}'))
        payload = self.comments if request.get_method() == "GET" else {"id": 1}
        return io.BytesIO(json.dumps(payload).encode())


def _upsert(fake: FakeGitHub) -> str:
    return upsert_comment(
        api_url="https://api.github.test",
        token="t0ken",
        repo="acme/shop",
        pr_number=7,
        body="new",
        marker=MARKER,
        opener=fake,
    )


def test_updates_its_own_earlier_comment() -> None:
    fake = FakeGitHub(
        [
            {"id": 41, "body": "hi", "user": {"type": "User"}},
            {"id": 42, "body": f"{MARKER}\nold", "user": {"type": "Bot"}},
        ]
    )
    assert _upsert(fake) == "updated"
    assert fake.calls[-1] == ("PATCH", "https://api.github.test/repos/acme/shop/issues/comments/42", {"body": "new"})


def test_creates_a_comment_when_only_a_person_quoted_the_marker() -> None:
    fake = FakeGitHub([{"id": 41, "body": f"> {MARKER}", "user": {"type": "User"}}])
    assert _upsert(fake) == "created"
    assert fake.calls[-1] == ("POST", "https://api.github.test/repos/acme/shop/issues/7/comments", {"body": "new"})


def test_a_refused_write_carries_the_status() -> None:
    with pytest.raises(CommentError) as refused:
        _upsert(FakeGitHub([], fail_with=403))
    assert refused.value.status == 403
