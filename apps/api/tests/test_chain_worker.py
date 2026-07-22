import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from tonsdk.boc import Cell

from app.chain_worker import (
    BANK_CREATE_POSITION,
    BANK_PAYOUT,
    DUEL_OPEN_OFFER,
    DUEL_PAYOUT,
    DUEL_REVEAL,
    ProjectionResult,
    apply_transaction,
    decode_body,
)
from app.config import get_settings
from app.models import User, Wallet
from app.modules.bank.models import BankChainEvent, BankPosition, BankPositionStatus
from app.modules.duel.models import (
    Duel,
    DuelChainEvent,
    DuelOffer,
    DuelState,
    OfferState,
)


def body_b64(opcode: int, fields: list[tuple[int, int]]) -> str:
    cell = Cell()
    cell.bits.write_uint(opcode, 32)
    cell.bits.write_uint(1, 64)
    for bits, value in fields:
        if bits == 0:
            cell.bits.write_coins(value)
        else:
            cell.bits.write_uint(value, bits)
    return base64.b64encode(cell.to_boc(has_idx=False)).decode()


def transaction(
    account: str,
    source: str,
    lt: int,
    body: str,
    value_nano: int,
    *,
    outputs: list[tuple[str, str, int]] | None = None,
    finalized: bool = True,
) -> dict[str, object]:
    return {
        "account": account,
        "lt": str(lt),
        "hash": f"tx-{lt}",
        "now": 1_800_000_000,
        "emulated": False,
        "mc_block_seqno": 12_345 if finalized else 0,
        "description": {
            "aborted": False,
            "compute_ph": {"success": True},
            "action": {"success": True},
        },
        "in_msg": {
            "source": source,
            "value": str(value_nano),
            "message_content": {"body": body},
        },
        "out_msgs": [
            {
                "destination": destination,
                "value": str(value),
                "message_content": {"body": output_body},
            }
            for destination, output_body, value in (outputs or [])
        ],
    }


def bank_create_body(position_id: int, principal: int, multiplier: int) -> str:
    return body_b64(
        BANK_CREATE_POSITION,
        [(64, position_id), (0, principal), (16, multiplier)],
    )


def bank_payout_body(position_id: int, principal: int, target: int) -> str:
    return body_b64(BANK_PAYOUT, [(64, position_id), (0, principal), (0, target)])


def duel_open_body(offer: DuelOffer) -> str:
    return body_b64(
        DUEL_OPEN_OFFER,
        [
            (64, offer.onchain_offer_id),
            (256, int(offer.commitment_hex, 16)),
            (16, offer.chance_bps),
            (0, offer.total_pool_nano),
            (32, int(offer.expires_at.timestamp())),
            (64, offer.counter_offer_id),
        ],
    )


def duel_reveal_body(duel_id: int, offer_id: int) -> str:
    return body_b64(DUEL_REVEAL, [(64, duel_id), (64, offer_id), (256, 777)])


def duel_payout_body(duel_id: int, offer_id: int) -> str:
    return body_b64(DUEL_PAYOUT, [(64, duel_id), (64, offer_id), (8, 1)])


def test_decodes_independent_bank_and_duel_layouts() -> None:
    bank = decode_body(bank_create_body(101, 2_000_000_000, 15_000))
    duel = decode_body(
        body_b64(
            DUEL_OPEN_OFFER,
            [(64, 202), (256, 123), (16, 2500), (0, 4_000_000_000), (32, 99), (64, 0)],
        )
    )
    assert bank == {
        "opcode": BANK_CREATE_POSITION,
        "query_id": 1,
        "position_id": 101,
        "principal_nano": 2_000_000_000,
        "multiplier_bps": 15_000,
    }
    assert duel["offer_id"] == 202
    assert duel["chance_bps"] == 2500


