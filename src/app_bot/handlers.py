# ruff: noqa: RUF001
from __future__ import annotations

import structlog
from aiogram import Bot, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from src.config import settings

router = Router(name="app_bot")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_WEB_APP_URL = "https://app.jampord.am"


def _menu_label_for(lang_code: str | None) -> str:
    """Pick the menu-button text for this user based on their Telegram
    language_code. Armenian → Armenian, everyone else → Russian (the
    product's primary non-Armenian market).
    """
    if (lang_code or "").lower().startswith("hy"):
        return "Հավելված"
    return "Приложение"


def _inline_label_for(lang_code: str | None) -> str:
    """CTA-style label for the inline WebApp button under the welcome
    message. Armenian → verb `Գրանցվել`, else Russian `Записаться`.
    """
    if (lang_code or "").lower().startswith("hy"):
        return "Գրանցվել"
    return "Записаться"


def _launch_kb(start_param: str | None, lang_code: str | None) -> InlineKeyboardMarkup:
    url = _WEB_APP_URL
    if start_param:
        url = f"{_WEB_APP_URL}?tgWebAppStartParam={start_param}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_inline_label_for(lang_code), web_app=WebAppInfo(url=url))]
        ]
    )


@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot: Bot,
    command: CommandObject | None = None,
) -> None:
    """Reply with a single WebApp-launcher button.

    The `/start <payload>` argument (e.g. `master_anna-1234` or `salon_foo`)
    is forwarded to the TMA as `tgWebAppStartParam` so the frontend can route
    the user directly to the intended master/salon page on open.

    Side effect: overrides the menu-button label for this specific chat to
    match the user's language_code — ru users see `Приложение`, hy users
    see `Հավելված`. Errors are logged but never bubble up.
    """
    start_param = command.args if command and command.args else None
    log.info(
        "app_bot_start",
        tg_id=message.from_user.id if message.from_user else None,
        start_param=start_param,
    )
    lang_code = (
        getattr(message.from_user, "language_code", None) if message.from_user is not None else None
    )
    is_hy = (lang_code or "").lower().startswith("hy")
    if is_hy:
        text = (
            "Բացիր գրանցումը մի քանի թափով։\n\n"
            if not start_param
            else "Բաց հավելվածը շարունակելու համար։\n\n"
        )
    else:
        text = (
            "Открой запись в пару тапов.\n\n"
            if not start_param
            else "Открой приложение, чтобы продолжить запись.\n\n"
        )
    _ = settings  # reference kept for future per-env URL config
    await message.answer(text, reply_markup=_launch_kb(start_param, lang_code))

    # Per-user menu button localization — only the chat this /start
    # came from is affected; other users keep seeing whatever default
    # was set bot-wide.
    if message.chat is not None:
        label = _menu_label_for(lang_code)
        try:
            await bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(text=label, web_app=WebAppInfo(url=_WEB_APP_URL)),
            )
        except Exception as exc:
            log.warning("set_chat_menu_button_failed", err=repr(exc))
