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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.utils.analytics import track_event

router = Router(name="app_bot")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_WEB_APP_URL = settings.tma_url


def _menu_label_for(lang: str) -> str:
    """Pick the menu-button text from the resolved lang. Driven by the
    user's stored preference (or Armenian default), NOT by Telegram
    language_code — see `_resolve_lang_default`.
    """
    if lang == "hy":
        return "Հավելված"
    if lang == "en":
        return "App"
    return "Приложение"


_INLINE_LABELS: dict[tuple[str, str], str] = {
    # (lang, kind) → label.  kind ∈ {"signup", "signup-salon", "invite",
    # "master_link", "salon_link", "default"}
    ("hy", "signup"): "Դառնալ վարպետ",
    ("ru", "signup"): "Стать мастером",
    ("en", "signup"): "Become a master",
    ("hy", "signup-salon"): "Գրանցել սրահ",
    ("ru", "signup-salon"): "Зарегистрировать салон",
    ("en", "signup-salon"): "Register a salon",
    ("hy", "invite"): "Ընդունել հրավերը",
    ("ru", "invite"): "Принять приглашение",
    ("en", "invite"): "Accept invite",
    ("hy", "master_link"): "Գրանցվել",
    ("ru", "master_link"): "Записаться",
    ("en", "master_link"): "Book",
    ("hy", "salon_link"): "Գրանցվել",
    ("ru", "salon_link"): "Записаться",
    ("en", "salon_link"): "Book",
    ("hy", "link"): "Բացել իմ գրանցումը",
    ("ru", "link"): "Открыть мою запись",
    ("en", "link"): "Open my booking",
    ("hy", "default"): "Բացել",
    ("ru", "default"): "Открыть",
    ("en", "default"): "Open",
}


_WELCOME_TEXTS: dict[tuple[str, str], str] = {
    ("hy", "default"): "Բացիր Grancvi-ն.",
    ("ru", "default"): "Открой Grancvi.",
    ("en", "default"): "Open Grancvi.",
    ("hy", "signup"): "Վարպետի գրանցում՝ մի քանի քայլով.",
    ("ru", "signup"): "Регистрация мастера — пара тапов.",
    ("en", "signup"): "Master registration — a couple of taps.",
    ("hy", "signup-salon"): "Սրահի գրանցում՝ մի քանի քայլով.",
    ("ru", "signup-salon"): "Регистрация салона — пара тапов.",
    ("en", "signup-salon"): "Salon registration — a couple of taps.",
    ("hy", "invite"): "Բացիր հավելվածը՝ հրավերն ընդունելու համար.",
    ("ru", "invite"): "Открой приложение чтобы принять приглашение.",
    ("en", "invite"): "Open the app to accept the invite.",
    ("hy", "master_link"): "Բացիր հավելվածը՝ գրանցվելու համար.",
    ("ru", "master_link"): "Открой приложение чтобы записаться.",
    ("en", "master_link"): "Open the app to book.",
    ("hy", "salon_link"): "Բացիր հավելվածը՝ գրանցվելու համար.",
    ("ru", "salon_link"): "Открой приложение чтобы записаться.",
    ("en", "salon_link"): "Open the app to book.",
    ("hy", "link"): "Բացիր հավելվածը՝ քո գրանցումը տեսնելու համար.",
    ("ru", "link"): "Открой приложение, чтобы увидеть свою запись.",
    ("en", "link"): "Open the app to see your booking.",
}


def _kind_for(start_param: str | None) -> str:
    if not start_param:
        return "default"
    if start_param == "signup":
        return "signup"
    if start_param == "signup-salon":
        return "signup-salon"
    if start_param.startswith("invite_"):
        return "invite"
    if start_param.startswith("master_"):
        return "master_link"
    if start_param.startswith("salon_"):
        return "salon_link"
    if start_param.startswith("link_"):
        return "link"
    return "default"


def _inline_label_for(start_param: str | None, lang: str) -> str:
    """CTA-style label for the inline WebApp button. Driven by
    (start_param kind, resolved lang).
    """
    kind = _kind_for(start_param)
    return _INLINE_LABELS.get((lang, kind), _INLINE_LABELS[(lang, "default")])


