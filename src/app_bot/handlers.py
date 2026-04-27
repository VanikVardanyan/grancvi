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
from src.utils.analytics import track_event

router = Router(name="app_bot")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_WEB_APP_URL = settings.tma_url


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
    user_tg_id = message.from_user.id if message.from_user else None
    log.info(
        "app_bot_start",
        tg_id=user_tg_id,
        start_param=start_param,
    )
    if user_tg_id is not None:
        # Categorize the param so the funnel groups «scanned a master QR»
        # vs «came from CTA на лендинге» without dimension explosion.
        if not start_param:
            kind = "direct"
        elif start_param.startswith("master_"):
            kind = "master_link"
        elif start_param.startswith("salon_"):
            kind = "salon_link"
        elif start_param.startswith("invite_"):
            kind = "invite"
        elif start_param == "signup":
            kind = "signup_master"
        elif start_param == "signup-salon":
            kind = "signup_salon"
        else:
            kind = "other"
        track_event(
            user_tg_id,
            "bot_start",
            {"kind": kind, "start_param": start_param or ""},
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

    # Per-user menu-button override: language + bake the current
    # /start payload into the URL so the menu button (next to the
    # input) deep-links to the same place as the inline CTA. Without
    # this, a user tapping the menu button right after a deep link
    # would miss the master/salon they came for; the localStorage
    # "Recent" list only catches that case on the second visit.
    # `/start` without an arg resets the menu URL back to plain root.
    if message.chat is not None:
        label = _menu_label_for(lang_code)
        menu_url = _WEB_APP_URL
        if start_param:
            menu_url = f"{_WEB_APP_URL}?tgWebAppStartParam={start_param}"
        try:
            await bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=MenuButtonWebApp(text=label, web_app=WebAppInfo(url=menu_url)),
            )
        except Exception as exc:
            log.warning("set_chat_menu_button_failed", err=repr(exc))
