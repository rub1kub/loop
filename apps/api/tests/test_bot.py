from types import SimpleNamespace

import pytest
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot import (
    BOT_COMMANDS,
    BOT_DESCRIPTION,
    BOT_MENU_TEXT,
    BOT_NAME,
    BOT_SHORT_DESCRIPTION,
    INLINE_PATTERN,
    RESULT_PATTERN,
    START_MESSAGES,
    SUPPORT_TEXT,
    build_start_rich_message,
    build_support_rich_message,
    configure_bot,
    format_gram,
    main_app_deep_link,
    start_message_for,
)
from app.config import get_settings


def _flatten_rich_text(node: object) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_flatten_rich_text(item) for item in node)
    return _flatten_rich_text(node.text)  # type: ignore[attr-defined]


def _flatten_rich_message(blocks: list[object]) -> list[str]:
    parts = []
    for block in blocks:
        if hasattr(block, "items"):
            for item in block.items:  # type: ignore[attr-defined]
                for nested in item.blocks:
                    parts.append(_flatten_rich_text(nested.text))
        elif hasattr(block, "text"):
            parts.append(_flatten_rich_text(block.text))  # type: ignore[attr-defined]
    return parts


def test_every_start_message_survives_the_rich_message_round_trip() -> None:
    for raw in START_MESSAGES:
        rich = build_start_rich_message(raw)
        assert rich.blocks[0].text == "∞ LOOP"
        original_words = raw.replace("\n", " ").split()
        rebuilt_words = " ".join(_flatten_rich_message(rich.blocks)).split()
        assert rebuilt_words == original_words, f"lost content converting {raw!r}"


def test_start_rich_message_emphasises_only_the_closing_line() -> None:
    from aiogram.types import RichTextItalic

    three_part = next(m for m in START_MESSAGES if len(m.split("\n\n")) == 3)
    rich = build_start_rich_message(three_part)
    assert not isinstance(rich.blocks[1].text, RichTextItalic)
    assert isinstance(rich.blocks[-1].text, RichTextItalic)

    two_part = next(m for m in START_MESSAGES if len(m.split("\n\n")) == 2)
    rich = build_start_rich_message(two_part)
    assert all(not isinstance(block.text, RichTextItalic) for block in rich.blocks[1:])


def test_support_rich_message_keeps_every_step_as_an_ordered_list_item() -> None:
    rich = build_support_rich_message(SUPPORT_TEXT)
    list_block = next(block for block in rich.blocks if hasattr(block, "items"))
    steps = [item.blocks[0].text for item in list_block.items]
    assert steps == [
        "Не отправляй транзакцию повторно.",
        "Сделай снимок экрана.",
        "Скопируй адрес кошелька и хэш транзакции, если он появился.",
        "Напиши, где возникла проблема: BANK, DUEL, рейтинг или вход.",
    ]
    assert [item.value for item in list_block.items] == [1, 2, 3, 4]
    rebuilt = " ".join(_flatten_rich_message(rich.blocks))
    assert "seed-фразу" in rebuilt
    assert "никогда их не запрашивает" in rebuilt


def test_inline_challenge_query_is_offer_bound() -> None:
    match = INLINE_PATTERN.fullmatch("duel 123456")
    assert match is not None and match.group(1) == "123456"
    assert INLINE_PATTERN.fullmatch("2 50") is None
    assert INLINE_PATTERN.fullmatch("duel not-an-offer") is None


def test_inline_result_query_uses_an_opaque_card_id() -> None:
    public_id = "AbCdEfGhIjKlMnOpQrStUvWx"
    match = RESULT_PATTERN.fullmatch(f"result {public_id}")
    assert match is not None and match.group(1) == public_id
    assert RESULT_PATTERN.fullmatch("result 1") is None
    assert RESULT_PATTERN.fullmatch("result ../../secret") is None


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


def test_start_and_support_copy_are_clear_and_safe() -> None:
    assert len(START_MESSAGES) >= 32
    assert len(set(START_MESSAGES)) == len(START_MESSAGES)
    for message in START_MESSAGES:
        start_copy = message.lower()
        assert all(section in start_copy for section in ("∞ loop", "bank", "duel"))
        assert "рейтинг" not in start_copy
        assert "кошелёк" not in start_copy
        assert len(message) <= 160
    assert "seed-фразу" in SUPPORT_TEXT
    assert "не отправляй транзакцию повторно" in SUPPORT_TEXT.lower()
    assert len(SUPPORT_TEXT) <= 4096


def test_start_message_rotates_on_every_call_without_early_repeats() -> None:
    cycle = [start_message_for(42, sequence) for sequence in range(1, len(START_MESSAGES) + 1)]
    assert len(set(cycle)) == len(START_MESSAGES)
    assert start_message_for(42, len(START_MESSAGES) + 1) == cycle[0]


def test_bot_commands_include_support() -> None:
    commands = {(item.command, item.description) for item in BOT_COMMANDS}
    assert commands == {
        ("start", "Открыть LOOP"),
        ("support", "Помощь и связь"),
    }


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
            return [
                BotCommand(command=item.command, description=item.description)
                for item in BOT_COMMANDS
            ]

        async def get_chat_menu_button(self):
            return MenuButtonWebApp(
                text=BOT_MENU_TEXT,
                web_app=WebAppInfo(url=f"{settings.public_origin}/"),
            )

    bot = FakeBot()
    await configure_bot(bot, settings)  # type: ignore[arg-type]
    assert bot.calls == ["description"]