def _welcome_text_for(start_param: str | None, lang: str) -> str:
    """Welcome text shown above the launcher button."""
    kind = _kind_for(start_param)
    return _WELCOME_TEXTS.get((lang, kind), _WELCOME_TEXTS[(lang, "default")])


def _resolve_lang_default(saved_lang: str | None) -> str:
    """Pick the lang for messages BEFORE the user has picked one in
    the TMA: armenian-first. Saved preference (Master.lang) overrides.
    Telegram language_code is intentionally NOT consulted — it biased
    non-Armenian Telegrams toward Russian.
    """
    if saved_lang in ("ru", "hy", "en"):
        return saved_lang
    return "hy"


async def _lookup_saved_lang(session: AsyncSession | None, tg_id: int) -> str | None:
    """Best-effort lookup of the user's last-used lang from the masters
    table. Returns None if the user is not yet a master, or session is
    unavailable.
    """
    if session is None:
        return None
    from src.db.models import Master  # local import to avoid circular

    result: str | None = await session.scalar(select(Master.lang).where(Master.tg_id == tg_id))
    return result


def _launch_kb(start_param: str | None, lang: str) -> InlineKeyboardMarkup:
    url = _WEB_APP_URL
    if start_param:
        url = f"{_WEB_APP_URL}?tgWebAppStartParam={start_param}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_inline_label_for(start_param, lang),
                    web_app=WebAppInfo(url=url),
                )
            ]
        ]
    )


@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    """Reply with a single WebApp-launcher button.

    The `/start <payload>` argument (e.g. `master_anna-1234` or `salon_foo`)
    is forwarded to the TMA as `tgWebAppStartParam` so the frontend can route
    the user directly to the intended master/salon page on open.

    Side effect: overrides the menu-button label for this specific chat to
    match the resolved lang — ru users see `Приложение`, hy users see
    `Հավելված`. Errors are logged but never bubble up.
    """
    start_param = command.args if command and command.args else None
    user_tg_id = message.from_user.id if message.from_user else None
    log.info(
        "app_bot_start",
        tg_id=user_tg_id,
        start_param=start_param,
    )
    # Web-booking opt-in: bind tg_id to Client by one-shot token. The
    # token came from the /v1/public/bookings response; tapping the
    # success-page button opens this bot with start=link_<token>. We
    # set Client.tg_id so future reminders go via Telegram and the
    # appointment shows up in the TMA's MyBookings.
    if start_param and start_param.startswith("link_"):
        from src.db.models import Client as ClientModel

        token = start_param[len("link_") :]
        if token and user_tg_id is not None:
            client = await session.scalar(
                select(ClientModel).where(ClientModel.link_token == token)
            )
            if client is not None and (client.tg_id is None or client.tg_id == user_tg_id):
                client.tg_id = user_tg_id
                client.link_token = None
                await session.commit()
                log.info("link_token_bound", tg_id=user_tg_id, client_id=str(client.id))
            elif client is not None:
                log.warning("link_token_owned_by_another", tg_id=user_tg_id, owner=client.tg_id)
            # If token not found in DB — silently ignore; user still
            # gets the standard welcome flow + inline button below.

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
        elif start_param.startswith("link_"):
            kind = "web_booking_link"
        else:
            kind = "other"
        track_event(
            user_tg_id,
            "bot_start",
            {"kind": kind, "start_param": start_param or ""},
        )
    saved_lang = await _lookup_saved_lang(session, user_tg_id) if user_tg_id is not None else None
    lang = _resolve_lang_default(saved_lang)
    text = _welcome_text_for(start_param, lang)
    _ = settings  # reference kept for future per-env URL config
    await message.answer(text, reply_markup=_launch_kb(start_param, lang))

    # Per-user menu-button override: language + bake the current
    # /start payload into the URL so the menu button (next to the
    # input) deep-links to the same place as the inline CTA. Without
    # this, a user tapping the menu button right after a deep link
    # would miss the master/salon they came for; the localStorage
    # "Recent" list only catches that case on the second visit.
    # `/start` without an arg resets the menu URL back to plain root.
    if message.chat is not None:
        label = _menu_label_for(lang)
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
