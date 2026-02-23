"""code_chunks fts backfill and trigger

Revision ID: 20260223_0005
Revises: 20260223_0004
Create Date: 2026-02-23 13:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0005"
down_revision: Union[str, None] = "20260223_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION devlens_code_chunks_fts_sync()
        RETURNS trigger AS $$
        BEGIN
            NEW.fts := to_tsvector('english', coalesce(NEW.file_path, '') || ' ' || coalesce(NEW.content, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_code_chunks_fts_sync ON code_chunks;
        CREATE TRIGGER trg_code_chunks_fts_sync
        BEFORE INSERT OR UPDATE OF file_path, content ON code_chunks
        FOR EACH ROW
        EXECUTE FUNCTION devlens_code_chunks_fts_sync();
        """
    )
    op.execute(
        """
        UPDATE code_chunks
        SET fts = to_tsvector('english', coalesce(file_path, '') || ' ' || coalesce(content, ''))
        WHERE fts IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_code_chunks_fts_sync ON code_chunks;")
    op.execute("DROP FUNCTION IF EXISTS devlens_code_chunks_fts_sync();")
    op.execute("UPDATE code_chunks SET fts = NULL;")
