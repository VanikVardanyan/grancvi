from __future__ import annotations

from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ClientPickCallback(CallbackData, prefix="cpk"):
    """Row in `/client` search results → open client page."""

    client_id: UUID


class ClientNotesEditCallback(CallbackData, prefix="cne"):
    """Button on client page → enter notes-edit FSM."""

    client_id: UUID


class ClientAddApptCallback(CallbackData, prefix="caa"):
    """Button on client page → enter MasterAdd FSM with client pre-picked."""

    client_id: UUID
