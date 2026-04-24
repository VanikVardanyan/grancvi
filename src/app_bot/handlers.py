from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from src.config import settings

router = Router(name="app_bot")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_WEB_APP_URL = "https://app.jampord.am"


def _launch_kb(start_param: str | None) -> InlineKeyboardMarkup:
    url = _WEB_APP_URL
    if start_param:
        url = f"{_WEB_APP_URL}?tgWebAppStartParam={start_param}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Գրանցվել", web_app=WebAppInfo(url=url))]
        ]
    )


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject | None = None,
) -> None:
    """Reply with a single WebApp-launcher button.

    The `/start <payload>` argument (e.g. `master_anna-1234` or `salon_foo`)
    is forwarded to the TMA as `tgWebAppStartParam` so the frontend can route
    the user directly to the intended master/salon page on open.
    """
    start_param = command.args if command and command.args else None
    log.info(
        "app_bot_start",
        tg_id=message.from_user.id if message.from_user else None,
        start_param=start_param,
    )
    text = (
        "Открой запись в пару тапов.\n\n"
        if not start_param
        else "Открой приложение, чтобы продолжить запись.\n\n"
    )
    _ = settings  # reference kept for future per-env URL config
    await message.answer(text, reply_markup=_launch_kb(start_param))
