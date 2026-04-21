from __future__ import annotations

from aiogram.fsm.state import State

from src.fsm.master_add import MasterAdd


def test_master_add_has_nine_states() -> None:
    states = [
        MasterAdd.PickingClient,
        MasterAdd.SearchingClient,
        MasterAdd.NewClientName,
        MasterAdd.NewClientPhone,
        MasterAdd.PickingService,
        MasterAdd.PickingDate,
        MasterAdd.PickingSlot,
        MasterAdd.EnteringCustomTime,
        MasterAdd.EnteringComment,
        MasterAdd.Confirming,
    ]
    assert len(states) == 10
    assert all(isinstance(s, State) for s in states)
