"""master.slot_step_min default 20 -> 10 minutes

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-29 06:35:00.000000

New masters get a 10-minute default grid instead of 20 — covers more
realistic salon cadence (haircut 30, manicure 90, etc. all align on 10
just as well as 20). Existing masters keep whatever they had set;
this only affects the column default for future inserts.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("masters", "slot_step_min", server_default="10")


def downgrade() -> None:
    op.alter_column("masters", "slot_step_min", server_default="20")
