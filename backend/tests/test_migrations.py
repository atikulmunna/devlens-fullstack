from sqlalchemy import text
from sqlalchemy.orm import Session


def test_schema_tables_exist(db_session: Session) -> None:
    rows = db_session.execute(
        text("select table_name from information_schema.tables where table_schema='public'")
    ).fetchall()
    tables = {row[0] for row in rows}

    required = {
        'users',
        'repositories',
        'analysis_jobs',
        'analysis_results',
        'code_chunks',
        'chat_sessions',
        'chat_messages',
        'refresh_tokens',
        'share_tokens',
        'dead_letter_jobs',
        'alembic_version',
    }
    assert required.issubset(tables)


def test_alembic_head_is_applied(db_session: Session) -> None:
    version = db_session.execute(text('select version_num from alembic_version')).scalar_one()
    assert version == '20260223_0006'


def test_hot_path_indexes_exist(db_session: Session) -> None:
    rows = db_session.execute(
        text(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            """
        )
    ).fetchall()
    indexes = {row[0] for row in rows}
    required = {
        "idx_code_chunks_fts",
        "idx_analysis_jobs_repo_status",
        "idx_analysis_jobs_retry",
        "idx_analysis_jobs_repo_commit_idempotency",
        "idx_analysis_jobs_repo_commit_status_created",
        "idx_analysis_results_repo_created",
    }
    assert required.issubset(indexes)
