from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.exceptions import InviteNotFound, SlugTaken
from src.services.master_registration import MasterRegistrationService


@pytest.mark.asyncio
async def test_register_happy_path(session: AsyncSession) -> None:
    inv = Invite(
        code="REG-0001",
        created_by_tg_id=1,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add(inv)
    await session.commit()

    svc = MasterRegistrationService(session)
    master = await svc.register(
        tg_id=500001,
        name="Арам",
        specialty="Стоматолог",
        slug="aram-test",
        lang="ru",
        invite_code="REG-0001",
    )
    await session.commit()
    assert master.tg_id == 500001 and master.slug == "aram-test"
    assert master.specialty_text == "Стоматолог"
    await session.refresh(inv)
    assert inv.used_by_tg_id == 500001


@pytest.mark.asyncio
async def test_register_rejects_invalid_invite(session: AsyncSession) -> None:
    svc = MasterRegistrationService(session)
    with pytest.raises(InviteNotFound):
        await svc.register(
            tg_id=500002,
            name="X",
            specialty="",
            slug="x-xxxx",
            lang="ru",
            invite_code="MISSING",
        )


@pytest.mark.asyncio
async def test_register_rejects_taken_slug(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="taken-0001")
    inv = Invite(
        code="REG-TK01",
        created_by_tg_id=1,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    session.add_all([m, inv])
    await session.commit()

    svc = MasterRegistrationService(session)
    with pytest.raises(SlugTaken):
        await svc.register(
            tg_id=999,
            name="New",
            specialty="",
            slug="taken-0001",
            lang="ru",
            invite_code="REG-TK01",
        )


@pytest.mark.asyncio
async def test_register_self_master_is_public_immediately(session: AsyncSession) -> None:
    """Self-service registration must NOT land on moderation. is_public=True from creation."""
    svc = MasterRegistrationService(session)
    master = await svc.register_self(
        tg_id=99001,
        name="Anna Test",
        specialty="hairdresser_women",
        slug="anna-test-public",
        lang="hy",
    )
    assert master.is_public is True, "self-service registration must skip moderation"


@pytest.mark.asyncio
async def test_register_self_master_marked_onboarded(session: AsyncSession) -> None:
    """register_self must set onboarded_at — there's no separate Onboarding wizard anymore."""
    svc = MasterRegistrationService(session)
    master = await svc.register_self(
        tg_id=99002,
        name="Hayk Test",
        specialty="barber",
        slug="hayk-test-onb",
        lang="hy",
    )
    assert master.onboarded_at is not None, "register_self must auto-set onboarded_at"
