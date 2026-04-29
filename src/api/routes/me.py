from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_session
from src.api.schemas import MeMasterProfileOut, MeOut, MeProfileOut, MeSalonProfileOut
from src.config import settings
from src.db.models import Master, Salon

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
async def me(
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    """Identify the caller by their Telegram id and return their role.

    Both Master and Salon are always queried so dual-role users get both
    profiles populated. Role precedence: master > salon_owner > client.
    """
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or "")
    is_admin = tg_id in settings.admin_tg_ids

    master = await session.scalar(select(Master).where(Master.tg_id == tg_id))
    salon = await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id))

    master_profile = (
        MeMasterProfileOut(
            master_id=master.id,
            name=master.name,
            slug=master.slug,
            specialty=master.specialty_text or None,
            is_public=master.is_public,
        )
        if master is not None
        else None
    )
    salon_profile = (
        MeSalonProfileOut(
            salon_id=salon.id,
            name=salon.name,
            slug=salon.slug,
            is_public=salon.is_public,
        )
        if salon is not None
        else None
    )

    if master is not None:
        role = "master"
    elif salon is not None:
        role = "salon_owner"
    else:
        role = "client"

    if role == "master":
        assert master is not None
        profile = MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            master_id=master.id,
            master_name=master.name,
            slug=master.slug,
            specialty=master.specialty_text or None,
        )
        return MeOut(
            role=role,
            profile=profile,
            master_profile=master_profile,
            salon_profile=salon_profile,
            is_admin=is_admin,
            onboarded=master.onboarded_at is not None,
        )

    if role == "salon_owner":
        assert salon is not None
        profile = MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            salon_id=salon.id,
            salon_name=salon.name,
            slug=salon.slug,
        )
        return MeOut(
            role=role,
            profile=profile,
            master_profile=master_profile,
            salon_profile=salon_profile,
            is_admin=is_admin,
        )

    return MeOut(
        role="client",
        profile=MeProfileOut(tg_id=tg_id, first_name=first_name),
        master_profile=None,
        salon_profile=None,
        is_admin=is_admin,
    )
