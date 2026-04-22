from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master
from src.strings import strings

router = Router(name="admin_stats")


async def cmd_admin_stats(*, message: Message, session: AsyncSession) -> None:
    now = datetime.now(UTC)

    masters_active = (
        await session.scalar(select(func.count(Master.id)).where(Master.blocked_at.is_(None))) or 0
    )
    masters_blocked = (
        await session.scalar(select(func.count(Master.id)).where(Master.blocked_at.is_not(None)))
        or 0
    )
    clients_distinct = (
        await session.scalar(
            select(func.count(distinct(Client.tg_id))).where(Client.tg_id.is_not(None))
        )
        or 0
    )
    appt_7d = (
        await session.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.created_at >= now - timedelta(days=7)
            )
        )
        or 0
    )
    appt_30d = (
        await session.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.created_at >= now - timedelta(days=30)
            )
        )
        or 0
    )

    await message.answer(
        strings.ADMIN_STATS_FMT.format(
            masters_active=masters_active,
            masters_blocked=masters_blocked,
            clients=clients_distinct,
            appt_7d=appt_7d,
            appt_30d=appt_30d,
        )
    )


@router.message(Command("stats"))
async def handle_stats_cmd(message: Message, session: AsyncSession, is_admin: bool = False) -> None:
    if not is_admin:
        return
    await cmd_admin_stats(message=message, session=session)
