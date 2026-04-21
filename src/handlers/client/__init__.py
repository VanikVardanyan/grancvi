from __future__ import annotations

from aiogram import Router

from src.handlers.client.booking import router as booking_router
from src.handlers.client.start import router as start_router

router = Router(name="client")
router.include_router(start_router)
router.include_router(booking_router)

__all__ = ["router"]
