from __future__ import annotations

import hashlib
import io
import math
import random
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultPhoto,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import select

from .config import Settings
from .models import NotificationOutbox, ResultCard
from .ton import explorer_transaction_url

CARD_WIDTH = 1080
CARD_HEIGHT = 1350
CARD_JPEG_QUALITY = 92
CARD_TEMPLATE_VERSION = 4
FONT_REGULAR_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)
FONT_BOLD_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)
RENDER_LIMIT = threading.BoundedSemaphore(2)


@dataclass(frozen=True)
class CardFacts:
    public_id: str
    mode: str
    payout_nano: int
    contributed_nano: int
    result_nano: int
    queue_position: int | None = None
    # Кого победили — @ник или имя. Появляется только на карточках DUEL.
    opponent: str | None = None
    demo: bool = False


def format_gram(nano: int, decimals: int = 3) -> str:
    value = nano / 1_000_000_000
    rendered = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return rendered.replace(".", ",")


ENTRY_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "headline": "ЧЕК НА {amount}\nВ ФИНАНСОВУЮ\nПИРАМИДУ",
        "subline": "Оплачено — да. Получено — нет.",
        "stat_label": "МОЙ НОМЕР В ОЧЕРЕДИ",
        "caption": (
            "Чек на {amount}. Назначение платежа — финансовая пирамида.\n\nОплачено — "
            "да, получено — нет. На руках номер в очереди."
        ),
    },
    {
        "headline": "СДАНО {amount}.\nНОМЕРОК НА РУКАХ.\nПАЛЬТО НЕ ВЕРНУТ.",
        "subline": "Финансовая пирамида, если без метафор.",
        "stat_label": "НОМЕРОК",
        "caption": (
            "Сдано {amount}, номерок на руках, пальто не вернут.\n\nBANK — финансовая "
            "пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "НЕ ИНВЕСТИЦИЯ.\nНЕ ДЕПОЗИТ.\nВЗНОС {amount}.",
        "subline": "Финансовая пирамида. Другого слова тут нет.",
        "stat_label": "МОЁ МЕСТО В ОЧЕРЕДИ",
        "caption": (
            "Не инвестиция и не депозит. Взнос {amount} в BANK — финансовую "
            "пирамиду.\n\nМне не выплачено ничего — есть только номер в очереди."
        ),
    },
    {
        "headline": "ЧЕМ БОЛЬШЕ\nЧИСЛО, ТЕМ ХУЖЕ.\nВЗНОС {amount}",
        "subline": "Не рейтинг, а место в финансовой пирамиде.",
        "stat_label": "МОЁ МЕСТО В ОЧЕРЕДИ",
        "caption": (
            "Взнос {amount} в BANK. Число на карточке — моё место в очереди: чем оно "
            "больше, тем больше чужих взносов должно прийти раньше.\n\nBANK — "
            "финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "БЕЗ ГАРАНТИЙ.\nБЕЗ СРОКОВ.\nВЗНОС {amount}.",
        "subline": "Отмены тоже нет. Это финансовая пирамида.",
        "stat_label": "МОЁ МЕСТО В ОЧЕРЕДИ",
        "caption": (
            "Без гарантий, без сроков, без отмены. Взнос {amount} в BANK.\n\nBANK — "
            "финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ВЗНОС {amount}\nПРИНЯТ. НОМЕР\nПРИСВОЕН.",
        "subline": "Больше ничего не произошло. Финансовая пирамида.",
        "stat_label": "ПРИСВОЕННЫЙ НОМЕР",
        "caption": (
            "Взнос {amount} принят, номер присвоен. Больше ничего не произошло.\n\nBANK "
            "— финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ДА, Я ЗНАЮ,\nЧТО ЭТО ПИРАМИДА.\nВЗНОС {amount}",
        "subline": "Вопрос закрыт, можно не писать в комментарии.",
        "stat_label": "МОЙ НОМЕР В ОЧЕРЕДИ",
        "caption": (
            "Да, я знаю, что это финансовая пирамида. Взнос {amount}.\n\nМне не "
            "выплачено ничего. Есть номер в очереди."
        ),
    },
    {
        "headline": "ПИРАМИДА.\nНЕ СХЕМА, НЕ ПРОЕКТ.\nВЗНОС {amount}",
        "subline": "Слово короткое и точное.",
        "stat_label": "МОЁ МЕСТО В ОЧЕРЕДИ",
        "caption": (
            "Финансовая пирамида. Не схема, не проект, не стартап. Взнос "
            "{amount}.\n\nМне не выплачено ничего."
        ),
    },
    {
        "headline": "ПРИНЯЛА {amount}.\nРАСПИСКИ\nНЕ БУДЕТ.",
        "subline": "Финансовая пирамида — она такая.",
        "stat_label": "ВЫДАННЫЙ НОМЕР",
        "caption": (
            "Пирамида приняла {amount}. Расписки не будет — только номер в "
            "очереди.\n\nBANK — финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ОЧЕРЕДЬ ПРИНЯЛА\n{amount} И НИЧЕГО\nНЕ ПООБЕЩАЛА",
        "subline": "Честнее, чем большинство продуктов.",
        "stat_label": "МОЙ НОМЕР",
        "caption": (
            "Очередь приняла {amount} и ничего не пообещала.\n\nBANK — финансовая "
            "пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ПОЗДРАВЛЯЮ СЕБЯ\nС ПОКУПКОЙ МЕСТА\nВ ОЧЕРЕДИ. {amount}",
        "subline": "Больше ничего не купил, только место.",
        "stat_label": "КУПЛЕННОЕ МЕСТО",
        "caption": (
            "Поздравляю себя с покупкой места в очереди за {amount}.\n\nBANK — "
            "финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "{amount} В ОБМЕН\nНА ПОРЯДКОВЫЙ\nНОМЕР",
        "subline": "Сделка века, как видите.",
        "stat_label": "ТОТ САМЫЙ НОМЕР",
        "caption": (
            "{amount} в обмен на порядковый номер. Сделка века.\n\nBANK — финансовая "
            "пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ГРАФИКОВ НЕ БУДЕТ.\nБУДЕТ НОМЕР.\nВЗНОС {amount}",
        "subline": "Ни свечей, ни иксов. Просто очередь.",
        "stat_label": "МОЙ НОМЕР В ОЧЕРЕДИ",
        "caption": (
            "Графиков не будет, будет номер в очереди. Взнос {amount} в "
            "очереди.\n\nBANK — финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "{amount}\nУШЛИ ВПЕРЁД\nПО ОЧЕРЕДИ",
        "subline": "Так это и работает, если что.",
        "stat_label": "МОЁ МЕСТО В ОЧЕРЕДИ",
        "caption": (
            "{amount} ушли вперёд по очереди, не ко мне. Так это и работает.\n\nBANK — "
            "финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ДЕНЬГИ ОТДАНЫ\nДОБРОВОЛЬНО.\nСУММА {amount}",
        "subline": "Никто не заставлял, никто не врал.",
        "stat_label": "НОМЕР В ОЧЕРЕДИ",
        "caption": (
            "Деньги отданы добровольно, сумма {amount}. Никто не заставлял и никто не "
            "врал.\n\nBANK — финансовая пирамида. Мне не выплачено ничего."
        ),
    },
    {
        "headline": "ВСЁ ПОНЯТНО\nПРО РИСКИ.\nВЗНОС {amount}",
        "subline": "Понятно. Взнос всё равно сделан.",
        "stat_label": "МОЙ НОМЕР В ОЧЕРЕДИ",
        "caption": (
            "Всё понятно про риски, взнос {amount} всё равно сделан.\n\nBANK — "
            "финансовая пирамида. Мне не выплачено ничего."
        ),
    },
)

def entry_variant(public_id: str) -> dict[str, str]:
    seed = int.from_bytes(hashlib.sha256(public_id.encode()).digest()[:4], "big")
    return ENTRY_VARIANTS[seed % len(ENTRY_VARIANTS)]


BANK_PAYOUT_HEADLINES = (
    "МОЙ ЦИКЛ\nЗАМКНУЛСЯ",
    "ОЧЕРЕДЬ ДОШЛА\nДО МЕНЯ",
    "ПИРАМИДА\nЗАПЛАТИЛА",
    "НОМЕР ОТЫГРАЛ.\nДЕНЬГИ ПРИШЛИ",
)
DUEL_PAYOUT_HEADLINES = (
    "ПУЛ МОЙ",
    "DUEL ЗАКРЫТ\nВ МОЮ ПОЛЬЗУ",
    "ЧУЖАЯ СТАВКА\nТЕПЕРЬ МОЯ",
    "ОДИН НА ОДИН.\nПУЛ У МЕНЯ",
)

# Победная карточка называет побеждённого по имени и глумится. Тон задан
# владельцем: жёстко, мемно, постиронично. Оба игрока сами согласились на
# дуэль в продукте, который называет себя финансовой пирамидой на первом
# экране, — карточка продолжает тот же язык. Вариант детерминирован public_id,
# чтобы картинка оставалась кэшируемой.
DUEL_TAUNT_VARIANTS: tuple[dict[str, str], ...] = (
    {"headline": "ПОСТАВИЛ РАКОМ\n{opp}", "caption": "Поставил раком {opp} в LOOP DUEL."},
    {
        "headline": "{opp}\nСПОНСИРУЕТ\nМОЙ УСПЕХ",
        "caption": "{opp} теперь спонсирует мой успех. Спасибо за взнос.",
    },
    {
        "headline": "МИНУТА МОЛЧАНИЯ\nПО СТАВКЕ\n{opp}",
        "caption": "Минута молчания по ставке {opp}. Она ушла ко мне.",
    },
    {
        "headline": "{opp},\nСПАСИБО.\nОЧЕНЬ ВКУСНО",
        "caption": "{opp}, спасибо. Очень вкусно. Ставку не верну.",
    },
    {
        "headline": "{opp}\nВЕРИЛ В СЕБЯ.\nЗРЯ",
        "caption": "{opp} верил в себя. Математика решила иначе.",
    },
    {
        "headline": "СОБОЛЕЗНУЕМ\nБЛИЗКИМ\n{opp}",
        "caption": "Соболезнуем близким {opp}. Ставка погибла в честном бою.",
    },
    {
        "headline": "{opp} —\nМОЙ ПАССИВНЫЙ\nДОХОД",
        "caption": "{opp} — мой пассивный доход. Рекомендую такого соперника каждому.",
    },
    {
        "headline": "ШАНСЫ БЫЛИ\n50/50.\nНО НЕ У {opp}",
        "caption": "Шансы были 50/50. Но, как выяснилось, не у {opp}.",
    },
)


def duel_taunt(public_id: str, opponent: str) -> dict[str, str]:
    seed = int.from_bytes(hashlib.sha256(f"taunt:{public_id}".encode()).digest()[:4], "big")
    variant = DUEL_TAUNT_VARIANTS[seed % len(DUEL_TAUNT_VARIANTS)]
    return {key: value.format(opp=opponent) for key, value in variant.items()}


def result_headline(mode: str, public_id: str = "") -> str:
    if mode == "bank":
        pool = BANK_PAYOUT_HEADLINES
    elif mode == "duel":
        pool = DUEL_PAYOUT_HEADLINES
    else:
        raise ValueError("unknown result card mode")
    if not public_id:
        return pool[0]
    seed = int.from_bytes(hashlib.sha256(public_id.encode()).digest()[:4], "big")
    return pool[seed % len(pool)]


def result_caption(card: ResultCard, opponent_label: str | None = None) -> str:
    if card.mode == "bank_entry":
        variant = entry_variant(card.public_id)
        return variant["caption"].format(amount=f"{format_gram(card.contributed_nano)} GRAM")
    result = format_gram(card.result_nano)
    payout = format_gram(card.payout_nano)
    if card.mode == "bank":
        return (
            f"Мой цикл в LOOP замкнулся.\n\n"
            f"Выплата: +{payout} GRAM\n"
            f"Сверх взноса: +{result} GRAM\n\n"
            "Результат подтверждён."
        )
    opening = (
        duel_taunt(card.public_id, opponent_label)["caption"]
        if opponent_label
        else "Я забрал DUEL в LOOP."
    )
    return (
        f"{opening}\n\n"
        f"Выплата: {payout} GRAM\n"
        f"Разница к входу: +{result} GRAM\n\n"
        "Результат подтверждён."
    )


def result_card_image_url(settings: Settings, card: ResultCard) -> str:
    # The image route is immutable for a template version. Version the URL so
    # Telegram and browser caches do not keep an older payout-as-profit card.
    return (
        f"{settings.public_origin}/api/v1/results/cards/{card.public_id}.jpg"
        f"?v={CARD_TEMPLATE_VERSION}"
    )


def turn_card_image_url(settings: Settings, card: ResultCard) -> str:
    return (
        f"{settings.public_origin}/api/v1/results/turn/{card.public_id}.jpg"
        f"?v={CARD_TEMPLATE_VERSION}"
    )


def turn_caption(card: ResultCard) -> str:
    return (
        "Я вошёл в LOOP. Теперь твой ход.\n\n"
        f"Взнос: {format_gram(card.contributed_nano)} GRAM. "
        f"Место в очереди: №{card.queue_position or '—'}.\n\n"
        "BANK — финансовая пирамида. Выплата не гарантирована."
    )


def result_deep_link(settings: Settings, referral_code: str | None) -> str:
    base = f"https://t.me/{settings.bot_username.removeprefix('@')}?startapp"
    return f"{base}=ref_{referral_code}" if referral_code else base


def build_result_inline(
    card: ResultCard,
    settings: Settings,
    referral_code: str | None,
    opponent_label: str | None = None,
) -> InlineQueryResultPhoto:
    entry = card.mode == "bank_entry"
    image_url = (
        turn_card_image_url(settings, card)
        if entry
        else result_card_image_url(settings, card)
    )
    return InlineQueryResultPhoto(
        id=card.public_id,
        photo_url=image_url,
        thumbnail_url=image_url,
        photo_width=CARD_WIDTH,
        photo_height=CARD_HEIGHT,
        title="Взнос в BANK" if entry else "Результат LOOP",
        description=(
            f"{format_gram(card.contributed_nano)} GRAM в очереди"
            if entry
            else f"+{format_gram(card.result_nano)} GRAM"
        ),
        caption=turn_caption(card) if entry else result_caption(card, opponent_label),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ПРИНЯТЬ ХОД" if entry else "ОТКРЫТЬ LOOP",
                        url=result_deep_link(settings, referral_code),
                    ),
                    InlineKeyboardButton(text="ПРОВЕРИТЬ", url=card.proof_url),
                ]
            ]
        ),
    )


def notification_markup(
    card: ResultCard,
    settings: Settings,
    referral_code: str | None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ПОДЕЛИТЬСЯ",
                    switch_inline_query=f"result {card.public_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="ОТКРЫТЬ LOOP",
                    url=result_deep_link(settings, referral_code),
                ),
                InlineKeyboardButton(text="ПРОВЕРИТЬ", url=card.proof_url),
            ],
        ]
    )


async def duel_opponent_label(db: Any, card: ResultCard) -> str | None:
    """Кого победил владелец карточки — @ник или имя, если сервер их знает."""
    if card.mode != "duel":
        return None
    from .modules.duel.models import Duel, DuelOffer

    duel = await db.get(Duel, card.entity_id)
    if duel is None:
        return None
    for offer_id in (duel.offer_a_id, duel.offer_b_id):
        offer = await db.get(DuelOffer, offer_id)
        if offer is None or offer.user_id is None or offer.user_id == card.user_id:
            continue
        from .models import User

        loser = await db.get(User, offer.user_id)
        if loser is None:
            return None
        return f"@{loser.username}" if loser.username else loser.first_name
    return None


async def create_result_card(
    db: Any,
    *,
    user_id: str | None,
    mode: str,
    entity_id: str,
    event_key: str,
    network: int,
    payout_nano: int,
    contributed_nano: int,
    tx_hash: str,
) -> ResultCard | None:
    if user_id is None:
        return None
    if mode not in {"bank", "duel"}:
        raise ValueError("unknown result card mode")
    if payout_nano <= contributed_nano or contributed_nano < 0:
        raise ValueError("shareable result must have a positive verified difference")
    existing: ResultCard | None = await db.scalar(
        select(ResultCard).where(ResultCard.event_key == event_key)
    )
    if existing is not None:
        return existing
    card = ResultCard(
        user_id=user_id,
        mode=mode,
        entity_id=entity_id,
        event_key=event_key,
        network=network,
        payout_nano=payout_nano,
        contributed_nano=contributed_nano,
        result_nano=payout_nano - contributed_nano,
        tx_hash=tx_hash,
        proof_url=explorer_transaction_url(network, tx_hash),
        template_version=CARD_TEMPLATE_VERSION,
    )
    db.add(card)
    await db.flush()
    db.add(
        NotificationOutbox(
            user_id=user_id,
            kind="result",
            dedupe_key=f"result:{card.id}",
            result_card_id=card.id,
        )
    )
    return card


async def create_entry_card(
    db: Any,
    *,
    user_id: str | None,
    entity_id: str,
    event_key: str,
    network: int,
    contributed_nano: int,
    queue_position: int | None,
    tx_hash: str,
) -> ResultCard | None:
    if user_id is None:
        return None
    if contributed_nano <= 0:
        raise ValueError("an entry card needs a positive contribution")
    existing: ResultCard | None = await db.scalar(
        select(ResultCard).where(ResultCard.event_key == event_key)
    )
    if existing is not None:
        return existing
    card = ResultCard(
        user_id=user_id,
        mode="bank_entry",
        entity_id=entity_id,
        event_key=event_key,
        network=network,
        payout_nano=0,
        contributed_nano=contributed_nano,
        result_nano=0,
        queue_position=queue_position,
        tx_hash=tx_hash,
        proof_url=explorer_transaction_url(network, tx_hash),
        template_version=CARD_TEMPLATE_VERSION,
    )
    db.add(card)
    await db.flush()
    return card


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_REGULAR_CANDIDATES
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    spacing: int = 10,
) -> None:
    draw.multiline_text(
        xy,
        text,
        font=font,
        fill=fill,
        anchor="mm",
        align="center",
        spacing=spacing,
    )


def _draw_infinity(image: Image.Image, y: int) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    points: list[tuple[float, float]] = []
    for step in range(361):
        angle = math.radians(step)
        denominator = 1 + math.sin(angle) ** 2
        x = math.cos(angle) / denominator
        wave = math.sin(angle) * math.cos(angle) / denominator
        points.append((CARD_WIDTH / 2 + x * 170, y + wave * 210))
    draw.line(points, fill=(255, 255, 255, 90), width=34, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    image.alpha_composite(glow)
    line = ImageDraw.Draw(image)
    line.line(points, fill=(236, 236, 236, 245), width=9, joint="curve")


def _draw_bank_particles(image: Image.Image, seed: int) -> None:
    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)  # noqa: S311 - deterministic visual noise, not security
    for index in range(440):
        x = rng.randint(80, CARD_WIDTH - 80)
        baseline = 1040 + int(34 * math.sin(x / 92))
        y = baseline + rng.randint(-22, 84)
        distance = max(0, y - baseline)
        shade = max(76, 205 - distance * 2)
        radius = 1 if index % 4 else 2
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(shade,) * 3 + (190,))


