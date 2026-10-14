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
    tech_debt = {'todo_count': 500, 'long_function_count': 100, 'test_file_count': 0}
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
    assert summary == 'test-owner/repo has 1 indexed file across src and the repository root. ' \
        'A written summary was not generated for this analysis.'
    assert 'later stages' not in summary


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

    assert summary.startswith('test-owner/repo has 1 indexed file')
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

    assert summary.startswith('test-owner/repo has 1 indexed file')
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


def _chunk(path: str, start: int = 1, content: str = 'x = 1') -> ChunkRecord:
    return ChunkRecord(file_path=path, start_line=start, end_line=start + 9, content=content, language='py')


def test_summary_sources_rank_readme_manifest_entrypoints_and_skip_tests() -> None:
    chunks = [
        _chunk('src/pkg/core.py'),
        _chunk('tests/main.py'),
        _chunk('docs/README.md'),
        _chunk('src/pkg/__init__.py'),
        _chunk('pyproject.toml'),
        _chunk('README.md', start=40, content='later part'),
        _chunk('README.md', start=1, content='# pkg'),
        _chunk('src/pkg/__main__.py'),
        _chunk('app.py', content='   '),
    ]

    sources = analyze_worker.select_summary_sources(chunks)

    assert [(c.file_path, c.start_line) for c in sources] == [
        ('README.md', 1),
        ('pyproject.toml', 1),
        ('src/pkg/__main__.py', 1),
        ('src/pkg/__init__.py', 1),
    ]


def test_summary_sources_are_capped() -> None:
    chunks = [_chunk(f'pkg{n}/__init__.py') for n in range(10)]

    assert len(analyze_worker.select_summary_sources(chunks)) == analyze_worker.SUMMARY_SOURCE_LIMIT


def test_summary_prompt_carries_readme_and_entrypoint_code(monkeypatch) -> None:
    snapshot = AnalyzeSnapshot(repo_id='r', job_id='j', full_name='test-owner/repo', default_branch='main')
    chunks = [
        _chunk('README.md', content='# repo Signs data so it can travel safely.'),
        _chunk('src/repo/__init__.py', content='from .signer import Signer'),
        _chunk('src/repo/signer.py', content='class Signer: ...'),
    ]
    monkeypatch.setattr(analyze_worker.settings, 'openrouter_api_key', 'test-key')
    captured = {}

    class CapturingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _url, headers=None, json=None):
            captured['prompt'] = json['messages'][1]['content']
            return _JsonResponse(200, {'choices': [{'message': {'content': 'A signing library.'}}]})

    monkeypatch.setattr(analyze_worker.httpx, 'Client', CapturingClient)

    assert analyze_worker.generate_architecture_summary(snapshot, {'py': 100.0}, chunks) == 'A signing library.'
    assert 'Signs data so it can travel safely.' in captured['prompt']
    assert 'from .signer import Signer' in captured['prompt']
    assert 'src/repo/signer.py' in captured['prompt']


def test_tech_debt_reports_parse_time_signals_longest_first() -> None:
    chunks = [
        ChunkRecord(file_path='src/app.py', start_line=1, end_line=9, content='x', language='py'),
        ChunkRecord(file_path='tests/test_app.py', start_line=1, end_line=9, content='x', language='py'),
    ]
    signals = {
        'long_functions': [
            {'file': 'src/app.py', 'name': 'short_one', 'line': 10, 'length': 55},
            {'file': 'src/app.py', 'name': 'long_one', 'line': 90, 'length': 120},
        ],
        'todo_files': {'src/app.py': 3, 'src/db.py': 1},
    }

    debt = analyze_worker.detect_tech_debt(chunks, signals)

    assert [f['name'] for f in debt['long_functions']] == ['long_one', 'short_one']
    assert debt['long_function_count'] == 2
    assert (debt['todo_count'], debt['todo_file_count'], debt['test_file_count']) == (4, 2, 1)
    assert debt['measured'] is True


def test_tech_debt_for_a_job_parsed_before_signals_existed() -> None:
    chunks = [ChunkRecord(file_path='src/app.py', start_line=1, end_line=90, content='x', language='py')]

    debt = analyze_worker.detect_tech_debt(chunks, None)

    assert debt['measured'] is False
    assert debt['long_function_count'] == 0
