"""Content-addressed embedding cache backed by Redis.

Embeddings are keyed by (model, sha256(content)), so identical chunk content is embedded
once and reused across re-analyses of the same repo (unchanged content is near-free) and
even across repos. Keying on content hash rather than (repo, commit) maximizes reuse while
still guaranteeing correctness: the same text always maps to the same vector for a model.

Redis is best-effort: any cache error falls back to embedding directly, so the pipeline
never fails because of the cache.
"""

import hashlib
import json
from typing import Callable

try:
    import redis
except Exception:  # pragma: no cover - redis is a runtime dep; keep cache import-safe without it
    redis = None

from config import settings

_client = None
_client_ready = False


def _get_client():
    global _client, _client_ready
    if not _client_ready:
        _client_ready = True
        if redis is None:
            _client = None
        else:
            try:
                _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                _client = None
    return _client


def _key(model: str, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"embedcache:{model}:{digest}"


def embed_with_cache(
    texts: list[str],
    embed_fn: Callable[[list[str]], list[list[float]]],
    model: str,
    ttl_seconds: int,
) -> list[list[float]]:
    """Return vectors for texts, serving cache hits from Redis and embedding only misses."""
    if not texts:
        return []

    client = _get_client()
    if client is None:
        return embed_fn(texts)

    keys = [_key(model, t) for t in texts]
    try:
        cached = client.mget(keys)
    except Exception:
        return embed_fn(texts)

    result: list[list[float] | None] = [None] * len(texts)
    missing: list[int] = []
    for i, raw in enumerate(cached):
        if raw:
            try:
                result[i] = json.loads(raw)
                continue
            except (ValueError, TypeError):
                pass
        missing.append(i)

    if missing:
        new_vectors = embed_fn([texts[i] for i in missing])
        try:
            pipe = client.pipeline()
            for slot, idx in enumerate(missing):
                result[idx] = new_vectors[slot]
                pipe.set(keys[idx], json.dumps(new_vectors[slot]), ex=ttl_seconds)
            pipe.execute()
        except Exception:
            # Store failed; still return freshly computed vectors.
            for slot, idx in enumerate(missing):
                result[idx] = new_vectors[slot]

    return [vec if vec is not None else [] for vec in result]
