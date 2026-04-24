from __future__ import annotations

from typing import Any

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def notify_user(
    *,
    app_bot: Bot | None,
    fallback_bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Any = None,
) -> bool:
    """Send a message to a Telegram user — master or client.

    Tries `app_bot` (new @grancviWebBot) first. If the user never opened
    that bot, Telegram replies 403 Forbidden — we silently fall back to
    `fallback_bot` (legacy @GrancviBot). Returns True on any successful
    send.

    Non-Forbidden errors are logged but also trigger the fallback, so a
    transient app-bot failure doesn't lose the notification.
    """
    if app_bot is not None:
        try:
            await app_bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            return True
        except TelegramForbiddenError:
            # Expected for legacy users who never started the new bot.
            pass
        except (TelegramBadRequest, TelegramRetryAfter) as exc:
            log.warning("notify_app_failed", chat_id=chat_id, err=repr(exc))
        except Exception as exc:
            log.warning("notify_app_unexpected", chat_id=chat_id, err=repr(exc))
    try:
        await fallback_bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return True
    except Exception as exc:
        log.warning("notify_failed", chat_id=chat_id, err=repr(exc))
        return False


# Back-compat alias for existing callsites that still import notify_client.
notify_client = notify_user
