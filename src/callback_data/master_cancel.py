from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class MasterCancelCallback(CallbackData, prefix="mca"):
    """Master-initiated cancellation of a future pending/confirmed appointment.

    `ask`     — show the confirmation dialog.
    `confirm` — actually cancel.
    `abort`   — close the confirmation without cancelling.
    """

    action: Literal["ask", "confirm", "abort"]
    appointment_id: UUID
