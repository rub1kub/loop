from __future__ import annotations

import hashlib
import html
import io
import json
import random
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .config import Settings
from .models import NotificationOutbox, User
from .result_cards import CARD_JPEG_QUALITY, CARD_WIDTH, _centered_text, _font, format_gram
from .ton import explorer_transaction_url

KIND_PUBLIC_FEED = "public_feed"
PUBLIC_FEED_TEMPLATE_VERSION = 1
PUBLIC_CARD_HEIGHT = 1080
PublicEventKind = Literal["bank_entry", "bank_payout", "duel_entry", "duel_payout"]

EVENT_COPY: dict[PublicEventKind, tuple[str, str, str]] = {
    "bank_entry": ("НОВАЯ ПОЗИЦИЯ", "В ПИРАМИДЕ", "BANK"),
    "bank_payout": ("ЦИКЛ ЗАМКНУЛСЯ", "ВЫПЛАЧЕНО", "BANK"),
    "duel_entry": ("НОВЫЙ ВЫЗОВ", "СТАВКА", "DUEL"),
    "duel_payout": ("DUEL ЗАВЕРШЁН", "ПОЛУЧЕНО", "DUEL"),
}


@dataclass(frozen=True)
class PublicFeedFacts:
    event_id: str
    event_kind: PublicEventKind
    amount_nano: int
    actor: str
    result_nano: int = 0
    queue_position: int | None = None


def public_actor_name(user: User | None) -> str:
    """Only expose a Telegram identity that the person already made public."""
    if user and user.username:
        username = user.username.strip().lstrip("@")
        if username:
            return f"@{username}"
    return "Участник LOOP"


def _payload(
    event_kind: PublicEventKind,
    amount_nano: int,
    network: int,
    tx_hash: str,
    *,
    result_nano: int = 0,
    queue_position: int | None = None,
) -> str:
    if event_kind not in EVENT_COPY:
        raise ValueError("unknown public feed event")
    if amount_nano <= 0 or result_nano < 0:
        raise ValueError("public feed amounts must be positive")
    return json.dumps(
        {
            "event_kind": event_kind,
            "amount_nano": amount_nano,
            "result_nano": result_nano,
            "queue_position": queue_position,
            "proof_url": explorer_transaction_url(network, tx_hash),
            "template_version": PUBLIC_FEED_TEMPLATE_VERSION,
        },
        separators=(",", ":"),
    )


async def enqueue_public_feed(
    db: Any,
    settings: Settings,
    *,
    user_id: str | None,
    event_kind: PublicEventKind,
    event_key: str,
    amount_nano: int,
    network: int,
    tx_hash: str,
    result_nano: int = 0,
    queue_position: int | None = None,
) -> NotificationOutbox | None:
    if not settings.public_feed_chat_id or user_id is None:
        return None
    dedupe_key = f"public_feed:{event_key}"
    existing: NotificationOutbox | None = await db.scalar(
        select(NotificationOutbox).where(NotificationOutbox.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return existing
    item = NotificationOutbox(
        user_id=user_id,
        kind=KIND_PUBLIC_FEED,
        dedupe_key=dedupe_key,
        payload_json=_payload(
            event_kind,
            amount_nano,
            network,
            tx_hash,
            result_nano=result_nano,
            queue_position=queue_position,
        ),
    )
    try:
        async with db.begin_nested():
            db.add(item)
            await db.flush()
    except IntegrityError:
        raced: NotificationOutbox | None = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.dedupe_key == dedupe_key)
        )
        return raced
    return item


def public_feed_facts(outbox: NotificationOutbox, user: User | None) -> PublicFeedFacts:
    payload = json.loads(outbox.payload_json)
    event_kind = payload.get("event_kind")
    if event_kind not in EVENT_COPY:
        raise ValueError("unknown public feed event")
    return PublicFeedFacts(
        event_id=outbox.id,
        event_kind=event_kind,
        amount_nano=int(payload["amount_nano"]),
        actor=public_actor_name(user),
        result_nano=int(payload.get("result_nano") or 0),
        queue_position=payload.get("queue_position"),
    )


