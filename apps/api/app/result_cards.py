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
CARD_TEMPLATE_VERSION = 1
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


def result_caption(card: ResultCard) -> str:
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
    return (
        f"Я забрал DUEL в LOOP.\n\n"
        f"Выплата: {payout} GRAM\n"
        f"Разница к входу: +{result} GRAM\n\n"
        "Результат подтверждён."
    )


def result_card_image_url(settings: Settings, card: ResultCard) -> str:
    return f"{settings.public_origin}/api/v1/results/cards/{card.public_id}.jpg"


def result_deep_link(settings: Settings, referral_code: str | None) -> str:
    base = f"https://t.me/{settings.bot_username.removeprefix('@')}?startapp"
    return f"{base}=ref_{referral_code}" if referral_code else base


def build_result_inline(
    card: ResultCard,
    settings: Settings,
    referral_code: str | None,
) -> InlineQueryResultPhoto:
    image_url = result_card_image_url(settings, card)
    entry = card.mode == "bank_entry"
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
            else f"+{format_gram(card.payout_nano)} GRAM"
        ),
        caption=result_caption(card),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ОТКРЫТЬ LOOP",
                        url=result_deep_link(settings, None if entry else referral_code),
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
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 610),
        result_headline(facts.mode, facts.public_id),
        font=_font(74, bold=True),
        fill=(250, 250, 250),
        spacing=-2,
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 790),
        f"+{format_gram(facts.payout_nano)} GRAM",
        font=_font(82, bold=True),
        fill=(255, 255, 255),
    )
    _centered_text(
        draw,
        (CARD_WIDTH // 2, 868),
        "ВЫПЛАЧЕНО",
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


def render_invite_card(*, first_name: str, username: str | None, launch_at: datetime) -> bytes:
    """The card a person sends when they invite someone in.

    Personalised with the inviter's name: an invitation from a person carries
    further than an advert from a bot.
    """
    with RENDER_LIMIT:
        date_text, time_text = launch_moment_ru(launch_at)
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
            (CARD_WIDTH // 2, 360),
            "ФИНАНСОВАЯ ПИРАМИДА",
            font=_font(30, bold=True),
            fill=(150, 150, 150),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 520),
            "ОТКРЫТИЕ",
            font=_font(72, bold=True),
            fill=(250, 250, 250),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 660),
            date_text,
            font=_font(104, bold=True),
            fill=(255, 255, 255),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 780),
            time_text,
            font=_font(44, bold=True),
            fill=(200, 200, 200),
        )

        _centered_text(
            draw,
            (CARD_WIDTH // 2, 960),
            "Очередь выплат на TON. Код открыт.",
            font=_font(28),
            fill=(150, 150, 150),
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


def invite_caption(launch_at: datetime) -> str:
    date_text, time_text = launch_moment_ru(launch_at)
    return (
        f"LOOP открывается {date_text.lower()} в {time_text.removesuffix(' МСК')} МСК.\n\n"
        "Финансовая пирамида на TON: заходишь, вносишь, встаёшь в очередь — "
        "выплата приходит сама.\n\n"
        "Вход уже открыт. Займи место до толпы."
    )


def build_invite_inline(
    *,
    settings: Settings,
    referral_code: str,
    first_name: str,
    username: str | None,
    launch_at: datetime,
) -> InlineQueryResultPhoto:
    image_url = f"{settings.public_origin}/api/v1/prelaunch/cards/{referral_code}.jpg"
    del first_name, username  # drawn into the image itself
    return InlineQueryResultPhoto(
        id=f"invite-{referral_code}",
        photo_url=image_url,
        thumbnail_url=image_url,
        photo_width=CARD_WIDTH,
        photo_height=CARD_HEIGHT,
        title="Приглашение в LOOP",
        description="Открытие · вход уже открыт",
        caption=invite_caption(launch_at),
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
