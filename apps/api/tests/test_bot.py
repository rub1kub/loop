from types import SimpleNamespace

import pytest
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot import (
    BOT_DESCRIPTION,
    BOT_MENU_TEXT,
    BOT_NAME,
    BOT_SHORT_DESCRIPTION,
    INLINE_PATTERN,
    configure_bot,
    format_gram,
    main_app_deep_link,
)
from app.config import get_settings


def test_inline_challenge_query_is_offer_bound() -> None:
    match = INLINE_PATTERN.fullmatch("duel 123456")
    assert match is not None and match.group(1) == "123456"
    assert INLINE_PATTERN.fullmatch("2 50") is None
    assert INLINE_PATTERN.fullmatch("duel not-an-offer") is None


def test_inline_amount_format_is_human_readable() -> None:
    assert format_gram(2_000_000_000) == "2"
    assert format_gram(1_250_000_000) == "1.25"


def test_main_app_deep_link_uses_the_botfather_launch_mode() -> None:
    assert main_app_deep_link("@getloopbot") == "https://t.me/getloopbot?startapp"


def test_bot_profile_describes_independent_bank_and_duel() -> None:
    copy = f"{BOT_DESCRIPTION} {BOT_SHORT_DESCRIPTION} {BOT_MENU_TEXT}".lower()
    assert "bank" in copy
    assert "duel" in copy
    assert "wallet-first" not in copy
    assert "твой кошелёк" not in copy


@pytest.mark.asyncio
async def test_bot_configuration_only_mutates_drifted_metadata() -> None:
    settings = get_settings()

    class FakeBot:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def get_webhook_info(self):
            return SimpleNamespace(
                url=f"{settings.public_origin}{settings.webhook_path}",
                allowed_updates=["message", "inline_query", "callback_query"],
            )

        async def get_my_name(self):
            return SimpleNamespace(name=BOT_NAME)

        async def get_my_description(self):
            return SimpleNamespace(description="stale")

        async def set_my_description(self, value: str) -> bool:
            assert value == BOT_DESCRIPTION
            self.calls.append("description")
            return True

        async def get_my_short_description(self):
            return SimpleNamespace(short_description=BOT_SHORT_DESCRIPTION)

        async def get_my_commands(self):
            return [BotCommand(command="start", description="Открыть LOOP")]

        async def get_chat_menu_button(self):
            return MenuButtonWebApp(
                text=BOT_MENU_TEXT,
                web_app=WebAppInfo(url=settings.public_origin),
            )

    bot = FakeBot()
    await configure_bot(bot, settings)  # type: ignore[arg-type]
    assert bot.calls == ["description"]
