"""appointments.source_salon_id — track booking referral from salon QR

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-25 20:00:00.000000

When a client enters via the salon QR (`start=salon_<slug>`) the salon
that referred them is recorded on the resulting booking. Salon owners
see "📌 via this salon" badges in their dashboard so they can tell
which bookings their stickers actually pulled in vs. ones the master
brought via their own link.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, Sequence[str], None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "source_salon_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("appointments", "source_salon_id")
