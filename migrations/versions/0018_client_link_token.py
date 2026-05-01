"""client.link_token — one-shot token for binding tg_id from web booking

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-01 12:00:00.000000

Web-booking flow gives the new client a `link_<token>` deep-link to
the bot. When they tap, the bot resolves the token, sets Client.tg_id
to update.from_user.id, and clears the token so it's not reusable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("link_token", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_clients_link_token",
        "clients",
        ["link_token"],
        unique=False,
        postgresql_where=sa.text("link_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_clients_link_token", table_name="clients")
    op.drop_column("clients", "link_token")
