"""worker retry and dead letter support

Revision ID: 20260223_0004
Revises: 20260223_0003
Create Date: 2026-02-23 11:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260223_0004"
down_revision: Union[str, None] = "20260223_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("analysis_jobs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_analysis_jobs_retry", "analysis_jobs", ["status", "next_retry_at"])

    op.create_table(
        "dead_letter_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analysis_jobs.id"), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_dead_letter_jobs_job_id", "dead_letter_jobs", ["job_id"])
    op.create_index("idx_dead_letter_jobs_repo_id", "dead_letter_jobs", ["repo_id"])


def downgrade() -> None:
    op.drop_index("idx_dead_letter_jobs_repo_id", table_name="dead_letter_jobs")
    op.drop_index("idx_dead_letter_jobs_job_id", table_name="dead_letter_jobs")
    op.drop_table("dead_letter_jobs")

    op.drop_index("idx_analysis_jobs_retry", table_name="analysis_jobs")
    op.drop_column("analysis_jobs", "next_retry_at")
    op.drop_column("analysis_jobs", "retry_count")
