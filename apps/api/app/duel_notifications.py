"""Text and markup for the alert that tells a player their duel found an opponent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .bot import main_app_deep_link
from .config import Settings

KIND_DUEL_MATCHED = "duel_matched"


def minutes_left(deadline: datetime, now: datetime) -> int:
    remaining = (deadline - now).total_seconds()
    if remaining < 60:
        return 0
    return int(remaining // 60)


def match_notification_text(payload: dict[str, Any], now: datetime) -> str:
    deadline = datetime.fromisoformat(str(payload["reveal_deadline"]))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    left = minutes_left(deadline, now)
    window = "меньше минуты" if left == 0 else f"{left} мин"
    return (
        "Соперник найден. Дуэль началась.\n\n"
        f"Вернись в LOOP — на исход осталось {window}. "
        "Не откроешь ты, откроет он: пул целиком уйдёт сопернику."
    )


def match_notification_markup(settings: Settings) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ОТКРЫТЬ LOOP",
                    url=main_app_deep_link(settings.bot_username),
                )
            ]
        ]
    )
