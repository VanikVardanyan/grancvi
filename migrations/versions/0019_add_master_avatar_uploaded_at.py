"""masters.avatar_uploaded_at — set when master uploads a profile photo

Revision ID: 0019
Revises: f96bbf15c0f1
Create Date: 2026-05-10 00:00:00.000000

NULL until the master uploads a profile photo via the bot. Used as a
presence flag (NULL = no avatar) and as a cache-buster (?v=<unix_ts>)
in URLs returned by the public API. The actual JPEG lives on disk
under settings.avatars_dir as <master_id>.jpg.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "f96bbf15c0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column("avatar_uploaded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("masters", "avatar_uploaded_at")
