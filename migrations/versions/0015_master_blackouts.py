"""master_blackouts — one-off non-working dates per master

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-26 12:00:00.000000

The weekly schedule (masters.work_hours) is recurring, but masters
need to mark specific dates as days off (vacation, sick day, holiday).
This table holds those exceptions; AvailabilityService skips slot
generation when the local date is in the set.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "master_blackouts",
        sa.Column(
            "master_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("date", sa.Date, primary_key=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_master_blackouts_master_date",
        "master_blackouts",
        ["master_id", "date"],
    )


def downgrade() -> None:
    op.drop_index("ix_master_blackouts_master_date", "master_blackouts")
    op.drop_table("master_blackouts")
