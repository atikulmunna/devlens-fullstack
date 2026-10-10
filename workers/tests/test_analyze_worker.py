import pytest

import analyze_worker
from analyze_worker import AnalyzeSnapshot, ChunkRecord


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


def test_generate_architecture_summary_falls_back_without_api_key(monkeypatch) -> None:
    snapshot = AnalyzeSnapshot(
        repo_id='00000000-0000-0000-0000-000000000071',
        job_id='00000000-0000-0000-0000-000000000072',
        full_name='test-owner/repo',
        default_branch='main',
    )
    chunks = [
        ChunkRecord(file_path='src/a.py', start_line=1, end_line=10, content='print(1)', language='py'),
    ]
    monkeypatch.setattr(analyze_worker.settings, 'openrouter_api_key', None)
    summary = analyze_worker.generate_architecture_summary(snapshot, {'py': 100.0}, chunks)
    assert 'Repository test-owner/repo' in summary


def test_generate_architecture_summary_uses_llm_response(monkeypatch) -> None:
    snapshot = AnalyzeSnapshot(
        repo_id='00000000-0000-0000-0000-000000000073',
        job_id='00000000-0000-0000-0000-000000000074',
        full_name='test-owner/repo',
        default_branch='main',
    )
    chunks = [
        ChunkRecord(file_path='src/a.py', start_line=1, end_line=10, content='print(1)', language='py'),
    ]

    monkeypatch.setattr(analyze_worker.settings, 'openrouter_api_key', 'test-key')
    monkeypatch.setattr(analyze_worker.settings, 'openrouter_base_url', 'https://example.test/api/v1')
    monkeypatch.setattr(analyze_worker.settings, 'llm_summary_model', 'test-model')
    monkeypatch.setattr(analyze_worker.settings, 'llm_summary_timeout_seconds', 5)

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {'choices': [{'message': {'content': 'LLM architecture summary'}}]}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            return DummyResponse()

    monkeypatch.setattr(analyze_worker.httpx, 'Client', DummyClient)
    summary = analyze_worker.generate_architecture_summary(snapshot, {'py': 100.0}, chunks)
    assert summary == 'LLM architecture summary'


@pytest.mark.parametrize(
    ('failure', 'error_code'),
    [
        (500, 'LLM_PROVIDER_HTTP_ERROR'),
        (429, 'LLM_PROVIDER_RATE_LIMITED'),
        (analyze_worker.httpx.TimeoutException('timed out'), 'LLM_PROVIDER_TIMEOUT'),
        (analyze_worker.httpx.ConnectError('unreachable'), 'LLM_PROVIDER_TRANSPORT_ERROR'),
    ],
)
def test_generate_architecture_summary_falls_back_when_openrouter_fails(monkeypatch, failure, error_code) -> None:
    snapshot = AnalyzeSnapshot(
        repo_id='00000000-0000-0000-0000-000000000091',
        job_id='00000000-0000-0000-0000-000000000092',
        full_name='test-owner/repo',
        default_branch='main',
    )
    chunks = [
        ChunkRecord(file_path='src/a.py', start_line=1, end_line=10, content='print(1)', language='py'),
    ]
    monkeypatch.setattr(analyze_worker.settings, 'openrouter_api_key', 'openrouter-key')
    monkeypatch.setattr(analyze_worker.settings, 'openrouter_base_url', 'https://example.test/openrouter')

    provider_attempts = []
    monkeypatch.setattr(
        analyze_worker,
        'record_llm_provider_attempt',
        lambda provider, status, error_code='none': provider_attempts.append((provider, status, error_code)),
    )

    class DummyResponse:
        text = ''

        def __init__(self, status_code: int):
            self.status_code = status_code

        def json(self):
            return {}

    class DummyClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            if isinstance(failure, Exception):
                raise failure
            return DummyResponse(failure)

    monkeypatch.setattr(analyze_worker.httpx, 'Client', DummyClient)
    summary = analyze_worker.generate_architecture_summary(snapshot, {'py': 100.0}, chunks)

    assert 'Repository test-owner/repo' in summary
    assert provider_attempts == [
        ('openrouter', 'error', error_code),
        ('fallback_summary', 'success', error_code),
    ]


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


class _ErrorClient:
    """httpx.Client stand-in whose post/get return one canned response or raise."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        if self._error:
            raise self._error
        return self._response

    get = post


class _JsonResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = ''

    def json(self):
        return self._payload


def test_summary_failure_logs_openrouter_reason(monkeypatch, caplog) -> None:
    snapshot = AnalyzeSnapshot(repo_id='r', job_id='j', full_name='test-owner/repo', default_branch='main')
    chunks = [ChunkRecord(file_path='src/a.py', start_line=1, end_line=10, content='print(1)', language='py')]
    monkeypatch.setattr(analyze_worker.settings, 'openrouter_api_key', 'openrouter-key')
    monkeypatch.setattr(analyze_worker, 'record_llm_provider_attempt', lambda *args, **kwargs: None)
    retired = _JsonResponse(404, {'error': {'message': 'This model is unavailable for free', 'code': 404}})
    monkeypatch.setattr(analyze_worker.httpx, 'Client', _ErrorClient(response=retired))

    summary = analyze_worker.generate_architecture_summary(snapshot, {'py': 100.0}, chunks)

    assert 'Repository test-owner/repo' in summary
    # This exact failure (a retired free model) was invisible before: only "llm_provider_http_error" was recorded.
    assert 'LLM_PROVIDER_HTTP_ERROR' in caplog.text
    assert 'status 404: This model is unavailable for free' in caplog.text


def test_contributor_stats_failures_are_logged(monkeypatch, caplog) -> None:
    monkeypatch.setattr(analyze_worker.httpx, 'Client', _ErrorClient(error=analyze_worker.httpx.ConnectError('dns failure')))
    unreachable = analyze_worker.get_contributor_stats('test-owner/repo')

    monkeypatch.setattr(analyze_worker.httpx, 'Client', _ErrorClient(response=_JsonResponse(403, {})))
    rate_limited = analyze_worker.get_contributor_stats('test-owner/repo')

    assert unreachable == {'top_contributors': [], 'error': 'github_unreachable'}
    assert rate_limited == {'top_contributors': [], 'error': 'github_status_403'}
    assert 'dns failure' in caplog.text
    assert 'returned status 403' in caplog.text
