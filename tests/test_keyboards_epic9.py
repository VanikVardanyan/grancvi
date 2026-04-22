from __future__ import annotations

from uuid import uuid4

from src.db.models import Master
from src.keyboards.admin import admin_menu, masters_list_kb
from src.keyboards.catalog import catalog_kb
from src.keyboards.registration import slug_confirm_kb, specialty_hints_kb
from src.strings import get_bundle


def test_specialty_hints_has_5_buttons() -> None:
    kb = specialty_hints_kb()
    flat = [btn.text for row in kb.inline_keyboard for btn in row]
    assert len(flat) == 5
    ru = get_bundle("ru")
    assert ru.REGISTER_SPECIALTY_HINT_HAIR in flat
    assert ru.REGISTER_SPECIALTY_HINT_CUSTOM in flat


def test_slug_confirm_has_use_and_change() -> None:
    kb = slug_confirm_kb()
    flat = [btn.text for row in kb.inline_keyboard for btn in row]
    ru = get_bundle("ru")
    assert ru.REGISTER_SLUG_USE_BTN in flat
    assert ru.REGISTER_SLUG_CHANGE_BTN in flat


def test_admin_menu_structure() -> None:
    kb = admin_menu()
    texts = [btn.text for row in kb.keyboard for btn in row]
    ru = get_bundle("ru")
    assert ru.ADMIN_MENU_MASTERS in texts
    assert ru.ADMIN_MENU_STATS in texts
    assert ru.ADMIN_MENU_INVITES in texts
    assert ru.ADMIN_MENU_MODERATION in texts


def test_masters_list_kb_per_master_buttons() -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(tg_id=2, name="B", slug="b-0001")
    m1.id = uuid4()
    m2.id = uuid4()
    kb = masters_list_kb([m1, m2])
    all_btns = [b for row in kb.inline_keyboard for b in row]
    assert len(all_btns) >= 2


def test_catalog_kb_has_button_per_master() -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001", specialty_text="Dentist")
    m1.id = uuid4()
    kb = catalog_kb([m1])
    assert len(kb.inline_keyboard) == 1


def test_catalog_kb_empty_returns_empty_keyboard() -> None:
    kb = catalog_kb([])
    assert kb.inline_keyboard == []
