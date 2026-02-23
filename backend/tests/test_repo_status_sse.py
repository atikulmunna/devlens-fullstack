from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AnalysisJob, Repository


def _create_repo(db_session: Session) -> Repository:
    repo = Repository(
        id=uuid4(),
        github_url='https://github.com/test-owner/status-repo',
        full_name='test-owner/status-repo',
        owner='test-owner',
        name='status-repo',
        default_branch='main',
        latest_commit_sha='sha-status',
    )
    db_session.add(repo)
    db_session.commit()
    return repo


def test_status_stream_progress_event_once(client, db_session: Session) -> None:
    repo = _create_repo(db_session)
    db_session.add(
        AnalysisJob(
            id=uuid4(),
            repo_id=repo.id,
            status='parsing',
            progress=35,
            commit_sha='sha-status',
        )
    )
    db_session.commit()

    response = client.get(f'/api/v1/repos/{repo.id}/status?once=true')
    assert response.status_code == 200
    assert 'event: progress' in response.text
    assert '"stage": "parsing"' in response.text
    assert '"progress": 35' in response.text


def test_status_stream_done_event_once(client, db_session: Session) -> None:
    repo = _create_repo(db_session)
    db_session.add(
        AnalysisJob(
            id=uuid4(),
            repo_id=repo.id,
            status='done',
            progress=100,
            commit_sha='sha-status',
        )
    )
    db_session.commit()

    response = client.get(f'/api/v1/repos/{repo.id}/status?once=true')
    assert response.status_code == 200
    assert 'event: done' in response.text
    assert '"stage": "done"' in response.text


def test_status_stream_error_event_once(client, db_session: Session) -> None:
    repo = _create_repo(db_session)
    db_session.add(
        AnalysisJob(
            id=uuid4(),
            repo_id=repo.id,
            status='failed',
            progress=100,
            commit_sha='sha-status',
            error_message='FILE_LIMIT_EXCEEDED: Repo has too many files',
        )
    )
    db_session.commit()

    response = client.get(f'/api/v1/repos/{repo.id}/status?once=true')
    assert response.status_code == 200
    assert 'event: error' in response.text
    assert '"code": "FILE_LIMIT_EXCEEDED"' in response.text


def test_status_stream_returns_404_for_unknown_repo(client) -> None:
    response = client.get(f'/api/v1/repos/{uuid4()}/status?once=true')
    assert response.status_code == 404
