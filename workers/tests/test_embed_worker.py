import pytest

import embed_worker
import embeddings
from embed_worker import ChunkRecord, EmbedError, EmbedSnapshot
from embeddings import embed_text, embed_texts

_REAL_ENSURE_COLLECTION = embed_worker.ensure_collection


class FakeSession:
    def __init__(self) -> None:
        self.events = []
        self.retry_count = 0

    def execute(self, *_args, **_kwargs):
        self.events.append(('execute', _args, _kwargs))
        return self

    def commit(self):
        self.events.append(('commit',))

    def mappings(self):
        return self

    def first(self):
        return {'retry_count': self.retry_count}


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response, capture):
        self._response = response
        self._capture = capture

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, headers=None, json=None):
        self._capture['url'] = url
        self._capture['headers'] = headers
        self._capture['json'] = json
        self._capture['posts'] = self._capture.get('posts', 0) + 1
        return self._response


def _fake_openrouter(monkeypatch, status_code, payload) -> dict:
    monkeypatch.setattr(embeddings.settings, 'openrouter_api_key', 'test-key')
    monkeypatch.setattr(embeddings.settings, 'openrouter_base_url', 'https://openrouter.test/api/v1')
    monkeypatch.setattr(embeddings.settings, 'embed_model', 'openai/text-embedding-3-small')
    capture = {}
    monkeypatch.setattr(
        embeddings.httpx,
        'Client',
        lambda *a, **k: _FakeClient(_FakeResponse(status_code, payload), capture),
    )
    return capture


def test_embed_texts_calls_openrouter_embeddings(monkeypatch) -> None:
    payload = {
        'data': [
            {'index': 1, 'embedding': [0.4, 0.5, 0.6]},
            {'index': 0, 'embedding': [0.1, 0.2, 0.3]},
        ]
    }
    capture = _fake_openrouter(monkeypatch, 200, payload)

    vectors = embed_texts(['first passage', 'second passage'])

    # Vectors are re-ordered by the "index" field, not response order.
    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert capture['url'] == 'https://openrouter.test/api/v1/embeddings'
    assert capture['json']['model'] == 'openai/text-embedding-3-small'
    assert capture['json']['input'] == ['first passage', 'second passage']
    assert 'input_type' not in capture['json']
    assert capture['headers']['Authorization'] == 'Bearer test-key'


def test_embed_texts_caps_oversized_inputs(monkeypatch) -> None:
    capture = _fake_openrouter(monkeypatch, 200, {'data': [{'index': 0, 'embedding': [0.1]}]})

    embed_texts(['x' * (embeddings.MAX_INPUT_CHARS + 500)])

    # Over the model's token limit the whole batch is rejected (e.g. one minified file).
    assert len(capture['json']['input'][0]) == embeddings.MAX_INPUT_CHARS


def test_embed_texts_client_error_fails_without_retry(monkeypatch) -> None:
    capture = _fake_openrouter(
        monkeypatch, 410, {'error': {'message': 'The model has reached its end of life', 'code': 410}}
    )

    # The provider's reason travels with the error into the job's failure message.
    with pytest.raises(embeddings.EmbeddingError, match='status 410: The model has reached its end of life'):
        embed_texts(['hello'])
    assert capture['posts'] == 1


def test_embed_text_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.setattr(embeddings.settings, 'openrouter_api_key', None)
    with pytest.raises(embeddings.EmbeddingError):
        embed_text('hello world')


def test_upsert_vectors_requires_matching_lengths() -> None:
    chunk = ChunkRecord(id='1', file_path='a.py', start_line=1, end_line=2, content='x', language='py')
    with pytest.raises(EmbedError) as raised:
        embed_worker.upsert_chunk_vectors('repo', [chunk], [])
    assert raised.value.code == 'EMBED_VECTOR_MISMATCH'


