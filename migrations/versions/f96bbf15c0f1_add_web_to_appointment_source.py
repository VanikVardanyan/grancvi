"""add_web_to_appointment_source

Revision ID: f96bbf15c0f1
Revises: 0018
Create Date: 2026-05-01 12:19:40.101190

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f96bbf15c0f1"
down_revision: Union[str, Sequence[str], None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_appointments_source", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_source",
        "appointments",
        "source IN ('client_request', 'master_manual', 'salon_manual', 'web')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_source", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_source",
        "appointments",
        "source IN ('client_request', 'master_manual', 'salon_manual')",
    )
