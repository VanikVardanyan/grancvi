from __future__ import annotations

from aiogram import Router

from src.handlers.master.add_manual import router as add_manual_router
from src.handlers.master.approve import router as approve_router
from src.handlers.master.calendar import router as calendar_router
from src.handlers.master.client_page import router as client_page_router
from src.handlers.master.my_link import router as my_link_router
from src.handlers.master.new_invite import router as new_invite_router
from src.handlers.master.mark_past import router as mark_past_router
from src.handlers.master.menu import router as menu_router
from src.handlers.master.services import router as services_router
from src.handlers.master.settings import router as settings_router
from src.handlers.master.start import router as start_router
from src.handlers.master.today import router as today_router
from src.handlers.master.week import router as week_router

router = Router(name="master")
router.include_router(start_router)
router.include_router(menu_router)
router.include_router(services_router)
router.include_router(settings_router)
router.include_router(approve_router)
router.include_router(add_manual_router)
router.include_router(today_router)
router.include_router(mark_past_router)
router.include_router(week_router)
router.include_router(calendar_router)
router.include_router(client_page_router)
router.include_router(my_link_router)
router.include_router(new_invite_router)

__all__ = ["router"]
