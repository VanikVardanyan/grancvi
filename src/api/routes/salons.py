from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import SalonPublicMasterOut, SalonPublicOut
from src.db.models import Master, Salon

router = APIRouter(prefix="/v1/salons", tags=["salons"])


@router.get("/by-slug/{slug}", response_model=SalonPublicOut)
async def get_salon_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> SalonPublicOut:
    """Public salon landing — used when a master's redirect points here.

    Returns the salon + its visible masters (public, not blocked) so the
    client can present a picker.
    """
    salon = await session.scalar(select(Salon).where(Salon.slug == slug))
    if salon is None:
        raise ApiError("not_found", "salon not found", status_code=404)

    masters = list(
        (
            await session.scalars(
                select(Master)
                .where(
                    Master.salon_id == salon.id,
                    Master.is_public.is_(True),
                    Master.blocked_at.is_(None),
                )
                .order_by(Master.name)
            )
        ).all()
    )
    return SalonPublicOut(
        id=salon.id,
        name=salon.name,
        slug=salon.slug,
        masters=[
            SalonPublicMasterOut(
                id=m.id,
                name=m.name,
                slug=m.slug,
                specialty=m.specialty_text or "",
            )
            for m in masters
        ],
    )
