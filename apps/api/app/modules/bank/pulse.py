from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ...config import Settings
from ...control_state import effective_contract_fee
from ...schemas import BankQueuePulseView
from .models import BankPosition, BankPositionStatus

QUEUE_STATES = (
    BankPositionStatus.QUEUED.value,
    BankPositionStatus.PARTIALLY_FUNDED.value,
    BankPositionStatus.COMPLETED.value,
)


def gross_needed(net_nano: int, fee_bps: int) -> int:
    """Gross confirmed deposits needed to put ``net_nano`` into the queue."""

    distributable_bps = 10_000 - fee_bps
    if net_nano <= 0:
        return 0
    if distributable_bps <= 0:
        return 0
    return (net_nano * 10_000 + distributable_bps - 1) // distributable_bps


async def bank_queue_pulse(db: Any, settings: Settings) -> BankQueuePulseView:
    """One source of truth for the in-app and Telegram queue pulse."""

    filters = (
        BankPosition.network == settings.ton_network_id,
        BankPosition.contract_address == settings.bank_contract_address,
        BankPosition.current_status.in_(QUEUE_STATES),
        BankPosition.queue_index.is_not(None),
    )
    active_positions = int(
        await db.scalar(select(func.count()).select_from(BankPosition).where(*filters)) or 0
    )
    positions = (
        await db.scalars(
            select(BankPosition)
            .where(*filters)
            .order_by(
                BankPosition.queue_index,
                BankPosition.confirmed_at,
                BankPosition.position_id,
            )
            # One contract call cannot close more positions than this. Loading
            # the whole tail on every five-second UI poll would get slower as
            # the product succeeds while changing no answer on the screen.
            .limit(81)
        )
    ).all()
    fee_bps = await effective_contract_fee(
        db,
        mode="bank",
        network=settings.ton_network_id,
        address=settings.bank_contract_address,
        fallback=settings.bank_fee_bps,
    )
    minimum_entry = settings.bank_min_principal_nano
    distributable = minimum_entry * (10_000 - fee_bps) // 10_000
    left = distributable
    closed = 0
    for position in positions:
        if position.remaining_amount_nano > left:
            break
        left -= position.remaining_amount_nano
        closed += 1

    next_remaining = positions[0].remaining_amount_nano if positions else 0
    return BankQueuePulseView(
        active_positions=active_positions,
        minimum_entry_nano=minimum_entry,
        minimum_entry_payouts=closed,
        next_payout_gross_nano=gross_needed(next_remaining, fee_bps),
        updated_at=datetime.now(UTC),
    )


def bank_queue_pulse_text(pulse: BankQueuePulseView) -> str:
    minimum = _format_gram(pulse.minimum_entry_nano)
    if pulse.active_positions == 0:
        movement = "Очередь ждёт первую позицию."
    elif pulse.minimum_entry_payouts == 1:
        movement = f"Следующий вход от {minimum} GRAM закроет ближайшую позицию."
    elif pulse.minimum_entry_payouts > 1:
        movement = (
            f"Следующий вход от {minimum} GRAM закроет "
            f"{pulse.minimum_entry_payouts} {_positions_word(pulse.minimum_entry_payouts)}."
        )
    else:
        shown = _format_gram(pulse.next_payout_gross_nano)
        movement = f"До ближайшей выплаты: {shown} GRAM новых входов."
    return (
        "∞ <b>Живой пульс BANK</b>\n\n"
        f"{movement}\n"
        f"Сейчас в очереди: {pulse.active_positions}.\n\n"
        "Обновляется после каждого подтверждённого взноса."
    )


def _positions_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "позицию"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "позиции"
    return "позиций"


def _format_gram(amount_nano: int) -> str:
    # Telegram readers mistook the decimal comma in `4,389` for a thousands
    # separator. Keep the public counter deliberately coarse and use a dot.
    hundredths = amount_nano // 10_000_000
    whole, fraction = divmod(hundredths, 100)
    if fraction == 0:
        return str(whole)
    return f"{whole}.{fraction:02d}".rstrip("0")
