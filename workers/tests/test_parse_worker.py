import tempfile
from pathlib import Path

import pytest

import parse_worker
from parse_worker import ParseError, RepoSnapshot, chunk_lines, iter_source_files, parse_job


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



def test_chunk_lines_with_overlap() -> None:
    content = '\n'.join([f'line-{i}' for i in range(1, 11)])
    chunks = chunk_lines(content, chunk_lines=4, overlap_lines=1)

    assert len(chunks) == 3
    assert chunks[0][0] == 1
    assert chunks[0][1] == 4
    assert chunks[1][0] == 4
    assert chunks[2][1] == 10


def test_chunk_lines_rejects_invalid_config() -> None:
    with pytest.raises(ParseError) as exc:
        chunk_lines('a\nb', chunk_lines=10, overlap_lines=10)
    assert exc.value.code == 'INVALID_CHUNK_CONFIG'


def test_iter_source_files_filters_extensions_and_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'src').mkdir()
        (root / 'src' / 'a.py').write_text('print(1)')
        (root / 'src' / 'b.txt').write_text('ignore')
        (root / 'node_modules').mkdir()
        (root / 'node_modules' / 'x.js').write_text('ignore')

        files = list(iter_source_files(tmp))
        rel = {str(p.relative_to(tmp)).replace('\\', '/') for p in files}

        assert 'src/a.py' in rel
        assert 'src/b.txt' not in rel
        assert 'node_modules/x.js' not in rel


def test_parse_job_fails_when_file_limit_exceeded(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = RepoSnapshot('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', 'https://github.com/x/y', 'abc')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for i in range(3):
            (root / f'f{i}.py').write_text('print(1)')

        monkeypatch.setattr(parse_worker.settings, 'parse_max_files', 2)
        monkeypatch.setattr(parse_worker, 'clone_repo', lambda *_args, **_kwargs: tmp)

        parse_job(fake_db, snapshot)

    # Verify we marked failed with explicit guardrail code.
    fail_updates = [e for e in fake_db.events if e[0] == 'execute' and 'UPDATE analysis_jobs' in str(e[1][0])]
    assert any('FILE_LIMIT_EXCEEDED' in str(ev) for ev in fail_updates)


def test_parse_job_success_transitions_to_embedding(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = RepoSnapshot('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000012', 'https://github.com/x/y', 'abc')

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / 'main.py').write_text('\n'.join(['x=1'] * 50))

        monkeypatch.setattr(parse_worker.settings, 'parse_max_files', 100)
        monkeypatch.setattr(parse_worker.settings, 'parse_max_chunks', 100)
        monkeypatch.setattr(parse_worker, 'clone_repo', lambda *_args, **_kwargs: tmp)

        stored = {'called': False, 'count': 0}

        def fake_store(_db, _repo_id, chunks):
            stored['called'] = True
            stored['count'] = len(chunks)

        monkeypatch.setattr(parse_worker, 'store_chunks', fake_store)
        observed = {'count': 0}
        monkeypatch.setattr(parse_worker, 'record_stage_duration', lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1))

        parse_job(fake_db, snapshot)

    assert stored['called'] is True
    assert stored['count'] > 0
    assert observed['count'] == 1
    updates = [e for e in fake_db.events if e[0] == 'execute' and 'UPDATE analysis_jobs' in str(e[1][0])]
    assert any("'embedding'" in str(u) or 'embedding' in str(u) for u in updates)


def test_parse_job_retriable_failure_schedules_retry(monkeypatch) -> None:
    fake_db = FakeSession()
    snapshot = RepoSnapshot(
        '00000000-0000-0000-0000-000000000061',
        '00000000-0000-0000-0000-000000000062',
        'https://github.com/x/y',
        'abc',
    )

    monkeypatch.setattr(parse_worker, 'clone_repo', lambda *_args, **_kwargs: (_ for _ in ()).throw(ParseError('CLONE_TIMEOUT', 'timeout')))
    called = {'stage': None, 'code': None}

    def fake_schedule(*_args, **kwargs):
        called['stage'] = kwargs['stage']
        called['code'] = kwargs['error_code']

    monkeypatch.setattr(parse_worker, 'schedule_retry_or_dead_letter', fake_schedule)
    observed = {'count': 0}
    monkeypatch.setattr(parse_worker, 'record_stage_duration', lambda *_args, **_kwargs: observed.__setitem__('count', observed['count'] + 1))
    parse_job(fake_db, snapshot)

    assert called['stage'] == 'parsing'
    assert called['code'] == 'CLONE_TIMEOUT'
    assert observed['count'] == 1
