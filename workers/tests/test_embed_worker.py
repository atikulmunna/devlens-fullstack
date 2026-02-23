import embed_worker
from embed_worker import ChunkRecord, EmbedSnapshot, EmbedError
from embeddings import embed_text


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



def test_embed_text_returns_fixed_size_and_is_deterministic(monkeypatch) -> None:
    monkeypatch.setattr(embed_worker.settings, 'embed_vector_size', 16)
    v1 = embed_text('hello world', size=16)
    v2 = embed_text('hello world', size=16)

    assert len(v1) == 16
    assert v1 == v2


def test_upsert_vectors_requires_matching_lengths() -> None:
    chunk = ChunkRecord(id='1', file_path='a.py', start_line=1, end_line=2, content='x', language='py')
    try:
        embed_worker.upsert_chunk_vectors('repo', [chunk], [])
        assert False, 'expected mismatch error'
    except EmbedError as exc:
        assert exc.code == 'EMBED_VECTOR_MISMATCH'


def test_embed_job_success_transitions_to_analyzing(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(repo_id='00000000-0000-0000-0000-000000000021', job_id='00000000-0000-0000-0000-000000000022')

    chunks = [
        ChunkRecord(id='00000000-0000-0000-0000-000000000101', file_path='a.py', start_line=1, end_line=10, content='print(1)', language='py'),
        ChunkRecord(id='00000000-0000-0000-0000-000000000102', file_path='b.py', start_line=1, end_line=10, content='print(2)', language='py'),
    ]

    monkeypatch.setattr(embed_worker, 'load_repo_chunks', lambda *_args, **_kwargs: chunks)
    monkeypatch.setattr(embed_worker, 'ensure_collection', lambda: None)
    monkeypatch.setattr(embed_worker, 'upsert_chunk_vectors', lambda _repo_id, batch, _vectors: [f'id-{c.id}' for c in batch])

    stored = {'count': 0}

    def fake_store(_db, _chunk_ids, _qdrant_ids):
        stored['count'] = len(_chunk_ids)

    monkeypatch.setattr(embed_worker, 'store_qdrant_point_ids', fake_store)
    observed = {'count': 0}
    monkeypatch.setattr(embed_worker, 'record_stage_duration', lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1))

    embed_worker.embed_job(fake_db, snapshot)

    assert stored['count'] == 2
    assert observed['count'] == 1
    updates = [e for e in fake_db.events if e[0] == 'execute' and 'UPDATE analysis_jobs' in str(e[1][0])]
    assert any('analyzing' in str(ev) for ev in updates)


def test_embed_job_fails_with_no_chunks(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(repo_id='00000000-0000-0000-0000-000000000031', job_id='00000000-0000-0000-0000-000000000032')

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

    def fake_request(method, url, *, json_body=None, allowed_statuses=None):
        captured['method'] = method
        captured['url'] = url
        captured['json_body'] = json_body
        captured['allowed_statuses'] = allowed_statuses
        return None

    monkeypatch.setattr(embed_worker, '_request_with_retries', fake_request)
    embed_worker.ensure_collection()

    assert captured['method'] == 'PUT'
    assert captured['allowed_statuses'] == {409}


def test_embed_job_retriable_failure_schedules_retry(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = EmbedSnapshot(repo_id='00000000-0000-0000-0000-000000000071', job_id='00000000-0000-0000-0000-000000000072')
    chunks = [ChunkRecord(id='1', file_path='a.py', start_line=1, end_line=2, content='print(1)', language='py')]

    monkeypatch.setattr(embed_worker, 'load_repo_chunks', lambda *_args, **_kwargs: chunks)
    monkeypatch.setattr(embed_worker, 'ensure_collection', lambda: None)
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
    monkeypatch.setattr(embed_worker, 'record_stage_duration', lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1))
    embed_worker.embed_job(fake_db, snapshot)

    assert called['stage'] == 'embedding'
    assert called['code'] == 'EMBED_UPSERT_FAILED'
    assert observed['count'] == 1
