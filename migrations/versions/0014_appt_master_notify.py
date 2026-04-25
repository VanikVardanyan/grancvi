"""appointments: track the master's notify message for back-edits

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-26 00:30:00.000000

When the bot DMs the master with the inline approve/reject keyboard,
we now store (chat_id, message_id, via) so that an approve/reject
done from anywhere — including the TMA dashboard — can call
edit_message_reply_markup on the original message and strip the
keyboard. Without this the chat message stayed live with stale
buttons that re-fired the legacy bot flow.

`via` is either 'app_bot' (the new @grancviWebBot) or 'fallback_bot'
(the legacy bot) so we know which bot session to issue the edit from.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column("master_notify_chat_id", sa.BigInteger, nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("master_notify_msg_id", sa.Integer, nullable=True),
    )
    op.add_column(
        "appointments",
        sa.Column("master_notify_via", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "master_notify_via")
    op.drop_column("appointments", "master_notify_msg_id")
    op.drop_column("appointments", "master_notify_chat_id")
