import json

import httpx
import pytest

from app.services import chat_synthesizer
from app.services.chat_synthesizer import ChatSynthesisError, synthesize_grounded_answer_stream

CONTEXTS = [{"chunk_id": "c1", "file_path": "src/auth.py", "line_start": 1, "line_end": 9, "content": "def login(): ..."}]


def _sse(*pieces: str) -> list[str]:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}" for piece in pieces]
    return [": keep-alive", "", *lines, "data: [DONE]"]


class _FakeStreamResponse:
    def __init__(self, status_code: int, lines: list[str]):
        self.status_code = status_code
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return b""

    def iter_lines(self):
        for line in self._lines:
            if isinstance(line, Exception):
                raise line
            yield line


def _fake_openrouter(monkeypatch, status_code: int = 200, lines: list | None = None, error: Exception | None = None) -> dict:
    """Replace httpx.Client and record the single streaming request the synthesizer makes."""
    captured: dict = {}

    class _FakeClient:
        def __init__(self, timeout=None):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def stream(self, method, url, headers=None, json=None):
            captured.update(method=method, url=url, headers=headers, body=json)
            if error is not None:
                raise error
            return _FakeStreamResponse(status_code, lines or [])

    monkeypatch.setattr(chat_synthesizer.httpx, "Client", _FakeClient)
    return captured


@pytest.fixture(autouse=True)
def _openrouter_settings(monkeypatch):
    monkeypatch.setattr(chat_synthesizer.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(chat_synthesizer.settings, "openrouter_base_url", "https://openrouter.test/api/v1")
    monkeypatch.setattr(chat_synthesizer.settings, "llm_chat_model", "test/model")
    monkeypatch.setattr(chat_synthesizer.settings, "llm_chat_timeout_seconds", 7)


def test_streams_tokens_from_openrouter(monkeypatch) -> None:
    captured = _fake_openrouter(monkeypatch, lines=_sse("Login ", "lives in ", "src/auth.py."))

    pieces = list(synthesize_grounded_answer_stream(query="where is login?", contexts=CONTEXTS))

    assert pieces == ["Login ", "lives in ", "src/auth.py."]
    assert captured["url"] == "https://openrouter.test/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "test/model"
    assert captured["body"]["stream"] is True
    assert captured["timeout"] == 7.0
    assert "def login(): ..." in captured["body"]["messages"][1]["content"]


def test_missing_api_key_raises_without_calling_openrouter(monkeypatch) -> None:
    captured = _fake_openrouter(monkeypatch, lines=_sse("unused"))
    monkeypatch.setattr(chat_synthesizer.settings, "openrouter_api_key", None)

    with pytest.raises(ChatSynthesisError, match="OPENROUTER_API_KEY"):
        list(synthesize_grounded_answer_stream(query="q", contexts=CONTEXTS))
    assert "url" not in captured


@pytest.mark.parametrize(
    ("status_code", "lines", "error", "message"),
    [
        (401, [], None, "status 401"),
        (200, [], httpx.ReadTimeout("slow"), "timeout"),
        (200, [], httpx.ConnectError("down"), "transport error"),
        (200, ["data: [DONE]"], None, "empty stream"),
    ],
)
def test_failures_before_any_token_raise_chat_synthesis_error(monkeypatch, status_code, lines, error, message) -> None:
    _fake_openrouter(monkeypatch, status_code=status_code, lines=lines, error=error)

    with pytest.raises(ChatSynthesisError, match=message):
        list(synthesize_grounded_answer_stream(query="q", contexts=CONTEXTS))


def test_mid_stream_failure_keeps_delivered_tokens(monkeypatch) -> None:
    _fake_openrouter(monkeypatch, lines=[*_sse("partial ")[:-1], httpx.ReadError("dropped")])
    stream = synthesize_grounded_answer_stream(query="q", contexts=CONTEXTS)

    assert next(stream) == "partial "
    with pytest.raises(ChatSynthesisError, match="transport error"):
        next(stream)


def test_malformed_chunk_surfaces_as_chat_synthesis_error(monkeypatch) -> None:
    # An empty "choices" list would raise IndexError; callers only handle ChatSynthesisError.
    _fake_openrouter(monkeypatch, lines=[*_sse("ok ")[:-1], 'data: {"choices": []}'])
    stream = synthesize_grounded_answer_stream(query="q", contexts=CONTEXTS)

    assert next(stream) == "ok "
    with pytest.raises(ChatSynthesisError, match="stream failed"):
        next(stream)


def test_no_contexts_raises() -> None:
    with pytest.raises(ChatSynthesisError, match="No contexts"):
        list(synthesize_grounded_answer_stream(query="q", contexts=[]))
