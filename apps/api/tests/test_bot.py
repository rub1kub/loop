from app.bot import (
    BOT_DESCRIPTION,
    BOT_MENU_TEXT,
    BOT_SHORT_DESCRIPTION,
    INLINE_PATTERN,
    format_gram,
)


def test_inline_challenge_query_is_offer_bound() -> None:
    match = INLINE_PATTERN.fullmatch("duel 123456")
    assert match is not None and match.group(1) == "123456"
    assert INLINE_PATTERN.fullmatch("2 50") is None
    assert INLINE_PATTERN.fullmatch("duel not-an-offer") is None


def test_inline_amount_format_is_human_readable() -> None:
    assert format_gram(2_000_000_000) == "2"
    assert format_gram(1_250_000_000) == "1.25"


def test_bot_profile_describes_social_loop() -> None:
    copy = f"{BOT_DESCRIPTION} {BOT_SHORT_DESCRIPTION} {BOT_MENU_TEXT}".lower()
    assert "bank" in copy
    assert "duel" in copy
    assert "wallet-first" not in copy
    assert "твой кошелёк" not in copy
