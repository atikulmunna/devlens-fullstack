"""add commit_diffs table for commit-diff intelligence

Revision ID: 20260719_0008
Revises: 20260224_0007
Create Date: 2026-07-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260719_0008"
down_revision: Union[str, None] = "20260224_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commit_diffs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("base_sha", sa.String(length=64), nullable=True),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("changed_files", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("security_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_commit_diffs_repo_created", "commit_diffs", ["repo_id", "created_at"])
    op.create_index("idx_commit_diffs_repo_head", "commit_diffs", ["repo_id", "head_sha"])


def downgrade() -> None:
    op.drop_index("idx_commit_diffs_repo_head", table_name="commit_diffs")
    op.drop_index("idx_commit_diffs_repo_created", table_name="commit_diffs")
    op.drop_table("commit_diffs")
