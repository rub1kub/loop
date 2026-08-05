import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from tonsdk.boc import Cell

from app.chain_worker import (
    BANK_CREATE_POSITION,
    BANK_PAYOUT,
    DUEL_ACCEPT_DIRECT_OFFER,
    DUEL_BOOST,
    DUEL_EXPIRE_DUEL,
    DUEL_OPEN_DIRECT_OFFER,
    DUEL_OPEN_OFFER,
    DUEL_PAYOUT,
    DUEL_REFUND,
    DUEL_REVEAL,
    ProjectionResult,
    apply_transaction,
    contract_control,
    decode_body,
)
from app.config import get_settings
from app.models import (
    NotificationOutbox,
    ReferralAttribution,
    ReferralCode,
    ReferralReward,
    ResultCard,
    User,
    Wallet,
)
from app.modules.bank.models import BankChainEvent, BankPosition, BankPositionStatus
from app.modules.duel.models import (
    ChallengeState,
    Duel,
    DuelBoost,
    DuelChainEvent,
    DuelInvitation,
    DuelOffer,
    DuelSettlement,
    DuelState,
    OfferState,
)
from app.ton import sign_direct_accept_permit, sign_holder_fee_permit


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
    now: int = 1_800_000_000,
) -> dict[str, object]:
    return {
        "account": account,
        "lt": str(lt),
        "hash": f"tx-{lt}",
        "now": now,
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


def duel_direct_open_body(offer: DuelOffer) -> str:
    assert offer.invite_id_hex
    return body_b64(
        DUEL_OPEN_DIRECT_OFFER,
        [
            (64, offer.onchain_offer_id),
            (256, int(offer.commitment_hex, 16)),
            (16, offer.chance_bps),
            (0, offer.total_pool_nano),
            (32, int(offer.expires_at.timestamp())),
            (256, int(offer.invite_id_hex, 16)),
        ],
    )


def duel_direct_accept_body(offer: DuelOffer, signature_hex: str, valid_until: int) -> str:
    cell = Cell()
    cell.bits.write_uint(DUEL_ACCEPT_DIRECT_OFFER, 32)
    cell.bits.write_uint(offer.query_id, 64)
    cell.bits.write_uint(offer.onchain_offer_id, 64)
    cell.bits.write_uint(int(offer.commitment_hex, 16), 256)
    cell.bits.write_uint(offer.chance_bps, 16)
    cell.bits.write_coins(offer.total_pool_nano)
    cell.bits.write_uint(int(offer.expires_at.timestamp()), 32)
    acceptance = Cell()
    acceptance.bits.write_uint(offer.counter_offer_id, 64)
    acceptance.bits.write_uint(valid_until, 32)
    acceptance.bits.write_uint(int(signature_hex, 16), 512)
    cell.refs.append(acceptance)
    return base64.b64encode(cell.to_boc(has_idx=False)).decode()


def duel_reveal_body(duel_id: int, offer_id: int) -> str:
    return body_b64(DUEL_REVEAL, [(64, duel_id), (64, offer_id), (256, 777)])


def duel_boost_body(
    duel_id: int,
    offer_id: int,
    amount_nano: int,
    revision: int,
    min_chance_bps: int,
    valid_until: int,
) -> str:
    return body_b64(
        DUEL_BOOST,
        [
            (64, duel_id),
            (64, offer_id),
            (0, amount_nano),
            (16, revision),
            (16, min_chance_bps),
            (32, valid_until),
        ],
    )


def duel_payout_body(duel_id: int, offer_id: int) -> str:
    return body_b64(DUEL_PAYOUT, [(64, duel_id), (64, offer_id), (8, 1)])


def duel_expire_duel_body(duel_id: int) -> str:
    return body_b64(DUEL_EXPIRE_DUEL, [(64, duel_id)])


def duel_refund_body(offer_id: int, reason: int) -> str:
    return body_b64(DUEL_REFUND, [(64, offer_id), (8, reason)])


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
    settings = get_settings().model_copy(update={"public_feed_chat_id": -1003933253277})
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
        assert newer.funded_amount_nano == 800_000_000
        assert newer.remaining_amount_nano == 2_200_000_000
        assert await db.scalar(select(func.count()).select_from(BankChainEvent)) == 1
        card = await db.scalar(select(ResultCard).where(ResultCard.mode == "bank"))
        assert card is not None
        assert card.user_id == older_user.id
        assert card.result_nano == 250_000_000
        entry = await db.scalar(select(ResultCard).where(ResultCard.mode == "bank_entry"))
        assert entry is not None
        assert entry.payout_nano == 0
        assert entry.result_nano == 0
        assert entry.queue_position is not None
        assert await db.scalar(select(func.count()).select_from(NotificationOutbox)) == 3
        public_events = (
            await db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.kind == "public_feed")
            )
        ).all()
        assert len(public_events) == 2
        assert {item.dedupe_key.split(":")[1] for item in public_events} == {
            "bank_entry",
            "bank_payout",
        }
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.IGNORED
        assert await db.scalar(select(func.count()).select_from(ResultCard)) == 2
        assert await db.scalar(select(func.count()).select_from(NotificationOutbox)) == 3


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
        assert position.funded_amount_nano == 900_000_000
        assert position.remaining_amount_nano == 350_000_000


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
        assert position.funded_amount_nano == 900_000_000


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
    settings = get_settings().model_copy(update={"public_feed_chat_id": -1003933253277})
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
            fee_bps=1000,
            payout_nano=3_600_000_000,
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
            fee_bps=1000,
            payout_nano=3_600_000_000,
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
        assert duel.state == DuelState.BOOSTING.value

        boosted = transaction(
            settings.effective_duel_contract_address,
            second_wallet.address,
            21,
            duel_boost_body(900, 100, 1_000_000_000, 0, 4_000, 1_800_000_180),
            1_050_000_000,
            now=1_800_000_055,
        )
        assert await apply_transaction(db, settings, boosted, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(duel)
        await db.refresh(counter)
        await db.refresh(newcomer)
        assert duel.boost_revision == 1
        assert duel.boost_deadline is not None
        boost_deadline = (
            duel.boost_deadline
            if duel.boost_deadline.tzinfo
            else duel.boost_deadline.replace(tzinfo=UTC)
        )
        assert int(boost_deadline.timestamp()) == 1_800_000_075
        assert newcomer.stake_nano == 2_000_000_000
        assert newcomer.chance_bps == 4_000
        assert counter.chance_bps == 6_000
        assert newcomer.total_pool_nano == 5_000_000_000
        assert await db.scalar(select(func.count()).select_from(DuelBoost)) == 1

        settled = transaction(
            settings.effective_duel_contract_address,
            second_wallet.address,
            22,
            duel_reveal_body(900, 100),
            30_000_000,
            outputs=[
                (
                    second_wallet.address,
                    duel_payout_body(900, 100),
                    4_500_000_000,
                )
            ],
            now=1_800_000_076,
        )
        assert await apply_transaction(db, settings, settled, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(duel)
        assert duel.state == DuelState.SETTLED.value
        assert duel.winner_wallet == second_wallet.address
        card = await db.scalar(select(ResultCard))
        assert card is not None
        assert card.mode == "duel"
        assert card.user_id == second_user.id
        assert card.result_nano == 2_500_000_000
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.kind == "result")
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.kind == "duel_matched")
            )
            == 2
        )
        public_events = (
            await db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.kind == "public_feed")
            )
        ).all()
        assert len(public_events) == 2
        assert {item.dedupe_key.split(":")[1] for item in public_events} == {
            "duel_entry",
            "duel_payout",
        }