@pytest.mark.asyncio
async def test_bank_projection_is_fifo_proof_bound_and_idempotent(app) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        older_user = User(telegram_id=1001, first_name="Older")
        newer_user = User(telegram_id=1002, first_name="Newer")
        db.add_all([older_user, newer_user])
        await db.flush()
        older_wallet = Wallet(
            user_id=older_user.id,
            network=-3,
            address="0:" + "1a" * 32,
            public_key="2a" * 32,
        )
        newer_wallet = Wallet(
            user_id=newer_user.id,
            network=-3,
            address="0:" + "1b" * 32,
            public_key="2b" * 32,
        )
        db.add_all([older_wallet, newer_wallet])
        await db.flush()
        older = BankPosition(
            position_id=100,
            query_id=100,
            user_id=older_user.id,
            wallet_id=older_wallet.id,
            owner_wallet=older_wallet.address,
            network=-3,
            contract_address=settings.bank_contract_address,
            principal_nano=1_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=1_250_000_000,
            funded_amount_nano=250_000_000,
            remaining_amount_nano=1_000_000_000,
            queue_index=0,
            current_status=BankPositionStatus.PARTIALLY_FUNDED.value,
        )
        newer = BankPosition(
            position_id=101,
            query_id=1,
            user_id=newer_user.id,
            wallet_id=newer_wallet.id,
            owner_wallet=newer_wallet.address,
            network=-3,
            contract_address=settings.bank_contract_address,
            principal_nano=2_000_000_000,
            multiplier_bps=15_000,
            target_payout_nano=3_000_000_000,
            remaining_amount_nano=3_000_000_000,
        )
        db.add_all([older, newer])
        await db.commit()

        tx = transaction(
            settings.bank_contract_address,
            newer_wallet.address,
            10,
            bank_create_body(101, 2_000_000_000, 15_000),
            2_080_000_000,
            outputs=[
                (
                    older_wallet.address,
                    bank_payout_body(100, 1_000_000_000, 1_250_000_000),
                    1_250_000_000,
                )
            ],
        )
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(older)
        await db.refresh(newer)
        assert older.current_status == BankPositionStatus.PAYOUT_SENT.value
        assert newer.queue_index == 1
        assert newer.current_status == BankPositionStatus.PARTIALLY_FUNDED.value
        assert newer.funded_amount_nano == 980_000_000
        assert newer.remaining_amount_nano == 2_020_000_000
        assert await db.scalar(select(func.count()).select_from(BankChainEvent)) == 1
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.IGNORED


@pytest.mark.asyncio
async def test_bank_projection_tracks_permissionless_position_and_detaches_stale_intent(
    app,
) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        user = User(telegram_id=1003, first_name="Bank")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "1c" * 32,
            public_key="2c" * 32,
        )
        db.add(wallet)
        await db.flush()
        position = BankPosition(
            position_id=102,
            query_id=1,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=-3,
            contract_address=settings.bank_contract_address,
            principal_nano=1_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=1_250_000_000,
            remaining_amount_nano=1_250_000_000,
        )
        db.add(position)
        await db.commit()
        tx = transaction(
            settings.bank_contract_address,
            "0:" + "ff" * 32,
            11,
            bank_create_body(102, 1_000_000_000, 12_500),
            1_080_000_000,
        )
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(position)
        assert position.user_id is None
        assert position.wallet_id is None
        assert position.owner_wallet == "0:" + "ff" * 32
        assert position.current_status == BankPositionStatus.PARTIALLY_FUNDED.value
        assert position.funded_amount_nano == 990_000_000
        assert position.remaining_amount_nano == 260_000_000


@pytest.mark.asyncio
async def test_bank_projection_claims_position_for_verified_wallet(app) -> None:
    settings = get_settings()
    owner = "0:" + "2c" * 32
    async with app.state.session_factory() as db:
        user = User(telegram_id=1004, first_name="Verified")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=settings.ton_network_id,
            address=owner.upper(),
            public_key="3c" * 32,
        )
        db.add(wallet)
        await db.commit()

        tx = transaction(
            settings.bank_contract_address,
            owner,
            12,
            bank_create_body(103, 1_000_000_000, 12_500),
            1_080_000_000,
        )
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.APPLIED
        await db.commit()
        position = await db.scalar(select(BankPosition).where(BankPosition.position_id == 103))
        assert position is not None
        assert position.user_id == user.id
        assert position.wallet_id == wallet.id
        assert position.current_status == BankPositionStatus.PARTIALLY_FUNDED.value
        assert position.funded_amount_nano == 990_000_000


