from __future__ import annotations

from src.fsm.master_view import MasterView


def test_states_exist() -> None:
    assert MasterView.SearchingClient.state is not None
    assert MasterView.EditingNotes.state is not None
    assert MasterView.SearchingClient.state != MasterView.EditingNotes.state
