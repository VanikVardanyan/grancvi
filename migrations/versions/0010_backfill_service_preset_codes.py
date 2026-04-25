"""backfill services.preset_code from existing names

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-25 13:00:00.000000

Existing services were typed in one language by the master before the
preset_code column existed; the booking UI couldn't switch their labels
to the client's language. This migration walks every row and, if the
trimmed `name` (case-insensitive) matches one of the SERVICE_PRESETS
entries (RU or HY), stamps the corresponding code.

Custom-named services stay untouched.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror of grancvi-web/src/lib/specialties.ts SERVICE_PRESETS.
# Each tuple is (preset_code, ru_name, hy_name). When the same code
# repeats across specialties the labels are identical, so deduping by
# code is fine.
_PRESETS: list[tuple[str, str, str]] = [
    ("haircut_women", "Женская стрижка", "Կանացի սանրվածք"),
    ("blowdry", "Укладка", "Հարդարում"),
    ("coloring", "Окрашивание", "Ներկում"),
    ("highlights", "Мелирование", "Մելիրովկա"),
    ("keratin", "Кератиновое выпрямление", "Կերատինային հարդարում"),
    ("trim_ends", "Полировка концов", "Ծայրերի կտրում"),
    ("haircut_men", "Мужская стрижка", "Տղամարդու սանրվածք"),
    ("beard_trim", "Моделирование бороды", "Մորուքի ձևավորում"),
    ("kids_haircut", "Детская стрижка", "Մանկական սանրվածք"),
    ("fade", "Fade", "Fade"),
    ("beard_shape", "Бритьё / моделирование бороды", "Մորուքի ձևավորում"),
    ("hot_towel", "Королевское бритьё", "Արքայական սափրում"),
    ("balayage", "Балаяж", "Բալայաժ"),
    ("shatush", "Шатуш", "Շատուշ"),
    ("root_touchup", "Окрашивание корней", "Արմատների ներկում"),
    ("manicure_classic", "Классический маникюр", "Դասական մանիկյուր"),
    ("manicure_gel", "Маникюр с покрытием гель-лак", "Մանիկյուր գել-լաքով"),
    ("nail_design", "Дизайн ногтей", "Եղունգների դիզայն"),
    ("nail_extensions", "Наращивание ногтей", "Եղունգների երկարացում"),
    ("pedicure_classic", "Классический педикюр", "Դասական պեդիկյուր"),
    ("pedicure_gel", "Педикюр с покрытием гель-лак", "Պեդիկյուր գել-լաքով"),
    ("combo_mani_pedi", "Комбо маникюр + педикюр", "Մանիկյուր + պեդիկյուր"),
    ("brows_shape", "Коррекция бровей", "Հոնքերի շտկում"),
    ("brows_tint", "Окрашивание бровей", "Հոնքերի ներկում"),
    ("brows_lamination", "Ламинирование бровей", "Հոնքերի լամինացիա"),
    ("lash_classic", "Классическое наращивание ресниц", "Դասական թարթիչների երկարացում"),
    ("lash_2d", "Наращивание 2D", "Երկարացում 2D"),
    ("lash_lamination", "Ламинирование ресниц", "Թարթիչների լամինացիա"),
    ("lash_removal", "Снятие ресниц", "Թարթիչների հեռացում"),
    ("makeup_day", "Дневной макияж", "Ցերեկային դիմահարդարում"),
    ("makeup_evening", "Вечерний макияж", "Երեկոյան դիմահարդարում"),
    ("makeup_wedding", "Свадебный макияж", "Հարսանեկան դիմահարդարում"),
    ("facial_cleansing", "Чистка лица", "Դեմքի մաքրում"),
    ("mask_care", "Уходовая процедура", "Խնամքի պրոցեդուրա"),
    ("peel", "Химический пилинг", "Քիմիական պիլինգ"),
    ("consultation", "Консультация", "Խորհրդատվություն"),
    ("massage_classic", "Классический массаж", "Դասական մերսում"),
    ("massage_back", "Массаж спины", "Մեջքի մերսում"),
    ("massage_relax", "Расслабляющий массаж", "Հանգստացնող մերսում"),
    ("massage_sport", "Спортивный массаж", "Սպորտային մերսում"),
    ("wax_legs", "Воск — ноги", "Մոմով՝ ոտքեր"),
    ("wax_bikini", "Воск — бикини", "Մոմով՝ բիկինի"),
    ("wax_armpits", "Воск — подмышки", "Մոմով՝ թևատակեր"),
    ("sugaring", "Шугаринг", "Շաքարավազով"),
    ("checkup", "Осмотр и консультация", "Զննություն և խորհրդատվություն"),
    ("cleaning", "Профессиональная чистка", "Պրոֆեսիոնալ մաքրում"),
    ("filling", "Лечение кариеса", "Կարիեսի բուժում"),
    ("whitening", "Отбеливание", "Սպիտակեցում"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for code, ru, hy in _PRESETS:
        bind.exec_driver_sql(
            "UPDATE services SET preset_code = %(c)s "
            "WHERE preset_code IS NULL "
            "AND (LOWER(TRIM(name)) = LOWER(%(ru)s) OR LOWER(TRIM(name)) = LOWER(%(hy)s))",
            {"c": code, "ru": ru, "hy": hy},
        )


def downgrade() -> None:
    # No-op: preset_code stays populated; reverting would lose information
    # we'd just have to recompute next time we run forward.
    pass
