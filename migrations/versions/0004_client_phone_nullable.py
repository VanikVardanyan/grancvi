"""make clients.phone nullable for anonymous walk-ins

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("clients", "phone", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("clients", "phone", existing_type=sa.Text(), nullable=False)
