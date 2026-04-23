from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.callback_data.approval import ApprovalCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Service
from src.keyboards.slots import approval_kb, confirm_kb, services_pick_kb, slots_grid

YEREVAN = ZoneInfo("Asia/Yerevan")


def test_slots_grid_three_per_row_with_hhmm_labels() -> None:
    slots = [
        datetime(2026, 5, 4, 10, 0, tzinfo=YEREVAN),
        datetime(2026, 5, 4, 11, 0, tzinfo=YEREVAN),
        datetime(2026, 5, 4, 12, 0, tzinfo=YEREVAN),
        datetime(2026, 5, 4, 13, 0, tzinfo=YEREVAN),
    ]
    kb = slots_grid(slots, tz=YEREVAN)
    # 2 rows of slots + 1 row for "back" = 3 rows.
    assert len(kb.inline_keyboard) == 3
    assert len(kb.inline_keyboard[0]) == 3
    assert len(kb.inline_keyboard[1]) == 1  # trailing row has only one slot
    assert kb.inline_keyboard[0][0].text == "10:00"
    restored = SlotCallback.unpack(kb.inline_keyboard[0][0].callback_data)
    assert (restored.hour, restored.minute) == (10, 0)
    # Last row is the back button.
    assert kb.inline_keyboard[-1][0].callback_data == "client_back"


def test_confirm_kb_has_confirm_and_cancel() -> None:
    kb = confirm_kb()
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "✅ Подтвердить" in texts
    assert "❌ Отменить" in texts


def test_services_pick_kb_packs_service_ids() -> None:
    s1 = Service(id=uuid4(), master_id=uuid4(), name="Стрижка", duration_min=60)
    s2 = Service(id=uuid4(), master_id=uuid4(), name="Маникюр", duration_min=45)
    kb = services_pick_kb([s1, s2])
    assert len(kb.inline_keyboard) == 2
    first = kb.inline_keyboard[0][0]
    restored = ClientServicePick.unpack(first.callback_data)
    assert restored.service_id == s1.id
    assert first.text == "Стрижка"


def test_approval_kb_has_three_buttons() -> None:
    appt_id = uuid4()
    kb = approval_kb(appt_id)
    buttons = [b for row in kb.inline_keyboard for b in row]
    actions = set()
    for b in buttons:
        actions.add(ApprovalCallback.unpack(b.callback_data).action)
    assert actions == {"confirm", "reject", "history"}
