from __future__ import annotations

from aiogram import Router

from src.handlers.master import router as master_router


def build_root_router() -> Router:
    root = Router(name="root")
    root.include_router(master_router)
    return root


__all__ = ["build_root_router"]
