"""epic 7: rename master_morning to master_before + unique reminder per appt/kind

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-21 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE reminders SET kind = 'master_before' WHERE kind = 'master_morning'")

    op.drop_constraint("ck_reminders_kind", "reminders", type_="check")
    op.create_check_constraint(
        "ck_reminders_kind",
        "reminders",
        "kind IN ('day_before', 'two_hours', 'master_before')",
    )

    op.create_unique_constraint(
        "uq_reminders_appointment_kind",
        "reminders",
        ["appointment_id", "kind"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reminders_appointment_kind", "reminders", type_="unique")
    op.drop_constraint("ck_reminders_kind", "reminders", type_="check")
    op.create_check_constraint(
        "ck_reminders_kind",
        "reminders",
        "kind IN ('day_before', 'two_hours', 'master_morning')",
    )
    op.execute("UPDATE reminders SET kind = 'master_morning' WHERE kind = 'master_before'")
