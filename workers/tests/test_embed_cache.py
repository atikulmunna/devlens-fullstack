import json

import embed_cache


class FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def set(self, key, value, ex=None):
        self._ops.append((key, value))

    def execute(self):
        for key, value in self._ops:
            self._store[key] = value
        self._ops = []


class FakeRedis:
    def __init__(self, store=None):
        self.store = store or {}
        self.mget_calls = 0

    def mget(self, keys):
        self.mget_calls += 1
        return [self.store.get(k) for k in keys]

    def pipeline(self):
        return FakePipeline(self.store)


def _use_fake(monkeypatch, fake):
    monkeypatch.setattr(embed_cache, "_client", fake)
    monkeypatch.setattr(embed_cache, "_client_ready", True)


def test_all_misses_calls_embed_and_stores(monkeypatch) -> None:
    fake = FakeRedis()
    _use_fake(monkeypatch, fake)
    calls = {"n": 0}

    def embed_fn(texts):
        calls["n"] += 1
        return [[float(len(t))] for t in texts]

    out = embed_cache.embed_with_cache(["ab", "cde"], embed_fn, model="m", ttl_seconds=10)
    assert out == [[2.0], [3.0]]
    assert calls["n"] == 1
    # Both vectors are now cached.
    assert len(fake.store) == 2


def test_partial_hit_only_embeds_missing(monkeypatch) -> None:
    fake = FakeRedis()
    # Pre-cache the vector for "ab".
    fake.store[embed_cache._key("m", "ab")] = json.dumps([2.0])
    _use_fake(monkeypatch, fake)

    embedded_texts = []

    def embed_fn(texts):
        embedded_texts.extend(texts)
        return [[99.0] for _ in texts]

    out = embed_cache.embed_with_cache(["ab", "cde"], embed_fn, model="m", ttl_seconds=10)
    assert out == [[2.0], [99.0]]
    # Only the missing text was embedded.
    assert embedded_texts == ["cde"]


def test_no_client_falls_back_to_embed(monkeypatch) -> None:
    monkeypatch.setattr(embed_cache, "_client", None)
    monkeypatch.setattr(embed_cache, "_client_ready", True)
    out = embed_cache.embed_with_cache(["x"], lambda texts: [[1.0]], model="m", ttl_seconds=10)
    assert out == [[1.0]]


def test_mget_error_falls_back(monkeypatch) -> None:
    class BrokenRedis:
        def mget(self, keys):
            raise RuntimeError("redis down")

    _use_fake(monkeypatch, BrokenRedis())
    out = embed_cache.embed_with_cache(["x", "y"], lambda texts: [[1.0], [2.0]], model="m", ttl_seconds=10)
    assert out == [[1.0], [2.0]]
