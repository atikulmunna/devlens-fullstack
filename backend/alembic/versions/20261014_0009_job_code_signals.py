"""add analysis_jobs.code_signals for code health measured while parsing

Revision ID: 20261014_0009
Revises: 20260719_0008
Create Date: 2026-10-14 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261014_0009"
down_revision: Union[str, None] = "20260719_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column("code_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_jobs", "code_signals")
