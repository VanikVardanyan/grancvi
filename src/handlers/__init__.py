from __future__ import annotations

from aiogram import Router

from src.handlers.admin import router as admin_router
from src.handlers.client import router as client_router
from src.handlers.master import router as master_router
from src.handlers.salon import router as salon_router


def build_root_router() -> Router:
    root = Router(name="root")
    root.include_router(admin_router)  # admin first — scoped by is_admin
    root.include_router(master_router)
    root.include_router(salon_router)
    root.include_router(client_router)
    return root


__all__ = ["build_root_router"]
