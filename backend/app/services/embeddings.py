"""Model-backed embeddings via NVIDIA NIM (OpenAI-compatible /embeddings endpoint).

NIM retrieval embedders are asymmetric: pass input_type="query" for search queries
and input_type="passage" for indexed documents. Both sides of the pipeline (this
backend query path and the worker index path) must use the same model + dimension so
vectors share one space.
"""

import httpx

from app.config import settings


class EmbeddingError(RuntimeError):
    pass


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    if not settings.nim_api_key:
        raise EmbeddingError("Missing NIM API key (nim_api_key)")
    if not texts:
        return []

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

    try:
        with httpx.Client(timeout=float(settings.embed_timeout_seconds)) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise EmbeddingError(f"NIM embeddings timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise EmbeddingError(f"NIM embeddings transport error: {exc}") from exc

    if response.status_code != 200:
        raise EmbeddingError(f"NIM embeddings returned status {response.status_code}")

    data = response.json().get("data") or []
    if len(data) != len(texts):
        raise EmbeddingError("NIM embeddings returned an unexpected number of vectors")

    ordered = sorted(data, key=lambda item: item.get("index", 0))
    return [[float(x) for x in (item.get("embedding") or [])] for item in ordered]


def embed_query(text: str) -> list[float]:
    return _embed([text], input_type="query")[0]


def embed_passages(texts: list[str]) -> list[list[float]]:
    return _embed(texts, input_type="passage")
