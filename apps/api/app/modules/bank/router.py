from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, update

from ...dependencies import Config, CurrentUser, Db
from ...models import Wallet
from ...schemas import (
    BankContractCall,
    BankPositionPreviewRequest,
    BankPositionPreviewResponse,
    BankPositionQuoteRequest,
    BankPositionQuoteResponse,
    BankPositionView,
)
from ...ton import explorer_transaction_url
from .models import BankPosition, BankPositionStatus

router = APIRouter(prefix="/bank", tags=["BANK"])


ACTIVE_POSITION_STATES = [
    BankPositionStatus.PENDING_CONFIRMATION.value,
    BankPositionStatus.QUEUED.value,
    BankPositionStatus.PARTIALLY_FUNDED.value,
    BankPositionStatus.COMPLETED.value,
]


async def position_view(db: Db, position: BankPosition) -> BankPositionView:
    progress = min(
        position.funded_amount_nano * 10_000 // max(position.target_payout_nano, 1),
        10_000,
    )
    proof_hash = position.payout_transaction or position.funding_transaction
    queue_position: int | None = None
    if position.queue_index is not None and position.current_status in ACTIVE_POSITION_STATES:
        ahead = await db.scalar(
            select(func.count())
            .select_from(BankPosition)
            .where(
                BankPosition.network == position.network,
                BankPosition.contract_address == position.contract_address,
                BankPosition.current_status.in_(ACTIVE_POSITION_STATES),
                BankPosition.queue_index.is_not(None),
                BankPosition.queue_index < position.queue_index,
            )
        )
        queue_position = int(ahead or 0) + 1
    return BankPositionView(
        id=position.id,
        position_id=position.position_id,
        owner_wallet=position.owner_wallet,
        principal_nano=position.principal_nano,
        multiplier_bps=position.multiplier_bps,
        target_payout_nano=position.target_payout_nano,
        funded_amount_nano=position.funded_amount_nano,
        remaining_amount_nano=position.remaining_amount_nano,
        progress_bps=progress,
        queue_index=position.queue_index,
        queue_position=queue_position,
        current_status=position.current_status,
        funding_transaction=position.funding_transaction,
        payout_transaction=position.payout_transaction,
        proof_url=(explorer_transaction_url(position.network, proof_hash) if proof_hash else None),
        created_at=position.created_at,
        completed_at=position.completed_at,
    )


async def active_wallet(db: Db, user_id: str, network: int) -> Wallet:
    wallet = await db.scalar(
        select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.network == network,
            Wallet.active.is_(True),
        )
    )
    if wallet is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "verified testnet wallet required")
    return wallet


@router.post("/positions/preview", response_model=BankPositionPreviewResponse)
async def preview_position(
    body: BankPositionPreviewRequest,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> BankPositionPreviewResponse:
    if settings.ton_network_id != -3:
        raise HTTPException(status.HTTP_409_CONFLICT, "LOOP BANK works only in TON testnet")
    if not settings.bank_contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "BANK contract is not configured")
    if (
        not settings.bank_min_principal_nano
        <= body.principal_nano
        <= settings.bank_max_principal_nano
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "principal is outside limits")
    await active_wallet(db, user.id, settings.ton_network_id)
    fee = body.principal_nano * settings.bank_fee_bps // 10_000
    return BankPositionPreviewResponse(
        principal_nano=body.principal_nano,
        multiplier_bps=body.multiplier_bps,
        target_payout_nano=body.principal_nano * body.multiplier_bps // 10_000,
        fee_nano=fee,
        gas_nano=settings.bank_position_gas_nano,
        transaction_amount_nano=body.principal_nano + settings.bank_position_gas_nano,
        contract_address=settings.bank_contract_address,
        network=settings.ton_network_id,
    )


@router.post(
    "/positions/quote",
    response_model=BankPositionQuoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def quote_position(
    body: BankPositionQuoteRequest,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> BankPositionQuoteResponse:
    if settings.ton_network_id != -3:
        raise HTTPException(status.HTTP_409_CONFLICT, "LOOP BANK works only in TON testnet")
    if not settings.bank_contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "BANK contract is not configured")
    if (
        not settings.bank_min_principal_nano
        <= body.principal_nano
        <= settings.bank_max_principal_nano
    ):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "principal is outside limits")
    wallet = await active_wallet(db, user.id, settings.ton_network_id)
    await db.execute(
        update(BankPosition)
        .where(
            BankPosition.wallet_id == wallet.id,
            BankPosition.current_status == BankPositionStatus.PENDING_CONFIRMATION.value,
            BankPosition.created_at < datetime.now(UTC) - timedelta(minutes=15),
        )
        .values(
            current_status=BankPositionStatus.FAILED.value,
            failure_reason="funding intent expired before on-chain confirmation",
        )
    )
    active = await db.scalar(
        select(BankPosition.id).where(
            BankPosition.wallet_id == wallet.id,
            BankPosition.current_status.in_(
                [
                    BankPositionStatus.PENDING_CONFIRMATION.value,
                    BankPositionStatus.QUEUED.value,
                    BankPositionStatus.PARTIALLY_FUNDED.value,
                    BankPositionStatus.COMPLETED.value,
                ]
            ),
        )
    )
    if active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "wallet already has an active BANK position")
    duplicate = await db.scalar(
        select(BankPosition.id).where(
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
            BankPosition.position_id == body.position_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "position id already exists")

    target = body.principal_nano * body.multiplier_bps // 10_000
    fee = body.principal_nano * settings.bank_fee_bps // 10_000
    position = BankPosition(
        position_id=body.position_id,
        query_id=body.position_id,
        user_id=user.id,
        wallet_id=wallet.id,
        owner_wallet=wallet.address,
        network=settings.ton_network_id,
        contract_address=settings.bank_contract_address,
        principal_nano=body.principal_nano,
        multiplier_bps=body.multiplier_bps,
        target_payout_nano=target,
        remaining_amount_nano=target,
    )
    db.add(position)
    await db.commit()
    await db.refresh(position)
    return BankPositionQuoteResponse(
        position=await position_view(db, position),
        transaction=BankContractCall(
            operation="create_bank_position",
            query_id=position.query_id,
            position_id=position.position_id,
            contract_address=position.contract_address,
            amount_nano=str(body.principal_nano + settings.bank_position_gas_nano),
            principal_nano=str(body.principal_nano),
            multiplier_bps=body.multiplier_bps,
            valid_until=int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            network=settings.ton_network_id,
            fee_nano=str(fee),
        ),
    )


@router.get("/positions/current", response_model=BankPositionView | None)
async def current_position(
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> BankPositionView | None:
    position = await db.scalar(
        select(BankPosition)
        .where(
            BankPosition.user_id == user.id,
            BankPosition.network == settings.ton_network_id,
            BankPosition.current_status.in_(
                [
                    BankPositionStatus.PENDING_CONFIRMATION.value,
                    BankPositionStatus.QUEUED.value,
                    BankPositionStatus.PARTIALLY_FUNDED.value,
                    BankPositionStatus.COMPLETED.value,
                ]
            ),
        )
        .order_by(BankPosition.created_at.desc())
    )
    return await position_view(db, position) if position else None


@router.get("/positions", response_model=list[BankPositionView])
async def list_positions(
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> list[BankPositionView]:
    positions = (
        await db.scalars(
            select(BankPosition)
            .where(
                BankPosition.user_id == user.id,
                BankPosition.network == settings.ton_network_id,
            )
            .order_by(BankPosition.created_at.desc())
            .limit(50)
        )
    ).all()
    return [await position_view(db, position) for position in positions]
