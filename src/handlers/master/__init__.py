from __future__ import annotations

from aiogram import Router

from src.handlers.master.menu import router as menu_router
from src.handlers.master.services import router as services_router
from src.handlers.master.settings import router as settings_router
from src.handlers.master.start import router as start_router

router = Router(name="master")
router.include_router(start_router)
router.include_router(menu_router)
router.include_router(services_router)
router.include_router(settings_router)

__all__ = ["router"]
