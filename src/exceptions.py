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


class SlugTaken(Exception):
    """Raised when trying to set a slug that already exists."""


class InvalidSlug(Exception):
    """Raised when slug fails regex validation."""


class ReservedSlug(Exception):
    """Raised when slug matches a reserved value (admin, bot, api, ...)."""


class InviteNotFound(Exception):
    """Raised when invite code does not exist."""


class InviteExpired(Exception):
    """Raised when invite exists but is past expires_at."""


class InviteAlreadyUsed(Exception):
    """Raised when invite has used_at set."""


class MasterBlocked(Exception):
    """Raised when a blocked master attempts a master-scope action."""
