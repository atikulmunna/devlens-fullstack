"""Chunk embeddings via OpenRouter's OpenAI-compatible /embeddings endpoint (index side).

Mirrors backend/app/services/embeddings.py but uses the worker settings object. Both sides
must use the same model and dimension so chunk and query vectors share one space.
"""

import time
from typing import Iterable

import httpx

from config import settings
from openrouter import describe_error

# The embedding model rejects inputs over 8192 tokens instead of truncating them, which would
# fail the whole batch (e.g. on a minified file). Code can run near 2 characters per token.
MAX_INPUT_CHARS = 16_000


class EmbeddingError(RuntimeError):
    pass


def _post_embeddings(texts: list[str]) -> list[list[float]]:
    if not settings.openrouter_api_key:
        raise EmbeddingError("OPENROUTER_API_KEY is not set")

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

    last_error: Exception | None = None
    for attempt in range(1, settings.embed_retry_attempts + 1):
        try:
            with httpx.Client(timeout=float(settings.embed_timeout_seconds)) as client:
                response = client.post(url, headers=headers, json=body)
            if response.status_code == 200:
                data = response.json().get("data") or []
                if len(data) != len(texts):
                    raise EmbeddingError("OpenRouter embeddings returned an unexpected number of vectors")
                ordered = sorted(data, key=lambda item: item.get("index", 0))
                return [[float(x) for x in (item.get("embedding") or [])] for item in ordered]
            if response.status_code < 500 and response.status_code != 429:
                # Non-retryable (e.g. bad key, unknown model): fail now with the provider's reason.
                raise EmbeddingError(f"OpenRouter embeddings returned {describe_error(response)}")
            last_error = EmbeddingError(f"OpenRouter embeddings transient {describe_error(response)}")
        except httpx.HTTPError as exc:
            last_error = exc
        if attempt < settings.embed_retry_attempts:
            time.sleep(0.5 * attempt)

    raise EmbeddingError(f"OpenRouter embeddings failed after retries: {last_error}")


def embed_texts(texts: Iterable[str], size: int | None = None) -> list[list[float]]:
    # size is accepted for backward compatibility; the model fixes the dimension.
    items = list(texts)
    if not items:
        return []
    return _post_embeddings(items)


def embed_text(text: str, size: int | None = None) -> list[float]:
    return embed_texts([text], size=size)[0]
