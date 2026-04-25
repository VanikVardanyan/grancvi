"""specialties table — move profession list out of frontend code

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-25 23:00:00.000000

Until now SPECIALTY_CODES + i18n labels lived in src/lib/specialties.ts
and src/lib/i18n.ts on the frontend. Adding a profession required a
code edit + redeploy. Moves the canonical list to a DB table so admins
can CRUD via /admin without touching code. Service presets stay in code
for now — separate refactor.

masters.specialty_text continues to store comma-separated codes; this
migration adds nothing to that column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEED: list[tuple[str, str, str, int]] = [
    ("hairdresser_women", "Парикмахер (женский)", "Վարսահարդար (կանացի)", 10),
    ("hairdresser_men", "Парикмахер (мужской)", "Վարսահարդար (տղամարդու)", 20),
    ("hairdresser_uni", "Парикмахер (универсал)", "Վարսահարդար (համընդհանուր)", 30),
    ("barber", "Барбер", "Բարբեր", 40),
    ("colorist", "Колорист", "Կոլորիստ", 50),
    ("nails_manicure", "Мастер маникюра", "Մանիկյուրի վարպետ", 60),
    ("nails_pedicure", "Мастер педикюра", "Պեդիկյուրի վարպետ", 70),
    ("brows", "Бровист", "Հոնքերի վարպետ", 80),
    ("lashes", "Лэшмейкер", "Թարթիչների վարպետ", 90),
    ("makeup", "Визажист", "Վիզաժիստ", 100),
    ("cosmetology", "Косметолог", "Կոսմետոլոգ", 110),
    ("massage", "Массажист", "Մերսող", 120),
    ("depilation", "Депиляция / эпиляция", "Դեպիլյացիա / էպիլյացիա", 130),
    ("dentist", "Стоматолог", "Ատամնաբույժ", 140),
    ("other", "Другое", "Այլ", 999),
]


def upgrade() -> None:
    op.create_table(
        "specialties",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name_ru", sa.Text, nullable=False),
        sa.Column("name_hy", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    bind = op.get_bind()
    for code, ru, hy, pos in SEED:
        bind.execute(
            sa.text(
                "INSERT INTO specialties (code, name_ru, name_hy, position) "
                "VALUES (:code, :ru, :hy, :pos) ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "ru": ru, "hy": hy, "pos": pos},
        )


def downgrade() -> None:
    op.drop_table("specialties")