@pytest.mark.asyncio
async def test_empty_contract_topup_is_ignored_instead_of_blocking_projection(app) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        tx = transaction(
            settings.bank_contract_address,
            "0:" + "ee" * 32,
            12,
            "",
            1_000_000,
        )
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.IGNORED


@pytest.mark.asyncio
async def test_duel_projection_tracks_permissionless_offer(app) -> None:
    settings = get_settings()
    expires_at = 1_800_000_900
    body = body_b64(
        DUEL_OPEN_OFFER,
        [(64, 777), (256, 123), (16, 2500), (0, 4_000_000_000), (32, expires_at), (64, 0)],
    )
    async with app.state.session_factory() as db:
        tx = transaction(
            settings.effective_duel_contract_address,
            "0:" + "5a" * 32,
            13,
            body,
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, tx, "duel") == ProjectionResult.APPLIED
        await db.commit()
        offer = await db.scalar(select(DuelOffer).where(DuelOffer.onchain_offer_id == 777))
        assert offer is not None
        assert offer.user_id is None and offer.wallet_id is None
        assert offer.owner_wallet == "0:" + "5a" * 32
        assert offer.state == OfferState.OPEN.value


@pytest.mark.asyncio
async def test_duel_projection_validates_funding_and_terminal_payout(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        first_user = User(telegram_id=2001, first_name="First")
        second_user = User(telegram_id=2002, first_name="Second")
        db.add_all([first_user, second_user])
        await db.flush()
        first_wallet = Wallet(
            user_id=first_user.id,
            network=-3,
            address="0:" + "3a" * 32,
            public_key="4a" * 32,
        )
        second_wallet = Wallet(
            user_id=second_user.id,
            network=-3,
            address="0:" + "3b" * 32,
            public_key="4b" * 32,
        )
        db.add_all([first_wallet, second_wallet])
        await db.flush()
        counter = DuelOffer(
            onchain_offer_id=900,
            query_id=900,
            user_id=first_user.id,
            wallet_id=first_wallet.id,
            owner_wallet=first_wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=7500,
            total_pool_nano=4_000_000_000,
            stake_nano=3_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=250,
            payout_nano=3_900_000_000,
            commitment_hex="aa" * 32,
            state=OfferState.OPEN.value,
            expires_at=expires,
        )
        newcomer = DuelOffer(
            onchain_offer_id=100,
            query_id=1,
            user_id=second_user.id,
            wallet_id=second_wallet.id,
            owner_wallet=second_wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=2500,
            total_pool_nano=4_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=3_000_000_000,
            fee_bps=250,
            payout_nano=3_900_000_000,
            commitment_hex="bb" * 32,
            counter_offer_id=900,
            expires_at=expires,
        )
        db.add_all([counter, newcomer])
        await db.commit()

        opened = transaction(
            settings.effective_duel_contract_address,
            second_wallet.address,
            20,
            duel_open_body(newcomer),
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, opened, "duel") == ProjectionResult.APPLIED
        await db.commit()
        duel = await db.scalar(select(Duel))
        assert duel is not None and duel.onchain_duel_id == 900
        assert counter.state == OfferState.MATCHED.value
        assert newcomer.state == OfferState.MATCHED.value

        settled = transaction(
            settings.effective_duel_contract_address,
            second_wallet.address,
            21,
            duel_reveal_body(900, 100),
            30_000_000,
            outputs=[
                (
                    second_wallet.address,
                    duel_payout_body(900, 100),
                    3_900_000_000,
                )
            ],
        )
        assert await apply_transaction(db, settings, settled, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(duel)
        assert duel.state == DuelState.SETTLED.value
        assert duel.winner_wallet == second_wallet.address
        assert await db.scalar(select(func.count()).select_from(DuelChainEvent)) == 2
