from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import SlugTaken
from src.repositories.masters import MasterRepository
from src.services.invite import InviteService
from src.utils.time import now_utc


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

        master = self._build_master(
            tg_id=tg_id, name=name, specialty=specialty, slug=slug, lang=lang
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

    async def register_self(
        self,
        *,
        tg_id: int,
        name: str,
        specialty: str,
        slug: str,
        lang: str,
    ) -> Master:
        """Self-service registration — no invite required. Master starts
        with `is_public = false` so they don't show up in catalogs / search
        until an admin moderates and approves. Otherwise identical to the
        invite-flow registration: same defaults, same UX afterwards.
        """
        existing = await self._session.scalar(select(Master).where(Master.slug == slug))
        if existing is not None:
            raise SlugTaken(slug)

        master = self._build_master(
            tg_id=tg_id, name=name, specialty=specialty, slug=slug, lang=lang
        )
        master.is_public = False  # awaiting admin moderation
        self._session.add(master)
        try:
            await self._session.flush()
        except IntegrityError as e:
            raise SlugTaken(slug) from e
        return master

    def _build_master(
        self,
        *,
        tg_id: int,
        name: str,
        specialty: str,
        slug: str,
        lang: str,
    ) -> Master:
        # Sensible default — Mon-Sat 09:00-20:00, Sunday off. Lets a new
        # master be immediately bookable; the onboarding wizard step 1
        # still walks them through tweaking it.
        default_hours = {
            "mon": [["09:00", "20:00"]],
            "tue": [["09:00", "20:00"]],
            "wed": [["09:00", "20:00"]],
            "thu": [["09:00", "20:00"]],
            "fri": [["09:00", "20:00"]],
            "sat": [["09:00", "20:00"]],
        }
        # Set slug_changed_at = now so the cooldown kicks in from
        # registration, not from the first manual rename. Otherwise the
        # master could rename their slug repeatedly right after creating
        # the account, breaking shared QR/links.
        return Master(
            tg_id=tg_id,
            name=name,
            slug=slug,
            specialty_text=specialty,
            lang=lang,
            work_hours=default_hours,
            slug_changed_at=now_utc(),
        )
