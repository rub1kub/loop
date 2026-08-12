"""Text and markup for the alert that tells a player their duel found an opponent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .bot import main_app_deep_link
from .config import Settings

KIND_DUEL_MATCHED = "duel_matched"
KIND_DUEL_REVEAL_SOON = "duel_reveal_soon"
KIND_REFERRAL_QUALIFIED = "referral_qualified"


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


def reveal_reminder_text(payload: dict[str, Any], now: datetime) -> str:
    """The last call before a duel expires unplayed.

    Missing the window is not a loss, it is a duel that never happened: both
    stakes go back and the match is void. Worth one message.
    """
    deadline = datetime.fromisoformat(str(payload["reveal_deadline"]))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    left = minutes_left(deadline, now)
    window = "меньше минуты" if left == 0 else f"{left} мин"
    return (
        "Ты ещё не открыл свою дуэль.\n\n"
        f"Осталось {window}. Если не откроет никто, ставки вернутся "
        "и дуэли не будет."
    )


def referral_text(payload: dict[str, Any]) -> str:
    confirmed = int(payload.get("qualified", 0))
    if payload.get("event") == "turn_accepted":
        return (
            "Ход принят. Цепочка продолжается.\n\n"
            f"Подтверждённых приглашений: {confirmed}."
        )
    return (
        "Твой друг подтвердил участие в LOOP.\n\n"
        f"Подтверждённых приглашений: {confirmed}."
    )
