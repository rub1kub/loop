import re

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import NotificationOutbox, ResultCard, User
from app.result_cards import (
    CARD_WIDTH,
    ENTRY_VARIANTS,
    CardFacts,
    _font,
    build_result_inline,
    create_entry_card,
    entry_variant,
    render_result_card,
    result_caption,
)

FORBIDDEN = (
    "скоро",
    "жду выплат",
    "успей",
    "осталось мест",
    "заработ",
    "профит",
    "зато",
    "пока что",
)
NEGATED_ONLY = ("гарантирован", "доход", "инвестиц", "депозит")


def test_every_variant_names_the_pyramid_and_promises_nothing() -> None:
    for variant in ENTRY_VARIANTS:
        blob = " ".join(variant.values()).lower()
        assert "пирамид" in blob
        assert "вклад" not in blob
        for word in FORBIDDEN:
            assert word not in blob, f"{word!r} in {variant['headline']!r}"
        for claim in NEGATED_ONLY:
            for match in re.finditer(claim, blob):
                assert blob[max(0, match.start() - 3) : match.start()] == "не ", (
                    f"{claim!r} appears as a claim, not a denial, in {variant['headline']!r}"
                )
        assert "{amount}" in variant["headline"]
        assert "{amount}" in variant["caption"]


GENDERED_PAST = ("депнул", "занёс", "занес", "знал", "вложил", "отдал", "получил ", "решил")


def test_no_variant_assigns_the_sender_a_gender() -> None:
    for variant in ENTRY_VARIANTS:
        blob = (variant["headline"] + " " + variant["subline"] + " " + variant["caption"]).lower()
        for word in GENDERED_PAST:
            assert word not in blob, (
                f"{word!r} is masculine past tense and misgenders half the senders: "
                f"{variant['headline']!r}"
            )


def test_every_variant_states_that_nothing_was_paid() -> None:
    for variant in ENTRY_VARIANTS:
        blob = (variant["subline"] + " " + variant["caption"]).lower()
        assert "не выплачено" in blob or "получено — нет" in blob


def test_the_variant_is_stable_for_a_card_and_differs_across_cards() -> None:
    first = entry_variant("pub-entry-000000000001")
    assert entry_variant("pub-entry-000000000001") == first
    seen = {entry_variant(f"pub-entry-{index:016d}")["headline"] for index in range(60)}
    assert len(seen) == len(ENTRY_VARIANTS)


def test_an_entry_card_renders_and_never_claims_a_payout() -> None:
    facts = CardFacts(
        public_id="pub-entry-000000000001",
        mode="bank_entry",
        payout_nano=0,
        contributed_nano=2_000_000_000,
        result_nano=0,
        queue_position=47,
    )
    image = render_result_card(facts)
    assert image.startswith(b"\xff\xd8")
    assert len(image) > 10_000


def test_rendering_refuses_an_entry_card_that_reports_a_result() -> None:
    with pytest.raises(ValueError, match="no payout and no result"):
        render_result_card(
            CardFacts(
                public_id="pub-entry-000000000002",
                mode="bank_entry",
                payout_nano=1_000,
                contributed_nano=2_000_000_000,
                result_nano=900,
                queue_position=3,
            )
        )


@pytest.mark.asyncio
async def test_entry_card_is_created_once_and_sends_no_telegram_message(app) -> None:
    async with app.state.session_factory() as db:
        user = User(telegram_id=920_001, first_name="Entrant")
        db.add(user)
        await db.flush()
        first = await create_entry_card(
            db,
            user_id=user.id,
            entity_id="position-1",
            event_key="bank_entry:-3:position-1",
            network=-3,
            contributed_nano=2_000_000_000,
            queue_position=47,
            tx_hash="ab" * 32,
        )
        assert first is not None
        again = await create_entry_card(
            db,
            user_id=user.id,
            entity_id="position-1",
            event_key="bank_entry:-3:position-1",
            network=-3,
            contributed_nano=2_000_000_000,
            queue_position=47,
            tx_hash="ab" * 32,
        )
        await db.commit()

    assert again is not None and again.id == first.id
    async with app.state.session_factory() as db:
        cards = (await db.scalars(select(ResultCard))).all()
        assert len(cards) == 1
        card = cards[0]
        assert card.mode == "bank_entry"
        assert card.payout_nano == 0
        assert card.result_nano == 0
        assert card.queue_position == 47
        assert (await db.scalars(select(NotificationOutbox))).all() == []


@pytest.mark.asyncio
async def test_the_caption_reports_the_contribution_and_no_gain(app) -> None:
    async with app.state.session_factory() as db:
        user = User(telegram_id=920_002, first_name="Entrant")
        db.add(user)
        await db.flush()
        card = await create_entry_card(
            db,
            user_id=user.id,
            entity_id="position-2",
            event_key="bank_entry:-3:position-2",
            network=-3,
            contributed_nano=1_500_000_000,
            queue_position=8,
            tx_hash="cd" * 32,
        )
        await db.commit()

    assert card is not None
    caption = result_caption(card)
    assert "1,5 GRAM" in caption
    assert "пирамид" in caption.lower()
    assert "+" not in caption


def test_no_headline_overflows_the_card_at_any_plausible_amount() -> None:
    font = _font(76, bold=True)
    box = CARD_WIDTH - 140
    for variant in ENTRY_VARIANTS:
        for amount in ("0,001 GRAM", "0,25 GRAM", "1 GRAM", "2 GRAM", "1000 GRAM"):
            for line in variant["headline"].format(amount=amount).split("\n"):
                assert font.getlength(line) <= box, f"{line!r} overflows"


@pytest.mark.asyncio
async def test_an_entry_card_carries_no_referral_code(app) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        user = User(telegram_id=920_003, first_name="Entrant")
        db.add(user)
        await db.flush()
        entry = await create_entry_card(
            db,
            user_id=user.id,
            entity_id="position-3",
            event_key="bank_entry:-3:position-3",
            network=-3,
            contributed_nano=1_000_000_000,
            queue_position=5,
            tx_hash="ef" * 32,
        )
        await db.commit()

    assert entry is not None
    inline = build_result_inline(entry, settings, "SOMECODE")
    urls = [button.url for row in inline.reply_markup.inline_keyboard for button in row]
    assert not any(url and "ref_" in url for url in urls), (
        "a confession card must not double as a paid recruitment link"
    )