def test_embed_job_success_transitions_to_analyzing(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000021', job_id='00000000-0000-0000-0000-000000000022'
    )

    chunks = [
        ChunkRecord(
            id='00000000-0000-0000-0000-000000000101',
            file_path='a.py',
            start_line=1,
            end_line=10,
            content='print(1)',
            language='py',
        ),
        ChunkRecord(
            id='00000000-0000-0000-0000-000000000102',
            file_path='b.py',
            start_line=1,
            end_line=10,
            content='print(2)',
            language='py',
        ),
    ]

    monkeypatch.setattr(embed_worker, 'load_repo_chunks', lambda *_args, **_kwargs: chunks)
    monkeypatch.setattr(embed_worker, 'ensure_collection', lambda _vector_size: None)
    monkeypatch.setattr(embed_worker, 'delete_repo_vectors', lambda _repo_id: None)
    monkeypatch.setattr(embed_worker, 'embed_texts', lambda contents, size=None: [[0.0] * 4 for _ in contents])
    monkeypatch.setattr(
        embed_worker, 'upsert_chunk_vectors', lambda _repo_id, batch, _vectors: [f'id-{c.id}' for c in batch]
    )

    monkeypatch.setattr(embed_worker.settings, 'embed_batch_size', 1)

    stored_batches = []

    def fake_store(_db, chunk_ids, qdrant_ids):
        stored_batches.append((chunk_ids, qdrant_ids))

    monkeypatch.setattr(embed_worker, 'store_qdrant_point_ids', fake_store)
    observed = {'count': 0}
    monkeypatch.setattr(
        embed_worker,
        'record_stage_duration',
        lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1),
    )

    embed_worker.embed_job(fake_db, snapshot)

    # One store per batch, so the status stream can count indexed chunks mid-run.
    assert stored_batches == [
        (['00000000-0000-0000-0000-000000000101'], ['id-00000000-0000-0000-0000-000000000101']),
        (['00000000-0000-0000-0000-000000000102'], ['id-00000000-0000-0000-0000-000000000102']),
    ]
    assert observed['count'] == 1
    updates = [e for e in fake_db.events if e[0] == 'execute' and 'UPDATE analysis_jobs' in str(e[1][0])]
    assert any('analyzing' in str(ev) for ev in updates)


def _stub_embed_pipeline(monkeypatch, chunks) -> list[tuple]:
    """Stub everything but the Qdrant HTTP layer, and record each Qdrant request."""
    qdrant_calls = []

    def fake_request(method, url, *, json_body=None, allowed_statuses=None, headers=None):
        qdrant_calls.append((method, url, json_body))
        return None

    monkeypatch.setattr(embed_worker, '_request_with_retries', fake_request)
    # Bypass the Redis embedding cache: vectors cached by one test would leak into the next.
    monkeypatch.setattr(embed_worker, 'embed_with_cache', lambda texts, embed_fn, **_kwargs: embed_fn(texts))
    monkeypatch.setattr(embed_worker, 'load_repo_chunks', lambda *_args, **_kwargs: chunks)
    monkeypatch.setattr(embed_worker, 'ensure_collection', lambda _vector_size: None)
    monkeypatch.setattr(embed_worker, 'embed_texts', lambda contents, size=None: [[0.0] * 4 for _ in contents])
    monkeypatch.setattr(embed_worker, 'store_qdrant_point_ids', lambda *_args: None)
    monkeypatch.setattr(embed_worker, 'record_stage_duration', lambda *_args, **_kwargs: None)
    return qdrant_calls