def _draw_duel_orbits(image: Image.Image) -> None:
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    for cx in (385, 695):
        draw.ellipse((cx - 118, 912, cx + 118, 1148), outline=(255, 255, 255, 90), width=22)
    glow = glow.filter(ImageFilter.GaussianBlur(22))
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)
    draw.ellipse((267, 912, 503, 1148), outline=(230, 230, 230, 235), width=5)
    draw.ellipse((577, 912, 813, 1148), outline=(230, 230, 230, 235), width=5)
    draw.line((503, 1030, 577, 1030), fill=(125, 125, 125, 255), width=3)


@lru_cache(maxsize=64)
def render_result_card(facts: CardFacts) -> bytes:
    with RENDER_LIMIT:
        if facts.mode == "bank_entry":
            return _render_entry_card(facts)
        return _render_result_card(facts)


def _render_entry_card(facts: CardFacts) -> bytes:
    if facts.result_nano != 0 or facts.payout_nano != 0:
        raise ValueError("an entry card must report no payout and no result")
    variant = entry_variant(facts.public_id)
    image = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    seed = int.from_bytes(hashlib.sha256(facts.public_id.encode()).digest()[:8], "big")
    rng = random.Random(seed)  # noqa: S311 - deterministic visual noise, not security
    for _ in range(520):
        shade = rng.randint(14, 42)
        draw.point(
            (rng.randrange(CARD_WIDTH), rng.randrange(CARD_HEIGHT)),
            fill=(shade, shade, shade, rng.randint(60, 150)),
        )

    draw.text((70, 64), "∞  LOOP", font=_font(30, bold=True), fill=(245, 245, 245), anchor="la")
    draw.text(
        (CARD_WIDTH - 70, 68),
        "BANK",
        font=_font(20, bold=True),
        fill=(142, 142, 142),
        anchor="ra",
    )
    if facts.demo:
        draw.rounded_rectangle((430, 52, 650, 102), radius=25, outline=(105, 105, 105), width=2)
        _centered_text(draw, (540, 77), "ОБРАЗЕЦ", font=_font(18, bold=True), fill=(170, 170, 170))

    headline = variant["headline"].format(amount=f"{format_gram(facts.contributed_nano)} GRAM")
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 430),
        headline,
        font=_font(76, bold=True),
        fill=(250, 250, 250),
        spacing=16,
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 640),
        variant["subline"],
        font=_font(30),
        fill=(150, 150, 150),
    )

    if facts.queue_position:
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 880),
            f"№ {facts.queue_position}",
            font=_font(92, bold=True),
            fill=(255, 255, 255),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 962),
            variant["stat_label"],
            font=_font(20, bold=True),
            fill=(135, 135, 135),
        )

    draw.line((70, 1176, CARD_WIDTH - 70, 1176), fill=(54, 54, 54), width=2)
    draw.text(
        (70, 1222),
        f"ВНЕСЕНО  {format_gram(facts.contributed_nano)} GRAM",
        font=_font(22, bold=True),
        fill=(212, 212, 212),
        anchor="la",
    )
    draw.text(
        (CARD_WIDTH - 70, 1222),
        "ВЫПЛАЧЕНО  0 GRAM",
        font=_font(22, bold=True),
        fill=(212, 212, 212),
        anchor="ra",
    )
    draw.text(
        (CARD_WIDTH // 2, 1318),
        "LOOP · TONSUITE.ORG",
        font=_font(16, bold=True),
        fill=(95, 95, 95),
        anchor="ma",
    )

    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=CARD_JPEG_QUALITY, optimize=True)
    return output.getvalue()


