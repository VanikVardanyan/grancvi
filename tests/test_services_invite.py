from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.exceptions import InviteAlreadyUsed, InviteExpired, InviteNotFound
from src.services.invite import InviteService


def test_generate_code_format() -> None:
    code = InviteService.generate_code()
    # Format XXXX-XXXX with alphabet A-Z (no I/O) + digits 2-9
    import re

    assert re.match(r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$", code)


def test_generate_code_unique() -> None:
    seen = {InviteService.generate_code() for _ in range(100)}
    assert len(seen) == 100  # effectively


@pytest.mark.asyncio
async def test_create_invite_persists(session: AsyncSession) -> None:
    svc = InviteService(session)
    invite = await svc.create_invite(actor_tg_id=111)
    await session.commit()
    assert invite.created_by_tg_id == 111
    assert invite.expires_at > datetime.now(UTC) + timedelta(days=6)


@pytest.mark.asyncio
async def test_redeem_success(session: AsyncSession) -> None:
    svc = InviteService(session)
    invite = await svc.create_invite(actor_tg_id=111)
    await session.commit()
    master = Master(tg_id=222, name="Arman", slug="arman-abcd")
    session.add(master)
    await session.flush()
    used = await svc.redeem(code=invite.code, tg_id=222, master_id=master.id)
    await session.commit()
    assert used.used_by_tg_id == 222
    assert used.used_for_master_id == master.id


@pytest.mark.asyncio
async def test_redeem_not_found(session: AsyncSession) -> None:
    svc = InviteService(session)
    with pytest.raises(InviteNotFound):
        await svc.redeem(code="MISSING", tg_id=111, master_id=uuid4())


@pytest.mark.asyncio
async def test_redeem_expired(session: AsyncSession) -> None:
    svc = InviteService(session)
    invite = Invite(
        code="EXP-0001",
        created_by_tg_id=1,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add(invite)
    await session.commit()
    with pytest.raises(InviteExpired):
        await svc.redeem(code="EXP-0001", tg_id=222, master_id=uuid4())


@pytest.mark.asyncio
async def test_redeem_already_used(session: AsyncSession) -> None:
    svc = InviteService(session)
    master = Master(tg_id=333, name="X", slug="x-aaaa")
    session.add(master)
    await session.flush()
    invite = Invite(
        code="USED-0001",
        created_by_tg_id=1,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        used_by_tg_id=333,
        used_for_master_id=master.id,
        used_at=datetime.now(UTC),
    )
    session.add(invite)
    await session.commit()
    with pytest.raises(InviteAlreadyUsed):
        await svc.redeem(code="USED-0001", tg_id=333, master_id=master.id)
