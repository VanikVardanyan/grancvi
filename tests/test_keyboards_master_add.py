from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.db.models import Client
from src.keyboards.master_add import (
    client_cancel_kb,
    confirm_add_kb,
    phone_dup_kb,
    recent_clients_kb,
    search_results_kb,
    skip_comment_kb,
    slots_grid_with_custom,
)


def _client(name: str, phone: str) -> Client:
    c = Client(master_id=uuid4(), name=name, phone=phone)
    c.id = uuid4()
    return c


def test_recent_clients_kb_has_new_and_search_row() -> None:
    kb = recent_clients_kb([_client("Anna", "+37499111111"), _client("Bob", "+37499222222")])
    # 2 client rows + 1 trailing row with search and new buttons
    assert len(kb.inline_keyboard) == 3
    last = kb.inline_keyboard[-1]
    assert len(last) == 2
    texts = [b.text for b in last]
    assert any("Поиск" in t for t in texts)
    assert any("Новый" in t for t in texts)


def test_recent_clients_kb_empty_just_control_row() -> None:
    kb = recent_clients_kb([])
    assert len(kb.inline_keyboard) == 1


def test_search_results_kb_has_cancel_row() -> None:
    kb = search_results_kb([_client("Anna", "+37499111111")])
    # client row + cancel search row
    assert len(kb.inline_keyboard) == 2
    assert "Отмена" in kb.inline_keyboard[-1][0].text


def test_phone_dup_kb_two_buttons() -> None:
    kb = phone_dup_kb(uuid4())
    assert len(kb.inline_keyboard) == 2
    assert all(len(row) == 1 for row in kb.inline_keyboard)


def test_slots_grid_with_custom_trailing_row() -> None:
    tz = ZoneInfo("Asia/Yerevan")
    slots = [datetime(2026, 5, 4, h, 0, tzinfo=UTC) for h in (6, 7, 8, 9)]
    kb = slots_grid_with_custom(slots, tz=tz)
    # 4 slots -> 2 rows (3+1) + 1 trailing control row
    assert len(kb.inline_keyboard) == 3
    control = kb.inline_keyboard[-1]
    assert len(control) == 2


def test_skip_comment_kb_one_button() -> None:
    kb = skip_comment_kb()
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 1


def test_confirm_add_kb_two_buttons() -> None:
    kb = confirm_add_kb()
    # two buttons — implementation free to use either one row or two
    flat = [b for row in kb.inline_keyboard for b in row]
    assert len(flat) == 2


def test_client_cancel_kb_one_button() -> None:
    kb = client_cancel_kb(uuid4())
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 1
