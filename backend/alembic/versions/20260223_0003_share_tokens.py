"""add share token store

Revision ID: 20260223_0003
Revises: 20260223_0002
Create Date: 2026-02-23 10:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260223_0003"
down_revision: Union[str, None] = "20260223_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "share_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_share_tokens_repo_id", "share_tokens", ["repo_id"])
    op.create_index("idx_share_tokens_user_id", "share_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_share_tokens_user_id", table_name="share_tokens")
    op.drop_index("idx_share_tokens_repo_id", table_name="share_tokens")
    op.drop_table("share_tokens")
