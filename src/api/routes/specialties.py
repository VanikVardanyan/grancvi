from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.schemas import SpecialtyOut
from src.db.models import Specialty

router = APIRouter(prefix="/v1/specialties", tags=["specialties"])


@router.get("", response_model=list[SpecialtyOut])
async def list_specialties(
    session: AsyncSession = Depends(get_session),
) -> list[SpecialtyOut]:
    """Public list of professions for the register form. Ordered by
    `position` (manual sort, lower first), then by name_ru as a tie
    breaker.
    """
    rows = (
        await session.scalars(select(Specialty).order_by(Specialty.position, Specialty.name_ru))
    ).all()
    return [
        SpecialtyOut(code=s.code, name_ru=s.name_ru, name_hy=s.name_hy, position=s.position)
        for s in rows
    ]
