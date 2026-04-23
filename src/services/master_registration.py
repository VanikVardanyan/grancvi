from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import SlugTaken
from src.repositories.masters import MasterRepository
from src.services.invite import InviteService


class MasterRegistrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._masters = MasterRepository(session)
        self._invites = InviteService(session)

    async def register(
        self,
        *,
        tg_id: int,
        name: str,
        specialty: str,
        slug: str,
        lang: str,
        invite_code: str,
    ) -> Master:
        """Register a new master atomically: validate slug, create Master, redeem invite.

        Raises SlugTaken if the slug is already in use.
        Raises InviteNotFound / InviteExpired / InviteAlreadyUsed via InviteService.
        """
        existing = await self._session.scalar(select(Master).where(Master.slug == slug))
        if existing is not None:
            raise SlugTaken(slug)

        master = Master(
            tg_id=tg_id,
            name=name,
            slug=slug,
            specialty_text=specialty,
            lang=lang,
        )
        self._session.add(master)
        try:
            await self._session.flush()
        except IntegrityError as e:
            raise SlugTaken(slug) from e

        # Redeem invite only after Master is successfully flushed
        redeemed = await self._invites.redeem(code=invite_code, tg_id=tg_id, master_id=master.id)
        # Salon-scoped invites carry a salon_id — auto-link the new master
        # to that salon so they show up in salon dashboards immediately.
        if redeemed.salon_id is not None:
            master.salon_id = redeemed.salon_id
        return master
