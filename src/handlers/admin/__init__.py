from __future__ import annotations

from aiogram import Router

from src.handlers.admin.invites_admin import router as invites_router
from src.handlers.admin.masters import router as masters_router
from src.handlers.admin.menu import router as menu_router
from src.handlers.admin.moderation import router as moderation_router
from src.handlers.admin.stats import router as stats_router

router = Router(name="admin")
router.include_router(menu_router)
router.include_router(masters_router)
router.include_router(stats_router)
router.include_router(invites_router)
router.include_router(moderation_router)

__all__ = ["router"]
