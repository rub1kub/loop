from datetime import UTC, datetime

import pytest

from app.config import get_settings
from app.control_state import application_control
from app.modules.bank.models import BankPosition, BankPositionStatus
from app.modules.bank.pulse import bank_queue_pulse, bank_queue_pulse_text, gross_needed
from app.schemas import BankQueuePulseView


def position(position_id: int, queue_index: int, remaining_nano: int) -> BankPosition:
    target = 2_000_000_000
    return BankPosition(
        position_id=position_id,
        owner_wallet=f"0:{position_id:064x}",
        network=get_settings().ton_network_id,
        contract_address=get_settings().bank_contract_address,
        query_id=position_id + 10_000,
        principal_nano=1_000_000_000,
        multiplier_bps=20_000,
        target_payout_nano=target,
        funded_amount_nano=target - remaining_nano,
        remaining_amount_nano=remaining_nano,
        queue_index=queue_index,
        current_status=BankPositionStatus.PARTIALLY_FUNDED.value,
        confirmed_at=datetime.now(UTC),
    )


def test_gross_needed_rounds_up_after_the_protocol_fee() -> None:
    assert gross_needed(260_000_000, 1_000) == 288_888_889


def test_public_pulse_uses_two_decimal_places_and_a_dot() -> None:
    text = bank_queue_pulse_text(
        BankQueuePulseView(
            active_positions=2,
            minimum_entry_nano=1_000_000_000,
            minimum_entry_payouts=0,
            next_payout_gross_nano=4_389_000_000,
            updated_at=datetime.now(UTC),
        )
    )
    assert "4.38 GRAM" in text
    assert "4,389" not in text


@pytest.mark.asyncio
async def test_queue_pulse_counts_what_the_minimum_entry_really_closes(app) -> None:
    async with app.state.session_factory() as db:
        db.add_all(
            [
                position(101, 0, 260_000_000),
                position(102, 1, 520_000_000),
                position(103, 2, 1_000_000_000),
            ]
        )
        await db.commit()

        pulse = await bank_queue_pulse(db, get_settings())

    assert pulse.active_positions == 3
    assert pulse.bank_enabled is True
    assert pulse.minimum_entry_payouts == 2
    assert pulse.next_payout_gross_nano == 288_888_889
    assert "закроет 2 позиции" in bank_queue_pulse_text(pulse)


@pytest.mark.asyncio
async def test_queue_pulse_exposes_the_live_bank_switch(app) -> None:
    async with app.state.session_factory() as db:
        control = await application_control(db)
        control.bank_enabled = False
        await db.commit()

        pulse = await bank_queue_pulse(db, get_settings())

    assert pulse.bank_enabled is False
