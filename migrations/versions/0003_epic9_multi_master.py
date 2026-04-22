"""epic 9: multi-master — masters columns + invites table + data migration

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns as nullable first
    op.add_column("masters", sa.Column("slug", sa.String(32), nullable=True))
    op.add_column(
        "masters",
        sa.Column("specialty_text", sa.String(200), nullable=False, server_default=""),
    )
    op.add_column(
        "masters",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "masters",
        sa.Column("blocked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 2. Data migration: generate slug for every existing master
    op.execute(
        """
        UPDATE masters
        SET slug = CONCAT(
            'master-',
            LPAD(TO_HEX((RANDOM() * 16777215)::int), 6, '0')
        )
        WHERE slug IS NULL
        """
    )

    # 3. Make slug NOT NULL and unique
    op.alter_column("masters", "slug", nullable=False)
    op.create_unique_constraint("uq_masters_slug", "masters", ["slug"])

    # 4. Catalog lookup index
    op.create_index(
        "ix_masters_catalog",
        "masters",
        ["is_public", "blocked_at"],
        postgresql_where=sa.text("blocked_at IS NULL AND is_public = true"),
    )

    # 5. Invites table
    op.create_table(
        "invites",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("created_by_tg_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_by_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "used_for_master_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(used_by_tg_id IS NULL) = (used_at IS NULL) "
            "AND (used_at IS NULL) = (used_for_master_id IS NULL)",
            name="ck_invites_usage_tuple",
        ),
    )
    op.create_index("ix_invites_code", "invites", ["code"])
    op.create_index(
        "ix_invites_creator",
        "invites",
        ["created_by_tg_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_invites_creator", table_name="invites")
    op.drop_index("ix_invites_code", table_name="invites")
    op.drop_table("invites")

    op.drop_index("ix_masters_catalog", table_name="masters")
    op.drop_constraint("uq_masters_slug", "masters", type_="unique")
    op.drop_column("masters", "blocked_at")
    op.drop_column("masters", "is_public")
    op.drop_column("masters", "specialty_text")
    op.drop_column("masters", "slug")
