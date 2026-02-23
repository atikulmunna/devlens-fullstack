import analyze_worker
from analyze_worker import AnalyzeError, AnalyzeSnapshot, ChunkRecord


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



def test_language_breakdown_percentages_sum_close_to_100() -> None:
    chunks = [
        ChunkRecord(file_path='a.py', start_line=1, end_line=2, content='x' * 50, language='py'),
        ChunkRecord(file_path='b.ts', start_line=1, end_line=2, content='x' * 50, language='ts'),
    ]
    breakdown = analyze_worker.language_breakdown(chunks)
    total = sum(breakdown.values())
    assert 99.0 <= total <= 101.0


def test_compute_quality_score_is_bounded() -> None:
    tech_debt = {
        'todo_count': 500,
        'long_functions': [{'file': 'a.py', 'line': 1, 'length': 500}] * 100,
        'missing_tests': ['a.py'],
    }
    score = analyze_worker.compute_quality_score(tech_debt, {'files': {'a.py': {}, 'README.md': {}}})
    assert 0 <= score <= 100


def test_analyze_job_success_marks_done(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = AnalyzeSnapshot(
        repo_id='00000000-0000-0000-0000-000000000041',
        job_id='00000000-0000-0000-0000-000000000042',
        full_name='test-owner/repo',
        default_branch='main',
    )

    chunks = [
        ChunkRecord(file_path='src/a.py', start_line=1, end_line=60, content='TODO\n' + ('x\n' * 60), language='py'),
        ChunkRecord(file_path='README.md', start_line=1, end_line=10, content='docs', language='md'),
    ]

    monkeypatch.setattr(analyze_worker, 'load_repo_chunks', lambda *_args, **_kwargs: chunks)
    monkeypatch.setattr(analyze_worker, 'get_contributor_stats', lambda *_args, **_kwargs: {'top_contributors': []})

    called = {'stored': False, 'done': False}

    def fake_store(*_args, **_kwargs):
        called['stored'] = True

    def fake_done(*_args, **_kwargs):
        called['done'] = True

    monkeypatch.setattr(analyze_worker, 'store_analysis_result', fake_store)
    monkeypatch.setattr(analyze_worker, 'mark_job_done', fake_done)
    observed = {'count': 0}
    monkeypatch.setattr(analyze_worker, 'record_stage_duration', lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1))

    analyze_worker.analyze_job(fake_db, snapshot)

    assert called['stored'] is True
    assert called['done'] is True
    assert observed['count'] == 1


def test_analyze_job_fails_when_no_chunks(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = AnalyzeSnapshot(
        repo_id='00000000-0000-0000-0000-000000000051',
        job_id='00000000-0000-0000-0000-000000000052',
        full_name='test-owner/repo',
        default_branch='main',
    )

    monkeypatch.setattr(analyze_worker, 'load_repo_chunks', lambda *_args, **_kwargs: [])

    analyze_worker.analyze_job(fake_db, snapshot)

    updates = [e for e in fake_db.events if e[0] == 'execute' and 'UPDATE analysis_jobs' in str(e[1][0])]
    assert any('NO_CHUNKS' in str(ev) for ev in updates)


def test_process_next_analyze_job_returns_false_when_none(monkeypatch) -> None:
    fake_db = FakeSession()
    monkeypatch.setattr(analyze_worker, 'fetch_next_analyze_job', lambda *_args, **_kwargs: None)
    assert analyze_worker.process_next_analyze_job(fake_db) is False


def test_analyze_job_unexpected_failure_schedules_retry(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = AnalyzeSnapshot(
        repo_id='00000000-0000-0000-0000-000000000081',
        job_id='00000000-0000-0000-0000-000000000082',
        full_name='test-owner/repo',
        default_branch='main',
    )
    monkeypatch.setattr(analyze_worker, 'load_repo_chunks', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('boom')))
    called = {'stage': None, 'code': None}

    def fake_schedule(*_args, **kwargs):
        called['stage'] = kwargs['stage']
        called['code'] = kwargs['error_code']

    monkeypatch.setattr(analyze_worker, 'schedule_retry_or_dead_letter', fake_schedule)
    observed = {'count': 0}
    monkeypatch.setattr(analyze_worker, 'record_stage_duration', lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1))
    analyze_worker.analyze_job(fake_db, snapshot)

    assert called['stage'] == 'analyzing'
    assert called['code'] == 'UNEXPECTED_ANALYZE_ERROR'
    assert observed['count'] == 1
