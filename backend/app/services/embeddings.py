"""Query embeddings via OpenRouter's OpenAI-compatible /embeddings endpoint.

The worker embeds indexed chunks with the same model and dimension
(workers/embeddings.py), so query and chunk vectors share one space.
"""

import httpx

from app.config import settings

# The embedding model rejects inputs over 8192 tokens instead of truncating them. Code can
# run near 2 characters per token, so cap by characters well under the limit.
MAX_INPUT_CHARS = 16_000


class EmbeddingError(RuntimeError):
    pass


def _embed(texts: list[str]) -> list[list[float]]:
    if not settings.openrouter_api_key:
        raise EmbeddingError("OPENROUTER_API_KEY is not set")
    if not texts:
        return []

    url = f"{str(settings.openrouter_base_url).rstrip('/')}/embeddings"
    body = {
        "input": [text[:MAX_INPUT_CHARS] for text in texts],
        "model": settings.embed_model,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=float(settings.embed_timeout_seconds)) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise EmbeddingError(f"OpenRouter embeddings timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise EmbeddingError(f"OpenRouter embeddings transport error: {exc}") from exc

    if response.status_code != 200:
        raise EmbeddingError(f"OpenRouter embeddings returned status {response.status_code}")

    data = response.json().get("data") or []
    if len(data) != len(texts):
        raise EmbeddingError("OpenRouter embeddings returned an unexpected number of vectors")

    ordered = sorted(data, key=lambda item: item.get("index", 0))
    return [[float(x) for x in (item.get("embedding") or [])] for item in ordered]


def embed_query(text: str) -> list[float]:
    return _embed([text])[0]
