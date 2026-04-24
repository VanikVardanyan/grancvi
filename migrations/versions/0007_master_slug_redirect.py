"""master slug redirect: redirect_master_id / redirect_salon_id

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column(
            "redirect_master_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "masters",
        sa.Column(
            "redirect_salon_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Mutual exclusion — at most one redirect target is set at a time.
    op.create_check_constraint(
        "ck_masters_redirect_single_target",
        "masters",
        "NOT (redirect_master_id IS NOT NULL AND redirect_salon_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_masters_redirect_single_target", "masters", type_="check")
    op.drop_column("masters", "redirect_salon_id")
    op.drop_column("masters", "redirect_master_id")
