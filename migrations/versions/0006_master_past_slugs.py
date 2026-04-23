"""master past_slugs jsonb + slug_changed_at for 30-day rename cooldown

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column(
            "past_slugs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "masters",
        sa.Column(
            "slug_changed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    # GIN index so `past_slugs @> '["old-slug"]'` lookups stay fast even
    # with hundreds of masters — typical query pattern for the
    # redirect path.
    op.create_index(
        "ix_masters_past_slugs_gin",
        "masters",
        ["past_slugs"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_masters_past_slugs_gin", table_name="masters")
    op.drop_column("masters", "slug_changed_at")
    op.drop_column("masters", "past_slugs")
