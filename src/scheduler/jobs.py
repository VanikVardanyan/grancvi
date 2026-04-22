from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.repositories.reminders import ReminderRepository
from src.strings import strings
from src.utils.time import now_utc

log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _format_reminder(
    reminder: Reminder,
    master: Master,
    client: Client,
    service: Service,
    appointment: Appointment,
) -> tuple[int, str] | None:
    """Return (chat_id, text) or None if the target chat is unreachable.

    Client-side kinds require `client.tg_id` — master-added phone-only clients
    have no Telegram link, so those reminders are skipped.
    """
    tz = ZoneInfo(master.timezone)
    local = appointment.start_at.astimezone(tz)
    time_s = local.strftime("%H:%M")

    if reminder.kind == "day_before":
        if client.tg_id is None:
            return None
        return client.tg_id, strings.REMINDER_CLIENT_DAY_BEFORE.format(
            time=time_s, service=service.name
        )
    if reminder.kind == "two_hours":
        if client.tg_id is None:
            return None
        return client.tg_id, strings.REMINDER_CLIENT_TWO_HOURS.format(
            time=time_s, service=service.name
        )
    if reminder.kind == "master_before":
        return master.tg_id, strings.REMINDER_MASTER_BEFORE.format(
            time=time_s,
            service=service.name,
            client_name=client.name,
            phone=client.phone or "",
        )
    raise ValueError(f"unknown reminder kind: {reminder.kind!r}")


async def send_due_reminders(
    *,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime | None = None,
) -> None:
    """One-tick worker: pick due reminders and send them.

    FOR UPDATE SKIP LOCKED makes concurrent ticks safe. If appointment.status
    is not 'confirmed', the reminder is marked sent without firing (lazy
    cleanup). TelegramBadRequest / TelegramForbiddenError also mark sent
    (don't retry dead chats forever). TelegramRetryAfter leaves sent=false
    so the next tick retries. Any other exception is logged and left unsent.
    """
    n = now if now is not None else now_utc()
    async with session_factory() as session:
        repo = ReminderRepository(session)
        rows = await repo.get_due_for_update(now=n, limit=100)

        for reminder, appointment, master, client, service in rows:
            if appointment.status != "confirmed":
                await repo.mark_sent(reminder.id, sent_at=n)
                continue

            formatted = _format_reminder(reminder, master, client, service, appointment)
            if formatted is None:
                await repo.mark_sent(reminder.id, sent_at=n)
                continue
            chat_id, text = formatted
            try:
                await bot.send_message(chat_id=chat_id, text=text)
            except TelegramRetryAfter as exc:
                log.warning(
                    "reminder_retry_after",
                    reminder_id=str(reminder.id),
                    retry_after=exc.retry_after,
                )
                continue
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                log.warning(
                    "reminder_dead_chat",
                    reminder_id=str(reminder.id),
                    chat_id=chat_id,
                    error=repr(exc),
                )
                await repo.mark_sent(reminder.id, sent_at=n)
                continue
            except Exception as exc:
                log.error(
                    "reminder_send_failed",
                    reminder_id=str(reminder.id),
                    error=repr(exc),
                )
                continue

            await repo.mark_sent(reminder.id, sent_at=n)

        await session.commit()