@pytest.mark.asyncio
async def test_duel_projection_requires_address_bound_direct_permit(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    valid_until = 1_800_000_300
    async with app.state.session_factory() as db:
        creator = User(telegram_id=2101, first_name="Creator")
        invited = User(telegram_id=2102, first_name="Invited")
        db.add_all([creator, invited])
        await db.flush()
        creator_wallet = Wallet(
            user_id=creator.id,
            network=-3,
            address="0:" + "5a" * 32,
            public_key="6a" * 32,
        )
        invited_wallet = Wallet(
            user_id=invited.id,
            network=-3,
            address="0:" + "5b" * 32,
            public_key="6b" * 32,
        )
        db.add_all([creator_wallet, invited_wallet])
        await db.flush()
        creator_offer = DuelOffer(
            onchain_offer_id=910,
            query_id=1,
            user_id=creator.id,
            wallet_id=creator_wallet.id,
            owner_wallet=creator_wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=7500,
            total_pool_nano=4_000_000_000,
            stake_nano=3_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=250,
            payout_nano=3_900_000_000,
            commitment_hex="ca" * 32,
            invite_id_hex="da" * 32,
            mode="direct",
            expires_at=expires,
        )
        invited_offer = DuelOffer(
            onchain_offer_id=911,
            query_id=911,
            user_id=invited.id,
            wallet_id=invited_wallet.id,
            owner_wallet=invited_wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=2500,
            total_pool_nano=4_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=3_000_000_000,
            fee_bps=250,
            payout_nano=3_900_000_000,
            commitment_hex="cb" * 32,
            counter_offer_id=creator_offer.onchain_offer_id,
            mode="direct",
            expires_at=expires,
        )
        db.add_all([creator_offer, invited_offer])
        await db.flush()
        db.add(
            DuelInvitation(
                code="direct-worker-proof",
                creator_user_id=creator.id,
                creator_offer_id=creator_offer.id,
                invite_id_hex=creator_offer.invite_id_hex,
                accepted_by_user_id=invited.id,
                accepted_wallet_address=invited_wallet.address,
                state=ChallengeState.FUNDING.value,
                expires_at=expires,
            )
        )
        await db.commit()

        opened = transaction(
            settings.effective_duel_contract_address,
            creator_wallet.address,
            30,
            duel_direct_open_body(creator_offer),
            3_050_000_000,
        )
        assert await apply_transaction(db, settings, opened, "duel") == ProjectionResult.APPLIED
        await db.commit()

        signature = sign_direct_accept_permit(
            settings.duel_invite_signing_key.get_secret_value(),
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            invite_id_hex=creator_offer.invite_id_hex,
            counter_offer_id=creator_offer.onchain_offer_id,
            invited_address=invited_wallet.address,
            valid_until=valid_until,
        )
        accepted = transaction(
            settings.effective_duel_contract_address,
            invited_wallet.address,
            31,
            duel_direct_accept_body(invited_offer, signature, valid_until),
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, accepted, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(creator_offer)
        await db.refresh(invited_offer)
        duel = await db.scalar(select(Duel).where(Duel.onchain_duel_id == 911))
        assert duel is not None
        assert creator_offer.direct_opponent_wallet == invited_wallet.address
        assert invited_offer.direct_opponent_wallet == creator_wallet.address
        assert creator_offer.state == invited_offer.state == OfferState.MATCHED.value
        assert await db.scalar(select(func.count()).select_from(DuelChainEvent)) == 2


@pytest.mark.asyncio
async def test_no_reveal_expire_duel_is_terminal_and_not_a_settlement(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        first_user = User(telegram_id=2101, first_name="Silent")
        second_user = User(telegram_id=2102, first_name="Quiet")
        db.add_all([first_user, second_user])
        await db.flush()
        first_wallet = Wallet(
            user_id=first_user.id,
            network=-3,
            address="0:" + "5a" * 32,
            public_key="6a" * 32,
        )
        second_wallet = Wallet(
            user_id=second_user.id,
            network=-3,
            address="0:" + "5b" * 32,
            public_key="6b" * 32,
        )
        db.add_all([first_wallet, second_wallet])
        await db.flush()
        offers = [
            DuelOffer(
                onchain_offer_id=offer_id,
                query_id=offer_id,
                user_id=user.id,
                wallet_id=wallet.id,
                owner_wallet=wallet.address,
                network=-3,
                contract_address=settings.effective_duel_contract_address,
                chance_bps=5000,
                total_pool_nano=2_000_000_000,
                stake_nano=1_000_000_000,
                opponent_stake_nano=1_000_000_000,
                fee_bps=250,
                payout_nano=1_950_000_000,
                commitment_hex=commitment * 32,
                state=OfferState.MATCHED.value,
                expires_at=expires,
            )
            for offer_id, user, wallet, commitment in (
                (920, first_user, first_wallet, "c1"),
                (921, second_user, second_wallet, "c2"),
            )
        ]
        db.add_all(offers)
        await db.flush()
        duel = Duel(
            onchain_duel_id=921,
            network=-3,
            offer_a_id=offers[0].id,
            offer_b_id=offers[1].id,
            state=DuelState.REVEALING.value,
            boost_deadline=datetime.fromtimestamp(1_800_000_060, UTC),
            hard_deadline=datetime.fromtimestamp(1_800_000_180, UTC),
            reveal_deadline=datetime.fromtimestamp(1_800_000_360, UTC),
        )
        db.add(duel)
        await db.commit()

        expired = transaction(
            settings.effective_duel_contract_address,
            first_wallet.address,
            40,
            duel_expire_duel_body(921),
            30_000_000,
            outputs=[
                (first_wallet.address, duel_refund_body(920, 5), 1_000_000_000),
                (second_wallet.address, duel_refund_body(921, 5), 1_000_000_000),
            ],
            now=1_800_000_400,
        )
        assert await apply_transaction(db, settings, expired, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(duel)
        for offer in offers:
            await db.refresh(offer)
            assert offer.state == OfferState.REFUNDED.value
        assert duel.state == DuelState.REFUNDED.value
        assert duel.settled_tx_hash == "tx-40"
        assert duel.settled_at is not None
        # A refund is not a completed duel: no settlement row, no rating points,
        # no shareable result card.
        assert await db.scalar(select(func.count()).select_from(DuelSettlement)) == 0
        assert await db.scalar(select(func.count()).select_from(ResultCard)) == 0


@pytest.mark.asyncio
async def test_confirmed_bank_payout_qualifies_the_referred_friend(app) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        inviter = User(telegram_id=3001, first_name="Inviter")
        invitee = User(telegram_id=3002, first_name="Invitee")
        funder = User(telegram_id=3003, first_name="Funder")
        db.add_all([inviter, invitee, funder])
        await db.flush()
        inviter_wallet = Wallet(
            user_id=inviter.id,
            network=-3,
            address="0:" + "7a" * 32,
            public_key="8a" * 32,
            active=True,
        )
        invitee_wallet = Wallet(
            user_id=invitee.id,
            network=-3,
            address="0:" + "7b" * 32,
            public_key="8b" * 32,
            active=True,
        )
        funder_wallet = Wallet(
            user_id=funder.id,
            network=-3,
            address="0:" + "7c" * 32,
            public_key="8c" * 32,
            active=True,
        )
        db.add_all([inviter_wallet, invitee_wallet, funder_wallet])
        db.add(ReferralCode(code="bankrefcode", owner_user_id=inviter.id))
        await db.flush()
        db.add(
            ReferralAttribution(
                inviter_user_id=inviter.id,
                invitee_user_id=invitee.id,
                code="bankrefcode",
            )
        )
        older = BankPosition(
            position_id=300,
            query_id=300,
            user_id=invitee.id,
            wallet_id=invitee_wallet.id,
            owner_wallet=invitee_wallet.address,
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
            position_id=301,
            query_id=301,
            user_id=funder.id,
            wallet_id=funder_wallet.id,
            owner_wallet=funder_wallet.address,
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
            funder_wallet.address,
            50,
            bank_create_body(301, 2_000_000_000, 15_000),
            2_080_000_000,
            outputs=[
                (
                    invitee_wallet.address,
                    bank_payout_body(300, 1_000_000_000, 1_250_000_000),
                    1_250_000_000,
                )
            ],
        )
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.APPLIED
        await db.commit()
        attribution = await db.scalar(select(ReferralAttribution))
        assert attribution is not None
        assert attribution.status == "qualified"
        assert attribution.qualified_tx_hash == "tx-50"
        reward = await db.scalar(select(ReferralReward))
        assert reward is not None
        assert reward.cause == "bank:300"


def duel_open_body_with_holder(offer: DuelOffer, valid_until: int, signature_hex: str) -> str:
    cell = Cell()
    cell.bits.write_uint(DUEL_OPEN_OFFER, 32)
    cell.bits.write_uint(offer.query_id, 64)
    cell.bits.write_uint(offer.onchain_offer_id, 64)
    cell.bits.write_uint(int(offer.commitment_hex, 16), 256)
    cell.bits.write_uint(offer.chance_bps, 16)
    cell.bits.write_coins(offer.total_pool_nano)
    cell.bits.write_uint(int(offer.expires_at.timestamp()), 32)
    cell.bits.write_uint(offer.counter_offer_id, 64)
    cell.bits.write_bit(1)
    permit = Cell()
    permit.bits.write_uint(valid_until, 32)
    permit.bits.write_uint(int(signature_hex, 16), 512)
    cell.refs.append(permit)
    return base64.b64encode(cell.to_boc(has_idx=False)).decode()


@pytest.mark.asyncio
async def test_verified_holder_permit_marks_the_offer_fee_exempt(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        user = User(telegram_id=2201, first_name="Holder")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "9a" * 32,
            public_key="9b" * 32,
        )
        db.add(wallet)
        await db.flush()
        offer = DuelOffer(
            onchain_offer_id=930,
            query_id=930,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=250,
            fee_exempt=True,
            payout_nano=2_000_000_000,
            commitment_hex="d1" * 32,
            expires_at=expires,
        )
        db.add(offer)
        await db.commit()

        valid_until = 1_800_000_290
        signature = sign_holder_fee_permit(
            settings.duel_invite_signing_key.get_secret_value(),
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            offer_id=930,
            owner_address=wallet.address,
            valid_until=valid_until,
        )
        tx = transaction(
            settings.effective_duel_contract_address,
            wallet.address,
            60,
            duel_open_body_with_holder(offer, valid_until, signature),
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, tx, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(offer)
        assert offer.state == OfferState.OPEN.value
        assert offer.fee_exempt is True
        assert offer.payout_nano == 2_000_000_000


@pytest.mark.asyncio
async def test_forged_holder_permit_blocks_the_projection(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        user = User(telegram_id=2202, first_name="Forger")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "9c" * 32,
            public_key="9d" * 32,
        )
        db.add(wallet)
        await db.flush()
        offer = DuelOffer(
            onchain_offer_id=931,
            query_id=931,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=250,
            payout_nano=1_950_000_000,
            commitment_hex="d2" * 32,
            expires_at=expires,
        )
        db.add(offer)
        await db.commit()

        # Signed for a different offer id: the worker must refuse to project a
        # fee exemption it cannot verify, even though the shape is valid.
        signature = sign_holder_fee_permit(
            settings.duel_invite_signing_key.get_secret_value(),
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            offer_id=999,
            owner_address=wallet.address,
            valid_until=1_800_000_290,
        )
        tx = transaction(
            settings.effective_duel_contract_address,
            wallet.address,
            61,
            duel_open_body_with_holder(offer, 1_800_000_290, signature),
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, tx, "duel") == ProjectionResult.RETRY


@pytest.mark.asyncio
async def test_funding_without_permit_clears_a_stale_local_exemption(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        user = User(telegram_id=2203, first_name="Stale")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "9e" * 32,
            public_key="9f" * 32,
        )
        db.add(wallet)
        await db.flush()
        offer = DuelOffer(
            onchain_offer_id=932,
            query_id=932,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=250,
            fee_exempt=True,
            payout_nano=2_000_000_000,
            commitment_hex="d3" * 32,
            expires_at=expires,
        )
        db.add(offer)
        await db.commit()

        tx = transaction(
            settings.effective_duel_contract_address,
            wallet.address,
            62,
            duel_open_body(offer),
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, tx, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(offer)
        assert offer.fee_exempt is False
        assert offer.payout_nano == 1_800_000_000


@pytest.mark.asyncio
async def test_worker_refuses_a_permit_outside_the_contract_expiry_window(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        user = User(telegram_id=2204, first_name="Expired")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "a1" * 32,
            public_key="a2" * 32,
        )
        db.add(wallet)
        await db.flush()
        offer = DuelOffer(
            onchain_offer_id=940,
            query_id=940,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=250,
            payout_nano=1_950_000_000,
            commitment_hex="e1" * 32,
            expires_at=expires,
        )
        db.add(offer)
        await db.commit()

        # Correctly signed, but long expired at the transaction's chain time.
        # The contract would never accept it, so a projection that did would be
        # trusting the transaction verdict instead of proving the exemption.
        for valid_until in (1_700_000_000, 1_800_000_000 + 7_200):
            signature = sign_holder_fee_permit(
                settings.duel_invite_signing_key.get_secret_value(),
                network=-3,
                contract_address=settings.effective_duel_contract_address,
                offer_id=940,
                owner_address=wallet.address,
                valid_until=valid_until,
            )
            tx = transaction(
                settings.effective_duel_contract_address,
                wallet.address,
                70 + (valid_until % 7),
                duel_open_body_with_holder(offer, valid_until, signature),
                1_050_000_000,
            )
            assert await apply_transaction(db, settings, tx, "duel") == ProjectionResult.RETRY


@pytest.mark.asyncio
async def test_funding_projects_the_observed_contract_fee_not_the_quote(app) -> None:
    settings = get_settings()
    expires = datetime.fromtimestamp(1_800_000_900, UTC)
    async with app.state.session_factory() as db:
        control = await contract_control(db, settings, "duel")
        control.fee_bps = 500
        user = User(telegram_id=2205, first_name="Stale")
        db.add(user)
        await db.flush()
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "a3" * 32,
            public_key="a4" * 32,
        )
        db.add(wallet)
        await db.flush()
        offer = DuelOffer(
            onchain_offer_id=941,
            query_id=941,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=-3,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            # The quote was priced before the owner raised the fee on chain.
            fee_bps=250,
            payout_nano=1_950_000_000,
            commitment_hex="e2" * 32,
            expires_at=expires,
        )
        db.add(offer)
        await db.commit()

        tx = transaction(
            settings.effective_duel_contract_address,
            wallet.address,
            80,
            duel_open_body(offer),
            1_050_000_000,
        )
        assert await apply_transaction(db, settings, tx, "duel") == ProjectionResult.APPLIED
        await db.commit()
        await db.refresh(offer)
        # Projecting the stale 250 bps would promise 1.95 and then retry the
        # settlement forever, because the contract pays 1.90.
        assert offer.fee_bps == 500
        assert offer.payout_nano == 1_900_000_000


@pytest.mark.asyncio
async def test_confirmed_referred_deposit_accrues_the_inviter_fee_share(app) -> None:
    """2% of every confirmed deposit by an invited person, funded by the fee.

    Accrued at confirmation rather than promised at sign-up: a fake account
    has to move real money and pay a real fee before a single nanoGRAM lands.
    Replays of the same deposit must not double the accrual.
    """
    settings = get_settings()
    async with app.state.session_factory() as db:
        inviter = User(telegram_id=3101, first_name="Inviter")
        invitee = User(telegram_id=3102, first_name="Invitee")
        db.add_all([inviter, invitee])
        await db.flush()
        invitee_wallet = Wallet(
            user_id=invitee.id,
            network=-3,
            address="0:" + "7d" * 32,
            public_key="8d" * 32,
            active=True,
        )
        db.add(invitee_wallet)
        db.add(ReferralCode(code="feeshare", owner_user_id=inviter.id))
        await db.flush()
        db.add(
            ReferralAttribution(
                inviter_user_id=inviter.id,
                invitee_user_id=invitee.id,
                code="feeshare",
            )
        )
        position = BankPosition(
            position_id=310,
            query_id=310,
            user_id=invitee.id,
            wallet_id=invitee_wallet.id,
            owner_wallet=invitee_wallet.address,
            network=-3,
            contract_address=settings.bank_contract_address,
            principal_nano=2_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=2_500_000_000,
            remaining_amount_nano=2_500_000_000,
        )
        db.add(position)
        await db.commit()

        tx = transaction(
            settings.bank_contract_address,
            invitee_wallet.address,
            60,
            bank_create_body(310, 2_000_000_000, 12_500),
            2_080_000_000,
        )
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.APPLIED
        await db.commit()

        reward = await db.scalar(
            select(ReferralReward).where(ReferralReward.cause == f"fee_share:{position.id}")
        )
        assert reward is not None
        assert reward.reward_nano == 40_000_000  # 2% of 2 GRAM
        assert reward.reward_points == 0

        # The same transaction seen again accrues nothing new.
        assert await apply_transaction(db, settings, tx, "bank") == ProjectionResult.IGNORED
        await db.commit()
        total = await db.scalar(
            select(func.count())
            .select_from(ReferralReward)
            .where(ReferralReward.cause == f"fee_share:{position.id}")
        )
        assert total == 1


class _Response:
    def __init__(self, transactions: list[dict[str, object]]) -> None:
        self._transactions = transactions

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"transactions": self._transactions}


class _Http:
    def __init__(self, transactions: list[dict[str, object]]) -> None:
        self._transactions = transactions

    async def get(self, _url: str, **_kwargs: object) -> _Response:
        return _Response(self._transactions)


async def test_a_failing_transaction_keeps_the_work_already_done(app, monkeypatch) -> None:
    # On launch night one deposit could not be written down, and the exception
    # discarded the whole batch with it: the checkpoint never moved, so every
    # following cycle replayed the same transactions and died in the same place.
    # Confirmations stopped for everyone for an hour. What applied must survive,
    # and the checkpoint must come to rest exactly at the transaction that hurt.
    from app import chain_worker

    settings = get_settings()
    address = settings.bank_contract_address or "0:" + "ab" * 32
    transactions = [
        transaction(address, "0:" + "cd" * 32, lt, "", 1_000_000_000) for lt in (10, 20, 30, 40)
    ]

    seen: list[int] = []

    async def flaky(_db, _settings, tx, _mode):
        lt = int(tx["lt"])
        seen.append(lt)
        if lt == 30:
            raise RuntimeError("this row cannot be written")
        return ProjectionResult.APPLIED

    monkeypatch.setattr(chain_worker, "apply_transaction", flaky)

    with pytest.raises(chain_worker.ProjectionFailure) as raised:
        await chain_worker.run_contract_once(
            _Http(transactions),
            app.state.session_factory,
            settings,
            mode="bank",
            address=address,
        )

    # It stopped at the offending transaction rather than stepping over it: a
    # later transaction may depend on an earlier one, so skipping would corrupt
    # the projection more quietly than standing still.
    assert seen == [10, 20, 30]
    assert raised.value.tx_hash == "tx-30"
    assert "tx-30" in str(raised.value)

    key = f"bank:{settings.ton_network_id}:{address}"
    async with app.state.session_factory() as db:
        checkpoint = await db.get(chain_worker.ChainCheckpoint, key)
        assert checkpoint is not None
        # Past the two that applied, and no further.
        assert checkpoint.last_lt == 21


async def test_a_broken_bank_transaction_still_lets_duels_settle(app, monkeypatch) -> None:
    # The two contracts share only this loop. BANK raised first and duels went
    # unsettled for an hour for a reason that had nothing to do with duels.
    from app import chain_worker

    settings = get_settings()
    attempted: list[str] = []

    async def one_sided(_http, _factory, _settings, *, mode: str, address: str):
        attempted.append(mode)
        if mode == "bank":
            raise chain_worker.ProjectionFailure("bank", "tx-7", RuntimeError("duplicate key"))
        return 3, False

    monkeypatch.setattr(chain_worker, "run_contract_once", one_sided)

    with pytest.raises(chain_worker.ProjectionFailure):
        await chain_worker.run_once(_Http([]), app.state.session_factory, settings)

    assert attempted == ["bank", "duel"]
