from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

log: structlog.stdlib.BoundLogger = structlog.get_logger()


@dataclass(frozen=True)
class SentInfo:
    """Identifies the resulting Telegram message — used by callers that
    need to edit it later (e.g. clear approve/reject buttons after a
    master decision made elsewhere).
    """

    chat_id: int
    message_id: int
    via: Literal["app_bot", "fallback_bot"]


async def notify_user(
    *,
    app_bot: Bot | None,
    fallback_bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Any = None,
) -> SentInfo | None:
    """Send a message to a Telegram user — master or client.

    Tries `app_bot` (new @grancviWebBot) first. If the user never opened
    that bot, Telegram replies 403 Forbidden — we silently fall back to
    `fallback_bot` (legacy @GrancviBot). Returns SentInfo on success
    (chat_id, message_id, which bot delivered) so callers can edit the
    message later, or None if both attempts failed.

    Non-Forbidden errors are logged but also trigger the fallback, so a
    transient app-bot failure doesn't lose the notification.
    """
    if app_bot is not None:
        try:
            msg = await app_bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
            return SentInfo(chat_id=chat_id, message_id=msg.message_id, via="app_bot")
        except TelegramForbiddenError:
            # Expected for legacy users who never started the new bot.
            pass
        except (TelegramBadRequest, TelegramRetryAfter) as exc:
            log.warning("notify_app_failed", chat_id=chat_id, err=repr(exc))
        except Exception as exc:
            log.warning("notify_app_unexpected", chat_id=chat_id, err=repr(exc))
    try:
        msg = await fallback_bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return SentInfo(chat_id=chat_id, message_id=msg.message_id, via="fallback_bot")
    except Exception as exc:
        log.warning("notify_failed", chat_id=chat_id, err=repr(exc))
        return None


async def clear_master_notification(
    *,
    app_bot: Bot | None,
    fallback_bot: Bot,
    chat_id: int | None,
    message_id: int | None,
    via: str | None,
    new_text: str | None = None,
) -> None:
    """Strip the approve/reject keyboard from the master's pending DM.

    Called after a state change made anywhere (TMA or bot callback) so
    the chat message stops showing buttons that re-fire stale flows.
    Optionally rewrites the text to reflect the new status. Silently
    no-ops on missing ids or transient Telegram errors — UI elsewhere
    is the source of truth, this is best-effort cleanup.
    """
    if not chat_id or not message_id or not via:
        return
    bot = app_bot if via == "app_bot" else fallback_bot
    if bot is None:
        return
    try:
        if new_text:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=new_text, reply_markup=None
            )
        else:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
    except Exception as exc:
        log.info("clear_master_notify_failed", chat_id=chat_id, msg_id=message_id, err=repr(exc))


# Back-compat alias for existing callsites that still import notify_client.
notify_client = notify_user
