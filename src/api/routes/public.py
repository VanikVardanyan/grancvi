from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import PublicSlugOut
from src.db.models import Master, Salon, Specialty

router = APIRouter(prefix="/v1/public", tags=["public"])


async def _resolve_specialty_text(
    session: AsyncSession, raw: str | None, lang: str
) -> str | None:
    """Convert a comma-separated mix of specialty codes and free-form
    text into a single human-readable string in `lang` (ru/hy).

    The masters.specialty_text field stores whatever the master picked
    in the profile UI: any combination of canonical codes
    (`hairdresser_women`) and free text (`Колорист`). Codes resolve via
    the specialties table; non-codes pass through unchanged so a
    master's custom specialty isn't dropped on the floor.
    """
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    codes = {p for p in parts if p.replace("_", "").isalnum() and p.islower()}
    name_map: dict[str, str] = {}
    if codes:
        rows = await session.scalars(select(Specialty).where(Specialty.code.in_(codes)))
        for s in rows.all():
            name_map[s.code] = s.name_hy if lang == "hy" else s.name_ru
    pretty = [name_map.get(p, p) for p in parts]
    return ", ".join(pretty)


@router.get("/by-slug/{slug}", response_model=PublicSlugOut)
async def by_slug(
    slug: str,
    lang: str = Query("ru", pattern="^(ru|hy)$"),
    session: AsyncSession = Depends(get_session),
) -> PublicSlugOut:
    """Resolve a short URL slug to a master or salon.

    Used by the grancvi.am/<slug> smart-redirect lander: it calls this
    endpoint, decides whether to deep-link into the TMA as
    `master_<slug>` or `salon_<slug>`, and uses the returned profile
    fields to render a fallback card when Telegram isn't available.

    `lang` controls how `specialty` is rendered — codes get translated
    via the specialties table; the lander passes the user's UI lang.
    """
    master = await session.scalar(select(Master).where(Master.slug == slug))
    if master is not None:
        return PublicSlugOut(
            kind="master",
            slug=master.slug,
            name=master.name,
            specialty=await _resolve_specialty_text(session, master.specialty_text, lang),
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
