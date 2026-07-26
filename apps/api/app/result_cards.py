from __future__ import annotations

import hashlib
import io
import math
import random
import threading
from dataclasses import dataclass
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
    demo: bool = False


def format_gram(nano: int, decimals: int = 3) -> str:
    value = nano / 1_000_000_000
    rendered = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return rendered.replace(".", ",")


def result_headline(mode: str) -> str:
    if mode == "bank":
        return "МОЙ ЦИКЛ\nЗАМКНУЛСЯ"
    if mode == "duel":
        return "Я ЗАБРАЛ\nDUEL"
    raise ValueError("unknown result card mode")


def result_caption(card: ResultCard) -> str:
    result = format_gram(card.result_nano)
    payout = format_gram(card.payout_nano)
    if card.mode == "bank":
        return (
            f"Мой цикл в LOOP замкнулся.\n\n"
            f"Выплата: {payout} GRAM\n"
            f"Разница к входу: +{result} GRAM\n\n"
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
    return InlineQueryResultPhoto(
        id=card.public_id,
        photo_url=image_url,
        thumbnail_url=image_url,
        photo_width=CARD_WIDTH,
        photo_height=CARD_HEIGHT,
        title="Результат LOOP",
        description=f"+{format_gram(card.result_nano)} GRAM",
        caption=result_caption(card),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ОТКРЫТЬ LOOP",
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
        return _render_result_card(facts)


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
        result_headline(facts.mode),
        font=_font(74, bold=True),
        fill=(250, 250, 250),
        spacing=-2,
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
        "РАЗНИЦА К ВХОДУ",
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
        f"ВЫПЛАТА  {format_gram(facts.payout_nano)} GRAM",
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
