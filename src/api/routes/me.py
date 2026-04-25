from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_session
from src.api.schemas import MeOut, MeProfileOut
from src.config import settings
from src.db.models import Master, Salon

router = APIRouter(prefix="/v1/me", tags=["me"])


@router.get("", response_model=MeOut)
async def me(
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    """Identify the caller by their Telegram id and return their role.

    Precedence: salon owner → master → client. A tg_id should only match one
    of the two by design (salon registration rejects tg_ids that are masters,
    and vice versa), but if both rows somehow exist the salon view wins
    because that's the higher-privilege role on this account.
    """
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or "")
    is_admin = tg_id in settings.admin_tg_ids

    salon = await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id))
    if salon is not None:
        return MeOut(
            role="salon_owner",
            profile=MeProfileOut(
                tg_id=tg_id,
                first_name=first_name,
                salon_id=salon.id,
                salon_name=salon.name,
                slug=salon.slug,
            ),
            is_admin=is_admin,
        )

    master = await session.scalar(select(Master).where(Master.tg_id == tg_id))
    if master is not None:
        return MeOut(
            role="master",
            profile=MeProfileOut(
                tg_id=tg_id,
                first_name=first_name,
                master_id=master.id,
                master_name=master.name,
                slug=master.slug,
                specialty=master.specialty_text or None,
            ),
            is_admin=is_admin,
            onboarded=master.onboarded_at is not None,
        )

    return MeOut(
        role="client",
        profile=MeProfileOut(tg_id=tg_id, first_name=first_name),
        is_admin=is_admin,
    )
