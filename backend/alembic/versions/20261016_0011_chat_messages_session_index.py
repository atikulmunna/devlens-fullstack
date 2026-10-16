"""index chat_messages by session and time

Every chat read filters messages by session and orders them by time (history for the model, a
session's transcript, the session list's count and latest message); without an index each one
scanned the whole table.

Revision ID: 20261016_0011
Revises: 20261016_0010
Create Date: 2026-10-16 00:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0011"
down_revision: Union[str, None] = "20261016_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("idx_chat_messages_session_created", "chat_messages", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_chat_messages_session_created", table_name="chat_messages")
