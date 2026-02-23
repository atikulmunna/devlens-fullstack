"""add hot-path indexes for analyze and dashboard queries

Revision ID: 20260223_0006
Revises: 20260223_0005
Create Date: 2026-02-23 15:35:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260223_0006"
down_revision: Union[str, None] = "20260223_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "idx_analysis_jobs_repo_commit_idempotency",
        "analysis_jobs",
        ["repo_id", "commit_sha", "idempotency_key"],
    )
    op.create_index(
        "idx_analysis_jobs_repo_commit_status_created",
        "analysis_jobs",
        ["repo_id", "commit_sha", "status", "created_at"],
    )
    op.create_index(
        "idx_analysis_results_repo_created",
        "analysis_results",
        ["repo_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_analysis_results_repo_created", table_name="analysis_results")
    op.drop_index("idx_analysis_jobs_repo_commit_status_created", table_name="analysis_jobs")
    op.drop_index("idx_analysis_jobs_repo_commit_idempotency", table_name="analysis_jobs")
