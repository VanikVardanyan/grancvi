"""epic 10.1: salons table + enum extensions

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-23 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salons",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_tg_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(32), nullable=False, unique=True),
        sa.Column("logo_file_id", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("blocked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.add_column(
        "masters",
        sa.Column(
            "salon_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_masters_salon_id", "masters", ["salon_id"])

    op.add_column(
        "invites",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'master'"),
        ),
    )
    op.add_column(
        "invites",
        sa.Column(
            "salon_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_invites_kind",
        "invites",
        "kind IN ('master', 'salon_owner')",
    )

    op.drop_constraint("ck_appointments_source", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_source",
        "appointments",
        "source IN ('client_request', 'master_manual', 'salon_manual')",
    )
    op.drop_constraint("ck_appointments_cancelled_by", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_cancelled_by",
        "appointments",
        "cancelled_by IS NULL OR cancelled_by IN ('client', 'master', 'system', 'salon')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_cancelled_by", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_cancelled_by",
        "appointments",
        "cancelled_by IS NULL OR cancelled_by IN ('client', 'master', 'system')",
    )
    op.drop_constraint("ck_appointments_source", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_source",
        "appointments",
        "source IN ('client_request', 'master_manual')",
    )
    op.drop_constraint("ck_invites_kind", "invites", type_="check")
    op.drop_column("invites", "salon_id")
    op.drop_column("invites", "kind")
    op.drop_index("ix_masters_salon_id", table_name="masters")
    op.drop_column("masters", "salon_id")
    op.drop_table("salons")
