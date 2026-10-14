import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import AnalysisJob, CodeChunk, Repository


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


def _add_job_with_chunks(db_session: Session, status: str) -> Repository:
    """Two files, three chunks, two of them already indexed in the vector store."""
    repo = _create_repo(db_session)
    db_session.add(AnalysisJob(id=uuid4(), repo_id=repo.id, status=status, progress=50, commit_sha='sha-status'))
    for file_path, indexed in [('a.py', True), ('a.py', True), ('b.py', False)]:
        db_session.add(
            CodeChunk(
                id=uuid4(),
                repo_id=repo.id,
                file_path=file_path,
                start_line=1,
                end_line=5,
                content='x = 1',
                language='py',
                qdrant_point_id=uuid4() if indexed else None,
            )
        )
    db_session.commit()
    return repo


def _payload(response_text: str) -> dict:
    data_line = next(line for line in response_text.splitlines() if line.startswith('data: '))
    return json.loads(data_line[len('data: '):])


def test_status_reports_file_and_chunk_counts_while_indexing(client, db_session: Session) -> None:
    repo = _add_job_with_chunks(db_session, 'embedding')

    payload = _payload(client.get(f'/api/v1/repos/{repo.id}/status?once=true').text)

    assert payload['stage'] == 'embedding'
    assert (payload['files'], payload['chunks'], payload['indexed_chunks']) == (2, 3, 2)


def test_status_done_event_carries_counts(client, db_session: Session) -> None:
    repo = _add_job_with_chunks(db_session, 'done')

    payload = _payload(client.get(f'/api/v1/repos/{repo.id}/status?once=true').text)

    assert payload['stage'] == 'done'
    assert payload['files'] == 2


def test_status_omits_counts_while_old_chunks_may_still_be_in_place(client, db_session: Session) -> None:
    repo = _add_job_with_chunks(db_session, 'parsing')

    payload = _payload(client.get(f'/api/v1/repos/{repo.id}/status?once=true').text)

    assert payload['stage'] == 'parsing'
    assert 'files' not in payload
    assert 'chunks' not in payload
