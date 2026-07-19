"""Model-backed embeddings via NVIDIA NIM (index/passage side).

Mirrors backend/app/services/embeddings.py but uses the worker settings object.
Indexed documents are embedded with input_type="passage"; the backend query path
uses input_type="query". Same model + dimension keeps both in one vector space.
"""

import time
from typing import Iterable

import httpx

from config import settings


class EmbeddingError(RuntimeError):
    pass


def _post_embeddings(texts: list[str], input_type: str) -> list[list[float]]:
    if not settings.nim_api_key:
        raise EmbeddingError("Missing NIM API key (nim_api_key)")

    url = f"{str(settings.nim_base_url).rstrip('/')}/embeddings"
    body = {
        "input": texts,
        "model": settings.embed_model,
        "input_type": input_type,
        "encoding_format": "float",
        "truncate": "END",
    }
    headers = {
        "Authorization": f"Bearer {settings.nim_api_key}",
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
                    raise EmbeddingError("NIM embeddings returned an unexpected number of vectors")
                ordered = sorted(data, key=lambda item: item.get("index", 0))
                return [[float(x) for x in (item.get("embedding") or [])] for item in ordered]
            if response.status_code < 500 and response.status_code != 429:
                raise EmbeddingError(f"NIM embeddings returned status {response.status_code}")
            last_error = EmbeddingError(f"NIM embeddings transient status {response.status_code}")
        except EmbeddingError as exc:
            # Non-retryable EmbeddingError (e.g. bad count / 4xx) bubbles up immediately.
            if "transient" not in str(exc):
                raise
            last_error = exc
        except httpx.HTTPError as exc:
            last_error = exc
        if attempt < settings.embed_retry_attempts:
            time.sleep(0.5 * attempt)

    raise EmbeddingError(f"NIM embeddings failed after retries: {last_error}")


def embed_texts(texts: Iterable[str], size: int | None = None) -> list[list[float]]:
    # size is accepted for backward compatibility; NIM fixes the dimension by model.
    items = list(texts)
    if not items:
        return []
    return _post_embeddings(items, input_type="passage")


def embed_text(text: str, size: int | None = None) -> list[float]:
    return embed_texts([text], size=size)[0]
