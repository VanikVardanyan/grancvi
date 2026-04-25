"""masters.onboarded_at — mark master as having completed first-run setup

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-25 22:00:00.000000

After registration the master goes through a wizard: pick work hours,
add services. The post-wizard call stamps onboarded_at so the dashboard
stops force-redirecting them back into setup. NULL until they finish or
explicitly skip.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column("onboarded_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Existing masters predate the wizard — treat them as already onboarded
    # so they don't get bounced into the flow on next launch.
    op.execute("UPDATE masters SET onboarded_at = now() WHERE onboarded_at IS NULL")


def downgrade() -> None:
    op.drop_column("masters", "onboarded_at")
