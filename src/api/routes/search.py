from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas import SearchHitOut, SearchResultOut
from src.db.models import Master, Salon

router = APIRouter(prefix="/v1/search", tags=["search"])


@router.get("", response_model=SearchResultOut)
async def search(
    q: str = Query(..., min_length=2, max_length=64),
    limit: int = Query(default=10, ge=1, le=25),
    session: AsyncSession = Depends(get_session),
) -> SearchResultOut:
    """Case-insensitive substring search over public masters & salons.

    Matches on name OR slug. Blocked / non-public masters are filtered
    out so redirects aren't a back-door discovery path. Results are
    interleaved — salons first for brand-recognition cases, masters
    after, each side capped at `limit`.
    """
    pattern = f"%{q.strip()}%"
    master_stmt = (
        select(Master)
        .where(
            Master.is_public.is_(True),
            Master.blocked_at.is_(None),
            or_(Master.name.ilike(pattern), Master.slug.ilike(pattern)),
        )
        .order_by(Master.name)
        .limit(limit)
    )
    salon_stmt = (
        select(Salon)
        .where(or_(Salon.name.ilike(pattern), Salon.slug.ilike(pattern)))
        .order_by(Salon.name)
        .limit(limit)
    )
    masters = list((await session.scalars(master_stmt)).all())
    salons = list((await session.scalars(salon_stmt)).all())

    hits: list[SearchHitOut] = []
    for s in salons:
        hits.append(SearchHitOut(kind="salon", id=s.id, name=s.name, slug=s.slug))
    for m in masters:
        hits.append(
            SearchHitOut(
                kind="master",
                id=m.id,
                name=m.name,
                slug=m.slug,
                specialty=m.specialty_text or None,
            )
        )
    return SearchResultOut(hits=hits)