def public_feed_caption(facts: PublicFeedFacts) -> str:
    actor = html.escape(facts.actor)
    amount = format_gram(facts.amount_nano)
    if facts.event_kind == "bank_entry":
        position = f" · место №{facts.queue_position}" if facts.queue_position else ""
        return (
            f"🏺 <b>{actor} вошёл в пирамиду</b>\n\n"
            f"Взнос: {amount} GRAM{position}\nТеперь он внутри цикла."
        )
    if facts.event_kind == "bank_payout":
        return (
            "∞ <b>Цикл замкнулся</b>\n\n"
            f"{actor} получил {amount} GRAM из BANK.\nВыплата подтверждена сетью."
        )
    if facts.event_kind == "duel_entry":
        return (
            f"⚔️ <b>{actor} вошёл в DUEL</b>\n\n"
            f"Ставка: {amount} GRAM\nВызов уже в игре."
        )
    result = format_gram(facts.result_nano)
    return (
        "⚔️ <b>DUEL завершён</b>\n\n"
        f"{actor} получил {amount} GRAM.\nРезультат: +{result} GRAM."
    )


def public_feed_markup(
    settings: Settings, facts: PublicFeedFacts, proof_url: str
) -> InlineKeyboardMarkup:
    username = settings.bot_username.strip().lstrip("@")
    start = "duel" if facts.event_kind.startswith("duel_") else "bank"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ОТКРЫТЬ LOOP",
                    url=f"https://t.me/{username}?startapp={start}",
                ),
                InlineKeyboardButton(text="ПРОВЕРИТЬ", url=proof_url),
            ]
        ]
    )


def public_feed_card_url(settings: Settings, outbox_id: str) -> str:
    return (
        f"{settings.public_origin}/api/v1/public-feed/cards/{outbox_id}.jpg"
        f"?v={PUBLIC_FEED_TEMPLATE_VERSION}"
    )


_RENDER_LIMIT = threading.BoundedSemaphore(2)


@lru_cache(maxsize=128)
def render_public_feed_card(facts: PublicFeedFacts) -> bytes:
    with _RENDER_LIMIT:
        title, label, mode = EVENT_COPY[facts.event_kind]
        image = Image.new("RGB", (CARD_WIDTH, PUBLIC_CARD_HEIGHT), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        seed = int.from_bytes(hashlib.sha256(facts.event_id.encode()).digest()[:8], "big")
        rng = random.Random(seed)  # noqa: S311 - deterministic visual texture only
        for _ in range(680):
            shade = rng.randint(18, 54)
            draw.point(
                (rng.randrange(CARD_WIDTH), rng.randrange(PUBLIC_CARD_HEIGHT)),
                fill=(shade,) * 3,
            )

        draw.text((70, 66), "∞  LOOP", font=_font(30, bold=True), fill=(245, 245, 245))
        draw.text(
            (CARD_WIDTH - 70, 72),
            mode,
            font=_font(20, bold=True),
            fill=(145, 145, 145),
            anchor="ra",
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 285),
            title,
            font=_font(58, bold=True),
            fill=(246, 246, 246),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 505),
            format_gram(facts.amount_nano),
            font=_font(142, bold=True),
            fill=(255, 255, 255),
        )
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 615),
            f"GRAM · {label}",
            font=_font(24, bold=True),
            fill=(145, 145, 145),
        )
        actor_line = facts.actor
        if facts.queue_position and facts.event_kind == "bank_entry":
            actor_line = f"{actor_line}  ·  № {facts.queue_position}"
        _centered_text(
            draw,
            (CARD_WIDTH // 2, 805),
            actor_line,
            font=_font(34, bold=True),
            fill=(225, 225, 225),
        )
        draw.line((70, 930, CARD_WIDTH - 70, 930), fill=(52, 52, 52), width=2)
        draw.text(
            (70, 984),
            "ПОДТВЕРЖДЕНО СЕТЬЮ",
            font=_font(18, bold=True),
            fill=(112, 112, 112),
        )
        draw.text(
            (CARD_WIDTH - 70, 984),
            "TONSUITE.ORG",
            font=_font(18, bold=True),
            fill=(112, 112, 112),
            anchor="ra",
        )
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=CARD_JPEG_QUALITY, optimize=True)
        return output.getvalue()
