import httpx
import pytest

from app.services import embeddings
from app.services.embeddings import EmbeddingError, embed_query


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self) -> dict:
        return self._payload


def _fake_openrouter(monkeypatch, status_code: int = 200, payload: dict | None = None, error: Exception | None = None) -> dict:
    """Replace httpx.Client and record the embeddings request."""
    captured: dict = {}

    class _FakeClient:
        def __init__(self, timeout=None):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, headers=None, json=None):
            captured.update(url=url, headers=headers, body=json)
            if error is not None:
                raise error
            return _FakeResponse(status_code, payload or {})

    monkeypatch.setattr(embeddings.httpx, "Client", _FakeClient)
    return captured


@pytest.fixture(autouse=True)
def _openrouter_settings(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(embeddings.settings, "openrouter_base_url", "https://openrouter.test/api/v1")
    monkeypatch.setattr(embeddings.settings, "embed_model", "openai/text-embedding-3-small")
    monkeypatch.setattr(embeddings.settings, "embed_timeout_seconds", 9)


def test_embed_query_calls_openrouter_embeddings(monkeypatch) -> None:
    captured = _fake_openrouter(monkeypatch, payload={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    vector = embed_query("where is login handled?")

    assert vector == [0.1, 0.2]
    assert captured["url"] == "https://openrouter.test/api/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["body"]["model"] == "openai/text-embedding-3-small"
    assert captured["body"]["input"] == ["where is login handled?"]
    assert captured["timeout"] == 9.0


def test_embed_query_caps_oversized_input(monkeypatch) -> None:
    captured = _fake_openrouter(monkeypatch, payload={"data": [{"index": 0, "embedding": [0.1]}]})

    embed_query("q" * (embeddings.MAX_INPUT_CHARS + 1))

    assert len(captured["body"]["input"][0]) == embeddings.MAX_INPUT_CHARS


def test_missing_api_key_raises_without_request(monkeypatch) -> None:
    captured = _fake_openrouter(monkeypatch)
    monkeypatch.setattr(embeddings.settings, "openrouter_api_key", None)

    with pytest.raises(EmbeddingError, match="OPENROUTER_API_KEY"):
        embed_query("q")
    assert "url" not in captured


@pytest.mark.parametrize(
    ("status_code", "payload", "error", "message"),
    [
        (410, {}, None, "status 410"),
        (401, {"error": {"message": "User not found.", "code": 401}}, None, "status 401: User not found."),
        (200, {"data": []}, None, "unexpected number of vectors"),
        (200, {}, httpx.ReadTimeout("slow"), "timeout"),
        (200, {}, httpx.ConnectError("down"), "transport error"),
    ],
)
def test_failures_raise_embedding_error(monkeypatch, status_code, payload, error, message) -> None:
    _fake_openrouter(monkeypatch, status_code=status_code, payload=payload, error=error)

    with pytest.raises(EmbeddingError, match=message):
        embed_query("q")