def render_turn_card(facts: CardFacts) -> bytes:
    if facts.mode != "bank_entry" or facts.contributed_nano <= 0:
        raise ValueError("a turn card needs a confirmed BANK entry")
    image = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    seed = int.from_bytes(hashlib.sha256(f"turn:{facts.public_id}".encode()).digest()[:8], "big")
    rng = random.Random(seed)  # noqa: S311 - deterministic visual noise, not security
    for _ in range(520):
        shade = rng.randint(14, 42)
        draw.point(
            (rng.randrange(CARD_WIDTH), rng.randrange(CARD_HEIGHT)),
            fill=(shade, shade, shade, rng.randint(60, 150)),
        )
    draw.text((70, 64), "∞  LOOP", font=_font(30, bold=True), fill=(245, 245, 245), anchor="la")
    draw.text(
        (CARD_WIDTH - 70, 68),
        "ТВОЙ ХОД",
        font=_font(20, bold=True),
        fill=(142, 142, 142),
        anchor="ra",
    )
    _draw_infinity(image, 330)
    draw = ImageDraw.Draw(image)
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 650),
        "Я ВОШЁЛ В LOOP.\nТЕПЕРЬ ТВОЙ ХОД.",
        font=_font(72, bold=True),
        fill=(250, 250, 250),
        spacing=18,
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 850),
        f"№ {facts.queue_position or '—'}",
        font=_font(92, bold=True),
        fill=(255, 255, 255),
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 932),
        "МОЁ МЕСТО В ОЧЕРЕДИ",
        font=_font(20, bold=True),
        fill=(135, 135, 135),
    )
    draw.line((70, 1176, CARD_WIDTH - 70, 1176), fill=(54, 54, 54), width=2)
    draw.text(
        (70, 1222),
        f"ВНЕСЕНО  {format_gram(facts.contributed_nano)} GRAM",
        font=_font(22, bold=True),
        fill=(212, 212, 212),
        anchor="la",
    )
    draw.text(
        (CARD_WIDTH - 70, 1222),
        "ВЫПЛАТА НЕ ГАРАНТИРОВАНА",
        font=_font(18, bold=True),
        fill=(150, 150, 150),
        anchor="ra",
    )
    draw.text(
        (CARD_WIDTH // 2, 1318),
        "LOOP · TONSUITE.ORG",
        font=_font(16, bold=True),
        fill=(95, 95, 95),
        anchor="ma",
    )
    output = io.BytesIO()
    image.convert("RGB").save(output, format="JPEG", quality=CARD_JPEG_QUALITY, optimize=True)
    return output.getvalue()


def _render_result_card(facts: CardFacts) -> bytes:
    if facts.mode not in {"bank", "duel"}:
        raise ValueError("unknown result card mode")
    if facts.result_nano <= 0 or facts.payout_nano <= facts.contributed_nano:
        raise ValueError("result card requires a positive verified difference")
    image = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    seed = int.from_bytes(hashlib.sha256(facts.public_id.encode()).digest()[:8], "big")
    rng = random.Random(seed)  # noqa: S311 - deterministic visual noise, not security
    for _ in range(520):
        shade = rng.randint(14, 42)
        x = rng.randrange(CARD_WIDTH)
        y = rng.randrange(CARD_HEIGHT)
        draw.point((x, y), fill=(shade, shade, shade, rng.randint(60, 150)))

    draw.text((70, 64), "∞  LOOP", font=_font(30, bold=True), fill=(245, 245, 245), anchor="la")
    draw.text(
        (CARD_WIDTH - 70, 68),
        facts.mode.upper(),
        font=_font(20, bold=True),
        fill=(142, 142, 142),
        anchor="ra",
    )
    if facts.demo:
        draw.rounded_rectangle((430, 52, 650, 102), radius=25, outline=(105, 105, 105), width=2)
        _centered_text(
            draw,
            (540, 77),
            "ОБРАЗЕЦ",
            font=_font(18, bold=True),
            fill=(170, 170, 170),
        )

    _draw_infinity(image, 325)
    draw = ImageDraw.Draw(image)
    taunt = (
        duel_taunt(facts.public_id, facts.opponent)
        if facts.mode == "duel" and facts.opponent
        else None
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 610),
        taunt["headline"] if taunt else result_headline(facts.mode, facts.public_id),
        # Ники бывают длинными, поэтому глумливый заголовок набирается мельче.
        # Интерлиньяж задаётся явно: на трёх строках дефолтный клал строки
        # друг на друга, и «@ник» перекрывал следующее слово.
        font=_font(56 if taunt else 74, bold=True),
        fill=(250, 250, 250),
        spacing=22 if taunt else -2,
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 790),
        f"+{format_gram(facts.result_nano)} GRAM",
        font=_font(82, bold=True),
        fill=(255, 255, 255),
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 868),
        "СВЕРХ СТАВКИ",
        font=_font(20, bold=True),
        fill=(135, 135, 135),
    )

    if facts.mode == "bank":
        _draw_bank_particles(image, seed)
    else:
        _draw_duel_orbits(image)

    draw = ImageDraw.Draw(image)
    draw.line((70, 1200, CARD_WIDTH - 70, 1200), fill=(54, 54, 54), width=2)
    draw.text(
        (70, 1246),
        # The headline now carries the payout, so the footer carries what went
        # in — repeating the payout twice told the reader nothing new.
        f"ВЗНОС  {format_gram(facts.contributed_nano)} GRAM",
        font=_font(22, bold=True),
        fill=(212, 212, 212),
        anchor="la",
    )
    draw.text(
        (CARD_WIDTH - 70, 1246),
        "ПОДТВЕРЖДЕНО",
        font=_font(22, bold=True),
        fill=(212, 212, 212),
        anchor="ra",
    )
    draw.text(
        (CARD_WIDTH // 2, 1302),
        "LOOP · TONSUITE.ORG",
        font=_font(16, bold=True),
        fill=(95, 95, 95),
        anchor="ma",
    )

    output = io.BytesIO()
    image.convert("RGB").save(
        output,
        format="JPEG",
        quality=CARD_JPEG_QUALITY,
        optimize=True,
    )
    return output.getvalue()


INVITE_VARIANTS: tuple[dict[str, str], ...] = (
    {
        "headline": "ПИРАМИДА\nОТКРЫВАЕТСЯ.\nМЕСТА СВЕРХУ.",
        "subline": "Потом будут только снизу.",
        "caption": (
            "Пирамида открывается. Места пока сверху — потом будут только снизу.\n\n"
            "LOOP: заходишь, вносишь, встаёшь в очередь."
        ),
    },
    {
        "headline": "ЗОВУ ТЕБЯ\nВ ФИНАНСОВУЮ\nПИРАМИДУ.",
        "subline": "Да, прямо так и называется.",
        "caption": (
            "Зову тебя в финансовую пирамиду. Да, она прямо так и называется — "
            "никто ничего не прячет.\n\nОткрытие уже скоро."
        ),
    },
    {
        "headline": "КТО ПЕРВЫЙ ВСТАЛ,\nТОГО И ОЧЕРЕДЬ.\nЯ УЖЕ ВСТАЛ.",
        "subline": "Стою и машу тебе рукой.",
        "caption": (
            "Кто первый встал, того и очередь. Я уже стою.\n\nLOOP открывается — "
            "выплаты идут по порядку, с начала."
        ),
    },
    {
        "headline": "ПОТОМ БУДЕШЬ\nГОВОРИТЬ, ЧТО\nНЕ ЗВАЛИ.",
        "subline": "Вот, зову. Скриншот сохрани.",
        "caption": (
            "Потом будешь говорить, что не звали. Вот — зову, скриншот "
            "сохрани.\n\nLOOP открывается."
        ),
    },
    {
        "headline": "ОЧЕРЕДЬ ЕЩЁ\nПУСТАЯ. ЭТО\nНЕНАДОЛГО.",
        "subline": "Дальше начнётся давка.",
        "caption": (
            "Очередь пока пустая, и это ненадолго.\n\nLOOP: ранние позиции "
            "наполняются первыми."
        ),
    },
    {
        "headline": "НЕ ИНВЕСТИЦИЯ.\nНЕ ПРОЕКТ.\nПРОСТО ОЧЕРЕДЬ.",
        "subline": "Зато честно с первой секунды.",
        "caption": (
            "Не инвестиция, не проект, не стартап. Просто очередь за деньгами.\n\n"
            "LOOP открывается — правила видно каждому."
        ),
    },
    {
        "headline": "ВСЕ СТРОЯТ\nПИРАМИДЫ. Я ЗОВУ\nВ ЧЕСТНУЮ.",
        "subline": "Честную в том, что она пирамида.",
        "caption": (
            "Все строят пирамиды, просто называют иначе. Эта честная — в том, "
            "что она пирамида.\n\nLOOP открывается."
        ),
    },
    {
        "headline": "СКАЖИ ПОТОМ,\nЧТО Я ТЕБЯ\nНЕ ПРЕДУПРЕЖДАЛ.",
        "subline": "Предупреждаю: это пирамида.",
        "caption": (
            "Скажи потом, что не предупреждал. Предупреждаю: это финансовая "
            "пирамида.\n\nLOOP открывается. Дальше сам."
        ),
    },
    {
        "headline": "ТУТ НЕТ\nГРАФИКОВ.\nТУТ ЕСТЬ ОЧЕРЕДЬ.",
        "subline": "Ни свечей, ни иксов, ни аналитики.",
        "caption": (
            "Тут нет графиков и прогнозов. Тут есть очередь и твой номер в "
            "ней.\n\nLOOP открывается."
        ),
    },
    {
        "headline": "МЕСТО В ОЧЕРЕДИ\nПОКА БЕСПЛАТНО.\nПОТОМ — НЕТ.",
        "subline": "Ну то есть вход бесплатный.",
        "caption": (
            "Место в очереди пока никем не занято.\n\nLOOP открывается — "
            "вход уже открыт, зайди заранее."
        ),
    },
    {
        "headline": "ПРИГЛАШАЮ\nВ ОЧЕРЕДЬ\nЗА ЧУЖИМИ ДЕНЬГАМИ.",
        "subline": "Формулировка точная. Извини.",
        "caption": (
            "Приглашаю в очередь за чужими деньгами. Формулировка точная.\n\n"
            "LOOP — финансовая пирамида на TON. Открытие скоро."
        ),
    },
    {
        "headline": "ЗАЙДЁШЬ РАНЬШЕ —\nБУДЕШЬ ВЫШЕ.\nВОТ И ВСЯ СХЕМА.",
        "subline": "Другой схемы и не было.",
        "caption": (
            "Зайдёшь раньше — будешь выше в очереди. Вот и вся схема, другой "
            "нет.\n\nLOOP открывается."
        ),
    },
    {
        "headline": "ОБЕЩАТЬ НИЧЕГО\nНЕ БУДУ.\nПОЗВАТЬ — ПОЗОВУ.",
        "subline": "Гарантий тут не выдают.",
        "caption": (
            "Обещать ничего не буду — гарантий тут не выдают. А позвать "
            "позову.\n\nLOOP открывается."
        ),
    },
    {
        "headline": "ЭТО ПИРАМИДА.\nВОПРОС ЗАКРЫТ.\nТЕПЕРЬ ПО ДЕЛУ:",
        "subline": "Открытие — уже скоро.",
        "caption": (
            "Да, это пирамида, вопрос закрыт. Теперь по делу — открытие уже "
            "скоро.\n\nLOOP на TON."
        ),
    },
)


def invite_variant(index: int) -> dict[str, str]:
    return INVITE_VARIANTS[index % len(INVITE_VARIANTS)]


LAUNCH_MONTHS_RU = (
    "",
    "ЯНВАРЯ",
    "ФЕВРАЛЯ",
    "МАРТА",
    "АПРЕЛЯ",
    "МАЯ",
    "ИЮНЯ",
    "ИЮЛЯ",
    "АВГУСТА",
    "СЕНТЯБРЯ",
    "ОКТЯБРЯ",
    "НОЯБРЯ",
    "ДЕКАБРЯ",
)


def launch_moment_ru(launch_at: datetime) -> tuple[str, str]:
    """The launch moment in Moscow words: ("5 АВГУСТА", "19:30 МСК").

    Derived rather than typed, so moving the launch is an env change and not
    an image-editing session.
    """
    if launch_at.tzinfo is None:
        launch_at = launch_at.replace(tzinfo=UTC)
    moscow = launch_at.astimezone(timezone(timedelta(hours=3)))
    return (
        f"{moscow.day} {LAUNCH_MONTHS_RU[moscow.month]}",
        f"{moscow.hour}:{moscow.minute:02d} МСК",
    )


def render_invite_card(
    *, first_name: str, username: str | None, launch_at: datetime, variant_index: int
) -> bytes:
    """The card a person sends when they invite someone in.

    One of a set of jokes rather than a single poster: the same three friends
    see the same invitation several times over a launch week, and a card that
    is always identical stops being read. The variant travels in the URL, so
    each share is a fresh draw and the image itself stays cacheable.
    """
    with RENDER_LIMIT:
        variant = invite_variant(variant_index)
        date_text, time_text = launch_moment_ru(launch_at)
        image = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        seed = int.from_bytes(
            hashlib.sha256(f"{first_name}:{variant_index}".encode()).digest()[:8], "big"
        )
        rng = random.Random(seed)  # noqa: S311 - deterministic visual noise, not security
        for _ in range(520):
            shade = rng.randint(14, 42)
            draw.point(
                (rng.randrange(CARD_WIDTH), rng.randrange(CARD_HEIGHT)),
                fill=(shade, shade, shade, rng.randint(60, 150)),
            )

        draw.text(
            (70, 64), "∞  LOOP", font=_font(30, bold=True), fill=(245, 245, 245), anchor="la"
        )
        draw.text(
            (CARD_WIDTH - 70, 68),
            "ПРИГЛАШЕНИЕ",
            font=_font(20, bold=True),
            fill=(142, 142, 142),
            anchor="ra",
        )

        _centered_text(
            draw,
            (CARD_WIDTH // 2, 430),
            variant["headline"],
            font=_font(76, bold=True),
            fill=(250, 250, 250),
            spacing=16,
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 640),
            variant["subline"],
            font=_font(30),
            fill=(150, 150, 150),
        )

        # Before the launch the card is a date to wait for; after it, a date
        # would be stale the moment it was true. The queue itself is the news.
        if launch_at > datetime.now(UTC):
            _centered_text(
                draw,
                (CARD_WIDTH // 2, 858),
                date_text,
                font=_font(92, bold=True),
                fill=(255, 255, 255),
            )
            _centered_text(
                draw,
                (CARD_WIDTH // 2, 946),
                f"ОТКРЫТИЕ · {time_text}",
                font=_font(20, bold=True),
                fill=(135, 135, 135),
            )
        else:
            _centered_text(
                draw,
                (CARD_WIDTH // 2, 858),
                "УЖЕ ИДЁТ",
                font=_font(92, bold=True),
                fill=(255, 255, 255),
            )
            _centered_text(
                draw,
                (CARD_WIDTH // 2, 946),
                "ОЧЕРЕДЬ ДВИЖЕТСЯ И ПЛАТИТ",
                font=_font(20, bold=True),
                fill=(135, 135, 135),
            )

        draw.line((70, 1176, CARD_WIDTH - 70, 1176), fill=(54, 54, 54), width=2)
        inviter = f"@{username}" if username else first_name
        draw.text(
            (70, 1222),
            f"ТЕБЯ ЗОВЁТ  {inviter.upper()}",
            font=_font(22, bold=True),
            fill=(212, 212, 212),
            anchor="la",
        )
        draw.text(
            (CARD_WIDTH - 70, 1222),
            "ВХОД УЖЕ ОТКРЫТ",
            font=_font(22, bold=True),
            fill=(212, 212, 212),
            anchor="ra",
        )
        draw.text(
            (CARD_WIDTH // 2, 1318),
            "LOOP · TONSUITE.ORG",
            font=_font(16, bold=True),
            fill=(95, 95, 95),
            anchor="ma",
        )

        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=CARD_JPEG_QUALITY, optimize=True)
        return output.getvalue()


def invite_caption(launch_at: datetime, variant_index: int) -> str:
    if launch_at > datetime.now(UTC):
        date_text, time_text = launch_moment_ru(launch_at)
        opening = f"Открытие {date_text.lower()} в {time_text.removesuffix(' МСК')} МСК."
    else:
        # "Открытие 5 августа" mailed on the seventh reads as an old flyer.
        opening = "Уже идёт: очередь движется и платит."
    return f"{invite_variant(variant_index)['caption']}\n\n{opening} Вход открыт."


def build_invite_inline(
    *,
    settings: Settings,
    referral_code: str,
    first_name: str,
    username: str | None,
    launch_at: datetime,
    variant_index: int,
) -> InlineQueryResultPhoto:
    image_url = (
        f"{settings.public_origin}/api/v1/prelaunch/cards/"
        f"{referral_code}-{variant_index}.jpg"
    )
    del first_name, username  # drawn into the image itself
    return InlineQueryResultPhoto(
        id=f"invite-{referral_code}-{variant_index}",
        photo_url=image_url,
        thumbnail_url=image_url,
        photo_width=CARD_WIDTH,
        photo_height=CARD_HEIGHT,
        title="Приглашение в LOOP",
        description=invite_variant(variant_index)["subline"],
        caption=invite_caption(launch_at, variant_index),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ЗАНЯТЬ МЕСТО",
                        url=result_deep_link(settings, referral_code),
                    )
                ]
            ]
        ),
    )


def render_duel_invite_card(
    *,
    first_name: str,
    username: str | None,
    opponent_stake_nano: int,
    receiver_chance_bps: int,
    profit_nano: int,
) -> bytes:
    """The card a player sends when calling someone out.

    Written from the receiver's side throughout — their stake, their odds,
    what they take home — because the person reading it in a group chat is
    deciding whether to answer, not admiring somebody else's terms.
    """
    with RENDER_LIMIT:
        image = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 255))
        draw = ImageDraw.Draw(image)
        seed = int.from_bytes(hashlib.sha256(first_name.encode()).digest()[:8], "big")
        rng = random.Random(seed)  # noqa: S311 - deterministic visual noise, not security
        for _ in range(520):
            shade = rng.randint(14, 42)
            draw.point(
                (rng.randrange(CARD_WIDTH), rng.randrange(CARD_HEIGHT)),
                fill=(shade, shade, shade, rng.randint(60, 150)),
            )
        # The orbits sit at a fixed height that lands exactly on the odds, so
        # this card takes the glow instead and keeps it above the headline.
        _draw_infinity(image, 205)
        draw = ImageDraw.Draw(image)

        draw.text(
            (70, 64), "∞  LOOP", font=_font(30, bold=True), fill=(245, 245, 245), anchor="la"
        )
        draw.text(
            (CARD_WIDTH - 70, 68),
            "ВЫЗОВ",
            font=_font(20, bold=True),
            fill=(142, 142, 142),
            anchor="ra",
        )

        _centered_text(
            draw,
            (CARD_WIDTH // 2, 400),
            "ТЕБЯ ВЫЗЫВАЮТ\nНА ДУЭЛЬ",
            font=_font(76, bold=True),
            fill=(250, 250, 250),
        )

        _centered_text(
            draw,
            (CARD_WIDTH // 2, 660),
            f"{format_gram(opponent_stake_nano)} GRAM",
            font=_font(112, bold=True),
            fill=(250, 250, 250),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 748),
            "ТВОЯ СТАВКА",
            font=_font(24, bold=True),
            fill=(135, 135, 135),
        )

        _centered_text(
            draw,
            (CARD_WIDTH // 2, 900),
            f"{receiver_chance_bps // 100}%",
            font=_font(84, bold=True),
            fill=(250, 250, 250),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 976),
            "ТВОИ ШАНСЫ",
            font=_font(24, bold=True),
            fill=(135, 135, 135),
        )

        _centered_text(
            draw,
            (CARD_WIDTH // 2, 1086),
            f"ПОБЕДА  ·  +{format_gram(profit_nano)} GRAM",
            font=_font(30, bold=True),
            fill=(212, 212, 212),
        )

        draw.line((70, 1176, CARD_WIDTH - 70, 1176), fill=(54, 54, 54), width=2)
        caller = f"@{username}" if username else first_name
        draw.text(
            (70, 1222),
            f"ВЫЗЫВАЕТ  {caller.upper()}",
            font=_font(22, bold=True),
            fill=(212, 212, 212),
            anchor="la",
        )
        draw.text(
            (CARD_WIDTH - 70, 1222),
            "ОТВЕТИТЬ МОЖНО РАЗ",
            font=_font(22, bold=True),
            fill=(212, 212, 212),
            anchor="ra",
        )
        draw.text(
            (CARD_WIDTH // 2, 1318),
            "LOOP · TONSUITE.ORG",
            font=_font(16, bold=True),
            fill=(95, 95, 95),
            anchor="ma",
        )

        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=CARD_JPEG_QUALITY, optimize=True)
        return output.getvalue()


def build_duel_invite_inline(
    *,
    settings: Settings,
    offer_id: str,
    accept_url: str,
    opponent_stake_nano: int,
    receiver_chance_bps: int,
    profit_nano: int,
    first_name: str,
) -> InlineQueryResultPhoto:
    image_url = (
        f"{settings.public_origin}/api/v1/duels/cards/{offer_id}.jpg?v={CARD_TEMPLATE_VERSION}"
    )
    stake = format_gram(opponent_stake_nano)
    return InlineQueryResultPhoto(
        id=f"duel-{offer_id}",
        photo_url=image_url,
        thumbnail_url=image_url,
        photo_width=CARD_WIDTH,
        photo_height=CARD_HEIGHT,
        title="Вызов на дуэль",
        description=f"Ставка {stake} GRAM · шансы {receiver_chance_bps // 100}%",
        caption=(
            f"{first_name} вызывает на дуэль.\n\n"
            f"Твоя ставка: {stake} GRAM\n"
            f"Твои шансы: {receiver_chance_bps // 100}%\n"
            f"Победа: +{format_gram(profit_nano)} GRAM"
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="ПРИНЯТЬ ВЫЗОВ", url=accept_url)]]
        ),
    )
