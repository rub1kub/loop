import base64
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from tonsdk.boc import Cell

from app.chain_worker import (
    DUEL_PAYOUT,
    OPEN_OFFER,
    REVEAL,
    apply_transaction,
    decode_body,
)
from app.config import get_settings
from app.models import ChainEvent, Duel, DuelState, MatchmakingOffer, OfferState, User, Wallet


def body_b64(opcode: int, fields: list[tuple[int, int | str]]) -> str:
    cell = Cell()
    cell.bits.write_uint(opcode, 32)
    cell.bits.write_uint(1, 64)
    for bits, value in fields:
        if bits == 0:
            cell.bits.write_coins(int(value))
        else:
            cell.bits.write_uint(int(value), bits)
    return base64.b64encode(cell.to_boc(has_idx=False)).decode()


def transaction(
    lt: int,
    body: str,
    *,
    outputs: list[str] | None = None,
    timestamp: int = 1_800_000_000,
) -> dict[str, object]:
    return {
        "lt": str(lt),
        "hash": f"tx-{lt}",
        "now": timestamp,
        "emulated": False,
        "description": {
            "aborted": False,
            "compute_ph": {"success": True},
            "action": {"success": True},
        },
        "in_msg": {"message_content": {"body": body, "hash": f"body-{lt}"}},
        "out_msgs": [
            {"message_content": {"body": output, "hash": f"out-{index}"}}
            for index, output in enumerate(outputs or [])
        ],
    }


def open_body(offer_id: int, counter_offer_id: int) -> str:
    return body_b64(
        OPEN_OFFER,
        [
            (64, offer_id),
            (256, 123),
            (16, 2500),
            (0, 4_000_000_000),
            (32, 1_800_000_900),
            (64, counter_offer_id),
        ],
    )


def reveal_body(duel_id: int, offer_id: int) -> str:
    return body_b64(REVEAL, [(64, duel_id), (64, offer_id), (256, offer_id + 99)])


def payout_body(duel_id: int, offer_id: int) -> str:
    return body_b64(DUEL_PAYOUT, [(64, duel_id), (64, offer_id), (8, 1)])


def test_decodes_contract_layout() -> None:
    decoded = decode_body(open_body(100, 900))
    assert decoded["offer_id"] == 100
    assert decoded["counter_offer_id"] == 900
    assert decoded["total_pool_nano"] == 4_000_000_000


@pytest.mark.asyncio
async def test_projection_is_idempotent_and_uses_terminal_payout(app) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        first_user = User(telegram_id=1001, first_name="First")
        second_user = User(telegram_id=1002, first_name="Second")
        db.add_all([first_user, second_user])
        await db.flush()
        first_wallet = Wallet(
            user_id=first_user.id,
            network=-3,
            address="0:" + "10" * 32,
            public_key="20" * 32,
        )
        second_wallet = Wallet(
            user_id=second_user.id,
            network=-3,
            address="0:" + "30" * 32,
            public_key="40" * 32,
        )
        db.add_all([first_wallet, second_wallet])
        await db.flush()
        expires = datetime.now(UTC) + timedelta(minutes=15)
        counter = MatchmakingOffer(
            onchain_offer_id=900,
            user_id=first_user.id,
            wallet_id=first_wallet.id,
            network=-3,
            contract_address=settings.ton_contract_address,
            chance_bps=7500,
            total_pool_nano=4_000_000_000,
            stake_nano=3_000_000_000,
            commitment_hex="aa" * 32,
            state=OfferState.OPEN.value,
            expires_at=expires,
        )
        newcomer = MatchmakingOffer(
            onchain_offer_id=100,
            user_id=second_user.id,
            wallet_id=second_wallet.id,
            network=-3,
            contract_address=settings.ton_contract_address,
            chance_bps=2500,
            total_pool_nano=4_000_000_000,
            stake_nano=1_000_000_000,
            commitment_hex="bb" * 32,
            counter_offer_id=900,
            expires_at=expires,
        )
        db.add_all([counter, newcomer])
        await db.commit()

        opened = transaction(10, open_body(100, 900))
        assert await apply_transaction(db, settings, opened) is True
        await db.commit()
        duel = await db.scalar(select(Duel))
        assert duel is not None
        assert duel.onchain_duel_id == 900
        assert duel.offer_a_id == newcomer.id
        assert duel.offer_b_id == counter.id

        assert await apply_transaction(db, settings, opened) is False
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(ChainEvent)) == 1

        assert await apply_transaction(db, settings, transaction(11, reveal_body(900, 900)))
        await db.commit()
        second_reveal = transaction(
            12,
            reveal_body(900, 100),
            outputs=[payout_body(900, 100)],
        )
        assert await apply_transaction(db, settings, second_reveal)
        await db.commit()

        await db.refresh(duel)
        await db.refresh(counter)
        await db.refresh(newcomer)
        assert duel.state == DuelState.SETTLED.value
        assert duel.winner_wallet == second_wallet.address
        assert counter.state == OfferState.SETTLED.value
        assert newcomer.state == OfferState.SETTLED.value
