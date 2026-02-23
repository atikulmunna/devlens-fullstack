from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.api.v1.repos as repos_module
from app.db.models import AnalysisJob, AnalysisResult, Repository


def _snapshot(commit_sha: str = 'abc123') -> dict:
    return {
        'github_url': 'https://github.com/test-owner/test-repo',
        'full_name': 'test-owner/test-repo',
        'owner': 'test-owner',
        'name': 'test-repo',
        'description': 'Test repository',
        'stars': 10,
        'forks': 2,
        'language': 'Python',
        'size_kb': 321,
        'default_branch': 'main',
        'commit_sha': commit_sha,
    }


def test_analyze_repo_creates_new_job(client, db_session: Session, monkeypatch):
    monkeypatch.setattr(repos_module, 'resolve_public_repo_snapshot', lambda url: _snapshot('sha-new'))

    response = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://github.com/test-owner/test-repo', 'force_reanalyze': False},
        headers={'Idempotency-Key': 'idem-1'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'queued'
    assert payload['cache_hit'] is False
    assert payload['commit_sha'] == 'sha-new'

    repo = db_session.execute(select(Repository).where(Repository.full_name == 'test-owner/test-repo')).scalar_one()
    job = db_session.execute(select(AnalysisJob).where(AnalysisJob.id == payload['job_id'])).scalar_one()
    assert str(repo.id) == payload['repo_id']
    assert job.idempotency_key == 'idem-1'


def test_analyze_repo_dedupes_by_idempotency_key(client, monkeypatch):
    monkeypatch.setattr(repos_module, 'resolve_public_repo_snapshot', lambda url: _snapshot('sha-idem'))

    first = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://github.com/test-owner/test-repo', 'force_reanalyze': False},
        headers={'Idempotency-Key': 'idem-dup'},
    )
    second = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://github.com/test-owner/test-repo', 'force_reanalyze': False},
        headers={'Idempotency-Key': 'idem-dup'},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()['job_id'] == first.json()['job_id']


def test_analyze_repo_returns_cache_hit_on_done_job(client, db_session: Session, monkeypatch):
    monkeypatch.setattr(repos_module, 'resolve_public_repo_snapshot', lambda url: _snapshot('sha-done'))

    created = client.post('/api/v1/repos/analyze', json={'github_url': 'https://github.com/test-owner/test-repo'})
    assert created.status_code == 200

    job = db_session.execute(select(AnalysisJob).where(AnalysisJob.id == created.json()['job_id'])).scalar_one()
    job.status = 'done'
    db_session.commit()

    repeated = client.post('/api/v1/repos/analyze', json={'github_url': 'https://github.com/test-owner/test-repo'})
    assert repeated.status_code == 200
    assert repeated.json()['job_id'] == created.json()['job_id']
    assert repeated.json()['cache_hit'] is True


def test_analyze_repo_force_reanalyze_creates_new_job(client, monkeypatch):
    monkeypatch.setattr(repos_module, 'resolve_public_repo_snapshot', lambda url: _snapshot('sha-force'))

    first = client.post('/api/v1/repos/analyze', json={'github_url': 'https://github.com/test-owner/test-repo'})
    second = client.post(
        '/api/v1/repos/analyze',
        json={'github_url': 'https://github.com/test-owner/test-repo', 'force_reanalyze': True},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()['job_id'] != first.json()['job_id']


def test_analyze_repo_rejects_invalid_url(client):
    response = client.post('/api/v1/repos/analyze', json={'github_url': 'https://example.com/not-github'})
    assert response.status_code == 400


def test_get_repo_dashboard_returns_latest_analysis(client, db_session: Session):
    repo = Repository(
        id=uuid4(),
        github_url='https://github.com/test-owner/dash-repo',
        full_name='test-owner/dash-repo',
        owner='test-owner',
        name='dash-repo',
        default_branch='main',
        latest_commit_sha='sha-dash',
        description='Dashboard repo',
        stars=11,
        forks=3,
        language='Python',
        size_kb=400,
    )
    db_session.add(repo)
    db_session.flush()

    older = AnalysisResult(
        id=uuid4(),
        repo_id=repo.id,
        job_id=None,
        architecture_summary='old',
        quality_score=50,
        language_breakdown={'Python': 100},
        contributor_stats={'total': 1},
        tech_debt_flags={'todo': 5},
        file_tree={'type': 'dir', 'name': '/'},
        cache_key='old-cache-key',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = AnalysisResult(
        id=uuid4(),
        repo_id=repo.id,
        job_id=None,
        architecture_summary='new summary',
        quality_score=88,
        language_breakdown={'Python': 80, 'TS': 20},
        contributor_stats={'total': 2},
        tech_debt_flags={'todo': 1},
        file_tree={'type': 'dir', 'name': '/', 'children': []},
        cache_key='new-cache-key',
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    db_session.add(older)
    db_session.add(newer)
    db_session.commit()

    response = client.get(f'/api/v1/repos/{repo.id}/dashboard')
    assert response.status_code == 200
    payload = response.json()
    assert payload['repo_id'] == str(repo.id)
    assert payload['repository']['full_name'] == 'test-owner/dash-repo'
    assert payload['has_analysis'] is True
    assert payload['analysis']['quality_score'] == 88
    assert payload['analysis']['architecture_summary'] == 'new summary'


def test_get_repo_dashboard_without_analysis(client, db_session: Session):
    repo = Repository(
        id=uuid4(),
        github_url='https://github.com/test-owner/no-analysis',
        full_name='test-owner/no-analysis',
        owner='test-owner',
        name='no-analysis',
        default_branch='main',
    )
    db_session.add(repo)
    db_session.commit()

    response = client.get(f'/api/v1/repos/{repo.id}/dashboard')
    assert response.status_code == 200
    payload = response.json()
    assert payload['repo_id'] == str(repo.id)
    assert payload['has_analysis'] is False
    assert payload['analysis'] is None


def test_get_repo_dashboard_404_for_missing_repo(client):
    response = client.get(f'/api/v1/repos/{uuid4()}/dashboard')
    assert response.status_code == 404
