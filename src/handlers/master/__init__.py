from __future__ import annotations

from aiogram import Router

from src.handlers.master.start import router as start_router

router = Router(name="master")
router.include_router(start_router)

__all__ = ["router"]
