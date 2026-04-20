from __future__ import annotations


class SlotAlreadyTaken(Exception):
    """Raised when the unique partial index rejects a pending/confirmed insert.

    Handlers should respond by re-rendering the current grid of free slots.
    """


class NotFound(Exception):
    """Raised by services when a referenced appointment does not exist."""


class InvalidState(Exception):
    """Raised when an appointment transition is not allowed from its current status.

    Example: trying to confirm an appointment that is already cancelled.
    """
