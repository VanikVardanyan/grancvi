"""relax invite usage CHECK so salon-owner invites can be redeemed

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-24 18:30:00.000000

The original constraint required `used_by_tg_id`, `used_at`, and
`used_for_master_id` to all be either NULL or NOT NULL together.
That worked for master invites but blocks salon-owner invites, which
don't create a master row and thus have nothing to put in
`used_for_master_id`. New rule: only `used_by_tg_id` and `used_at`
must move together; the master-id column is optional.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_invites_usage_tuple", "invites", type_="check")
    op.create_check_constraint(
        "ck_invites_usage_tuple",
        "invites",
        "(used_by_tg_id IS NULL) = (used_at IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_invites_usage_tuple", "invites", type_="check")
    op.create_check_constraint(
        "ck_invites_usage_tuple",
        "invites",
        "(used_by_tg_id IS NULL) = (used_at IS NULL) "
        "AND (used_at IS NULL) = (used_for_master_id IS NULL)",
    )
