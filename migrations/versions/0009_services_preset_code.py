"""services.preset_code for localization-on-display

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-25 12:00:00.000000

A free-text `name` doesn't survive a UI language switch — clients
who book in Armenian still see Russian names typed by the master.
Storing a pre-defined preset code alongside the name lets the
frontend swap labels via i18n, while custom-typed services keep
rendering as-is.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "services",
        sa.Column("preset_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("services", "preset_code")