def test_embed_job_deletes_old_repo_vectors_before_upserting(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000041', job_id='00000000-0000-0000-0000-000000000042'
    )
    chunks = [
        ChunkRecord(
            id='00000000-0000-0000-0000-000000000141',
            file_path='a.py',
            start_line=1,
            end_line=2,
            content='print(1)',
            language='py',
        )
    ]
    qdrant_calls = _stub_embed_pipeline(monkeypatch, chunks)

    embed_worker.embed_job(fake_db, snapshot)

    # A re-analysis replaces every chunk, so the repo's previous points must go before new ones land.
    assert [(method, url.rsplit('/', 1)[-1]) for method, url, _ in qdrant_calls] == [
        ('POST', 'delete?wait=true'),
        ('PUT', 'points?wait=true'),
    ]
    assert qdrant_calls[0][2] == {'filter': {'must': [{'key': 'repo_id', 'match': {'value': snapshot.repo_id}}]}}


def test_embed_job_stops_before_upsert_when_vector_delete_fails(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000051', job_id='00000000-0000-0000-0000-000000000052'
    )
    chunks = [
        ChunkRecord(
            id='00000000-0000-0000-0000-000000000151',
            file_path='a.py',
            start_line=1,
            end_line=2,
            content='print(1)',
            language='py',
        )
    ]
    qdrant_calls = _stub_embed_pipeline(monkeypatch, chunks)

    def failing_delete(method, url, *, json_body=None, allowed_statuses=None, headers=None):
        qdrant_calls.append((method, url, json_body))
        if url.endswith('/points/delete?wait=true'):
            raise EmbedError('EMBED_UPSERT_FAILED', 'qdrant unavailable')
        return None

    monkeypatch.setattr(embed_worker, '_request_with_retries', failing_delete)
    scheduled = {}
    monkeypatch.setattr(
        embed_worker, 'schedule_retry_or_dead_letter', lambda *_args, **kwargs: scheduled.update(kwargs)
    )

    embed_worker.embed_job(fake_db, snapshot)

    assert [method for method, _, _ in qdrant_calls] == ['POST']
    assert scheduled['stage'] == 'embedding'
    assert scheduled['error_code'] == 'EMBED_UPSERT_FAILED'


def test_embed_job_fails_with_no_chunks(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000031', job_id='00000000-0000-0000-0000-000000000032'
    )

    monkeypatch.setattr(embed_worker, 'load_repo_chunks', lambda *_args, **_kwargs: [])

    embed_worker.embed_job(fake_db, snapshot)

    fail_updates = [e for e in fake_db.events if e[0] == 'execute' and 'UPDATE analysis_jobs' in str(e[1][0])]
    assert any('NO_CHUNKS' in str(ev) for ev in fail_updates)


def test_process_next_embed_job_returns_false_if_none(monkeypatch) -> None:
    fake_db = FakeSession()
    monkeypatch.setattr(embed_worker, 'fetch_next_embed_job', lambda *_args, **_kwargs: None)

    assert embed_worker.process_next_embed_job(fake_db) is False


def test_ensure_collection_allows_existing_collection(monkeypatch) -> None:
    captured = {}

    def fake_request(method, url, *, json_body=None, allowed_statuses=None, headers=None):
        captured['method'] = method
        captured['url'] = url
        captured['json_body'] = json_body
        captured['allowed_statuses'] = allowed_statuses
        captured['headers'] = headers
        return None

    monkeypatch.setattr(embed_worker, '_request_with_retries', fake_request)
    embed_worker.ensure_collection(1536)

    assert captured['method'] == 'PUT'
    assert captured['allowed_statuses'] == {409}
    assert captured['json_body'] == {'vectors': {'size': 1536, 'distance': 'Cosine'}}


def test_ensure_collection_keeps_matching_size_and_recreates_on_change(monkeypatch) -> None:
    calls = []
    existing = {'result': {'config': {'params': {'vectors': {'size': 1024, 'distance': 'Cosine'}}}}}

    def fake_request(method, url, *, json_body=None, allowed_statuses=None, headers=None):
        calls.append((method, json_body))
        return existing if method == 'GET' else None

    monkeypatch.setattr(embed_worker, '_request_with_retries', fake_request)

    embed_worker.ensure_collection(1024)
    assert [method for method, _ in calls] == ['GET']

    calls.clear()
    embed_worker.ensure_collection(1536)
    assert [method for method, _ in calls] == ['GET', 'DELETE', 'PUT']
    assert calls[2][1] == {'vectors': {'size': 1536, 'distance': 'Cosine'}}


