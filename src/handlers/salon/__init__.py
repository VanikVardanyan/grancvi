from __future__ import annotations

from aiogram import Router

from src.handlers.salon.start import router as start_router

router = Router(name="salon")
router.include_router(start_router)

__all__ = ["router"]
