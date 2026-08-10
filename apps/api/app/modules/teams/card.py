import hashlib
import io
import math
from functools import lru_cache
from pathlib import Path

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultPhoto
from PIL import Image, ImageDraw, ImageFont

from ...config import Settings
from .schemas import TeamEntryView

CARD_WIDTH = 1080
CARD_HEIGHT = 1080
CARD_VERSION = 2
FONT_REGULAR = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)
FONT_BOLD = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_BOLD if bold else FONT_REGULAR:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _fit(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = start
    while size > 36:
        font = _font(size, bold=True)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 4
    return _font(36, bold=True)


def _mark(draw: ImageDraw.ImageDraw, mark: int, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    cx, cy = (left + right) // 2, (top + bottom) // 2
    radius = min(right - left, bottom - top) // 2
    width = 8
    shape = mark % 6
    if shape == 0:
        draw.polygon(
            [(cx, top), (right, cy), (cx, bottom), (left, cy)],
            outline="white",
            width=width,
        )
    elif shape == 1:
        draw.ellipse(box, outline="white", width=width)
        draw.ellipse(
            (cx - radius // 3, cy - radius // 3, cx + radius // 3, cy + radius // 3),
            fill="white",
        )
    elif shape == 2:
        draw.rounded_rectangle(box, radius=radius // 3, outline="white", width=width)
        draw.line((left + 30, bottom - 30, right - 30, top + 30), fill="white", width=width)
    elif shape == 3:
        draw.arc((left, cy - radius // 2, cx + 12, cy + radius // 2), 200, 520, "white", width)
        draw.arc((cx - 12, cy - radius // 2, right, cy + radius // 2), 20, 340, "white", width)
    elif shape == 4:
        draw.line((cx, top, cx, bottom), fill="white", width=width)
        draw.line((left, cy, right, cy), fill="white", width=width)
        draw.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill="white")
    else:
        points = []
        for index in range(8):
            angle = index * 45
            inner = radius // 2 if index % 2 else radius
            points.append(
                (
                    cx + int(math.cos(math.radians(angle - 90)) * inner),
                    cy + int(math.sin(math.radians(angle - 90)) * inner),
                )
            )
        draw.polygon(points, outline="white", width=width)


def format_gram(nano: int) -> str:
    return f"{nano / 1_000_000_000:.2f}".rstrip("0").rstrip(".")


@lru_cache(maxsize=256)
def render_team_card(
    name: str,
    mark: int,
    rank: int,
    flow_nano: int,
    member_count: int,
) -> bytes:
    image = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), "black")
    draw = ImageDraw.Draw(image)
    muted = (135, 135, 140)
    draw.text((72, 64), "∞  LOOP · КОМАНДЫ", fill="white", font=_font(30, bold=True))
    draw.text((72, 114), "НЕДЕЛЬНЫЙ ЗАЧЁТ BANK", fill=muted, font=_font(24))
    _mark(draw, mark, (72, 230, 232, 390))
    draw.text((272, 260), name, fill="white", font=_fit(draw, name, 720, 86))
    draw.line((72, 470, 1008, 470), fill=(45, 45, 48), width=2)
    draw.text((72, 540), f"#{rank}", fill="white", font=_font(116, bold=True))
    draw.text((78, 672), "МЕСТО СЕЙЧАС", fill=muted, font=_font(24, bold=True))
    flow = format_gram(flow_nano)
    flow_font = _fit(draw, flow, 450, 116)
    draw.text((552, 540), flow, fill="white", font=flow_font)
    draw.text((558, 672), "GRAM ЗА НЕДЕЛЮ", fill=muted, font=_font(24, bold=True))
    draw.line((72, 790, 1008, 790), fill=(45, 45, 48), width=2)
    draw.text(
        (72, 850),
        f"{member_count} УЧАСТНИКОВ. ОДНО ДВИЖЕНИЕ.",
        fill="white",
        font=_font(31, bold=True),
    )
    draw.text((72, 918), "ВСТУПАЙ. ИЛИ ОБОЙДИ НАС.", fill=muted, font=_font(27))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    return buffer.getvalue()


def card_url(settings: Settings, team: TeamEntryView) -> str:
    version = hashlib.sha256(
        (
            f"{CARD_VERSION}:{team.name}:{team.mark}:"
            f"{team.flow_nano}:{team.rank}:{team.member_count}"
        ).encode()
    ).hexdigest()[:12]
    return f"{settings.public_origin}/api/v1/team-cards/{team.slug}.jpg?v={version}"


def build_team_invite_inline(
    *,
    settings: Settings,
    team: TeamEntryView,
    token: str,
    referral_code: str,
    inviter_name: str,
) -> InlineQueryResultPhoto:
    image_url = card_url(settings, team)
    start = f"team_{token}-ref_{referral_code}"
    deep_link = f"https://t.me/{settings.bot_username.removeprefix('@')}?startapp={start}"
    return InlineQueryResultPhoto(
        id=hashlib.sha256(f"team:{team.id}:{token}".encode()).hexdigest()[:32],
        photo_url=image_url,
        thumbnail_url=image_url,
        photo_width=CARD_WIDTH,
        photo_height=CARD_HEIGHT,
        title=f"Команда {team.name}",
        description=f"#{team.rank} · {format_gram(team.flow_nano)} GRAM за неделю",
        caption=(
            f"{inviter_name} зовёт тебя в команду {team.name}.\n\n"
            f"Сейчас #{team.rank}. За неделю подтверждено "
            f"{format_gram(team.flow_nano)} GRAM.\n\n"
            "Вступай — или собирай свою команду и обходи."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="ВСТУПИТЬ В КОМАНДУ", url=deep_link)]]
        ),
    )
