from __future__ import annotations

from aiogram.fsm.state import State

from src.fsm.master_register import MasterRegister


def test_new_states_exist() -> None:
    assert isinstance(MasterRegister.waiting_specialty, State)
    assert isinstance(MasterRegister.waiting_slug_confirm, State)
    assert isinstance(MasterRegister.waiting_custom_slug, State)