def test_embed_job_sizes_the_collection_from_the_model_output(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000061', job_id='00000000-0000-0000-0000-000000000062'
    )
    chunks = [
        ChunkRecord(
            id='00000000-0000-0000-0000-000000000161',
            file_path='a.py',
            start_line=1,
            end_line=2,
            content='print(1)',
            language='py',
        )
    ]
    qdrant_calls = _stub_embed_pipeline(monkeypatch, chunks)
    monkeypatch.setattr(embed_worker, 'ensure_collection', _REAL_ENSURE_COLLECTION)

    embed_worker.embed_job(fake_db, snapshot)

    # The stubbed model returns 4-dim vectors; config must not decide the size (it drifted twice).
    methods = [(method, url.rsplit('/', 1)[-1]) for method, url, _ in qdrant_calls]
    assert methods == [
        ('GET', embed_worker.settings.qdrant_collection),
        ('PUT', embed_worker.settings.qdrant_collection),
        ('POST', 'delete?wait=true'),
        ('PUT', 'points?wait=true'),
    ]
    assert qdrant_calls[1][2] == {'vectors': {'size': 4, 'distance': 'Cosine'}}


def test_embed_job_rejects_empty_vectors_before_touching_qdrant(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000071', job_id='00000000-0000-0000-0000-000000000072'
    )
    chunks = [
        ChunkRecord(
            id='00000000-0000-0000-0000-000000000171',
            file_path='a.py',
            start_line=1,
            end_line=2,
            content='print(1)',
            language='py',
        )
    ]
    qdrant_calls = _stub_embed_pipeline(monkeypatch, chunks)
    monkeypatch.setattr(embed_worker, 'embed_texts', lambda contents, size=None: [[] for _ in contents])
    scheduled = {}
    monkeypatch.setattr(
        embed_worker, 'schedule_retry_or_dead_letter', lambda *_args, **kwargs: scheduled.update(kwargs)
    )

    embed_worker.embed_job(fake_db, snapshot)

    assert scheduled['error_code'] == 'EMBED_EMPTY_VECTOR'
    assert qdrant_calls == []


def test_embed_job_retriable_failure_schedules_retry(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(
        repo_id='00000000-0000-0000-0000-000000000071', job_id='00000000-0000-0000-0000-000000000072'
    )
    chunks = [ChunkRecord(id='1', file_path='a.py', start_line=1, end_line=2, content='print(1)', language='py')]

    monkeypatch.setattr(embed_worker, 'load_repo_chunks', lambda *_args, **_kwargs: chunks)
    monkeypatch.setattr(embed_worker, 'ensure_collection', lambda _vector_size: None)
    monkeypatch.setattr(embed_worker, 'delete_repo_vectors', lambda _repo_id: None)
    monkeypatch.setattr(embed_worker, 'embed_texts', lambda contents, size=None: [[0.0] * 4 for _ in contents])
    monkeypatch.setattr(
        embed_worker,
        'upsert_chunk_vectors',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(EmbedError('EMBED_UPSERT_FAILED', 'temporary qdrant error')),
    )
    called = {'stage': None, 'code': None}

    def fake_schedule(*_args, **kwargs):
        called['stage'] = kwargs['stage']
        called['code'] = kwargs['error_code']

    monkeypatch.setattr(embed_worker, 'schedule_retry_or_dead_letter', fake_schedule)
    observed = {'count': 0}
    monkeypatch.setattr(
        embed_worker,
        'record_stage_duration',
        lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1),
    )
    embed_worker.embed_job(fake_db, snapshot)

    assert called['stage'] == 'embedding'
    assert called['code'] == 'EMBED_UPSERT_FAILED'
    assert observed['count'] == 1
