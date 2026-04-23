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


@pytest.mark.asyncio
async def test_pick_language_refreshes_reply_keyboard(session: AsyncSession) -> None:
    """After language switch, a new message with the main_menu keyboard must be sent
    so Telegram redraws the reply keyboard in the newly chosen language."""
    from unittest.mock import AsyncMock, MagicMock

    from aiogram.types import Message, ReplyKeyboardMarkup

    from src.callback_data.settings import LanguageCallback
    from src.handlers.master.settings import cb_pick_language

    master = Master(tg_id=1001, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    await session.commit()

    cb = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.answer = AsyncMock()
    cb_data = LanguageCallback(lang="hy")

    await cb_pick_language(cb, callback_data=cb_data, master=master, session=session)

    assert cb.message.answer.await_count >= 1
    sent_markups = [kwargs.get("reply_markup") for _, kwargs in cb.message.answer.await_args_list]
    assert any(isinstance(m, ReplyKeyboardMarkup) for m in sent_markups), (
        "Expected cb_pick_language to send a new message with ReplyKeyboardMarkup "
        "so the bottom buttons refresh in the new language."
    )
