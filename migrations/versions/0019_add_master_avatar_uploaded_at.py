"""add_master_avatar_uploaded_at

Revision ID: 0019
Revises: f96bbf15c0f1
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: Union[str, Sequence[str], None] = "f96bbf15c0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column("avatar_uploaded_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("masters", "avatar_uploaded_at")
