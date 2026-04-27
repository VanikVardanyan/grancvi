"""master.phone_public — public/private toggle for the phone field

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-27 18:00:00.000000

`grancvi.am/<slug>` shows a no-Telegram fallback button that calls the
master's phone via tel: link. Some masters don't want their personal
number on a publicly-resolvable URL, so we gate the exposure behind an
explicit toggle in the master profile. Default `true` for back-compat:
existing masters are happy to be called (that's how they worked before
Telegram), and they can flip it off in profile if they prefer.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column(
            "phone_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("masters", "phone_public")
