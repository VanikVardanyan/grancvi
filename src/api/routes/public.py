from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import PublicSlugOut
from src.db.models import Master, Salon

router = APIRouter(prefix="/v1/public", tags=["public"])


@router.get("/by-slug/{slug}", response_model=PublicSlugOut)
async def by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> PublicSlugOut:
    """Resolve a short URL slug to a master or salon.

    Used by the grancvi.am/<slug> smart-redirect lander: it calls this
    endpoint, decides whether to deep-link into the TMA as
    `master_<slug>` or `salon_<slug>`, and uses the returned profile
    fields to render a fallback card when Telegram isn't available.
    """
    master = await session.scalar(select(Master).where(Master.slug == slug))
    if master is not None:
        return PublicSlugOut(
            kind="master",
            slug=master.slug,
            name=master.name,
            specialty=master.specialty_text or None,
            phone=master.phone if master.phone_public else None,
            is_public=master.is_public,
        )
    salon = await session.scalar(select(Salon).where(Salon.slug == slug))
    if salon is not None:
        return PublicSlugOut(
            kind="salon",
            slug=salon.slug,
            name=salon.name,
            is_public=salon.is_public,
        )
    raise ApiError("not_found", "slug not found", status_code=404)
