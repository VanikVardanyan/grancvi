from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.types import BotCommandScopeChat, BotCommandScopeDefault

from src.main import setup_bot_commands


@pytest.mark.asyncio
async def test_setup_bot_commands_registers_default_for_clients_in_both_langs() -> None:
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock()

    await setup_bot_commands(bot, admin_tg_ids=[])

    langs_called: list[str] = []
    for call in bot.set_my_commands.call_args_list:
        kwargs: dict[str, Any] = call.kwargs
        assert isinstance(kwargs["scope"], BotCommandScopeDefault)
        langs_called.append(kwargs["language_code"])
    assert set(langs_called) == {"ru", "hy"}
    assert bot.set_my_commands.await_count == 2


@pytest.mark.asyncio
async def test_setup_bot_commands_adds_master_scope_per_admin() -> None:
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock()

    await setup_bot_commands(bot, admin_tg_ids=[111, 222])

    chat_scopes: list[int] = []
    for call in bot.set_my_commands.call_args_list:
        scope = call.kwargs["scope"]
        if isinstance(scope, BotCommandScopeChat):
            chat_scopes.append(scope.chat_id)

    # each admin gets 2 calls (ru + hy)
    assert chat_scopes.count(111) == 2
    assert chat_scopes.count(222) == 2
    # plus 2 default calls
    assert bot.set_my_commands.await_count == 2 + 2 * 2


@pytest.mark.asyncio
async def test_master_commands_include_core_schedule_and_crud() -> None:
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock()

    await setup_bot_commands(bot, admin_tg_ids=[123])

    master_ru_call = next(
        c
        for c in bot.set_my_commands.call_args_list
        if isinstance(c.kwargs["scope"], BotCommandScopeChat) and c.kwargs["language_code"] == "ru"
    )
    names = {cmd.command for cmd in master_ru_call.kwargs["commands"]}
    assert {"start", "today", "tomorrow", "week", "calendar", "add", "client"}.issubset(names)
