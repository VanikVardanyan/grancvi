"""masters.address — free-text public address

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-20 00:00:00.000000

NULL until the master fills it in. Rendered on the master's public
TMA page (/m/<slug>) so clients know where to come. No geocoding /
format validation — masters write whatever helps clients find them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column("address", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("masters", "address")
