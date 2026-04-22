from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master


@pytest.mark.asyncio
async def test_pick_language_updates_master_lang(session: AsyncSession) -> None:
    from unittest.mock import AsyncMock

    from src.callback_data.settings import LanguageCallback
    from src.handlers.master.settings import cb_pick_language

    master = Master(tg_id=999, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    await session.commit()

    cb = AsyncMock()
    cb_data = LanguageCallback(lang="hy")

    await cb_pick_language(cb, callback_data=cb_data, master=master, session=session)

    assert master.lang == "hy"
    await session.commit()
    await session.refresh(master)
    assert master.lang == "hy"
