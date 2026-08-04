from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update

from ...control_state import effective_contract_fee, ensure_mode_enabled
from ...dependencies import Config, CurrentUser, Db, require_full_access
from ...models import Wallet
from ...schemas import (
    BankContractCall,
    BankLimitView,
    BankPositionPreviewRequest,
    BankPositionPreviewResponse,
    BankPositionQuoteRequest,
    BankPositionQuoteResponse,
    BankPositionView,
)
from ...ton import TonProviderError, explorer_transaction_url
from .models import BankPayout, BankPosition, BankPositionStatus

router = APIRouter(
    prefix="/bank",
    tags=["BANK"],
    # Signing in is open to everyone before launch; the product is not.
    dependencies=[Depends(require_full_access)],
)


ACTIVE_POSITION_STATES = [
    BankPositionStatus.PENDING_CONFIRMATION.value,
    BankPositionStatus.QUEUED.value,
    BankPositionStatus.PARTIALLY_FUNDED.value,
    BankPositionStatus.COMPLETED.value,
]

GRAM = 1_000_000_000


# Mirrors BankQueue.tolk exactly: a cap of N GRAM unlocks after 5N payouts.
# The contract is the authority; this exists so the app can show the number
# and refuse an over-limit deposit before the user pays gas to be rejected.
LADDER_GRAM = (1, 2, 3, 5, 7, 10, 15, 20, 30, 50, 75, 100)
COMPLETIONS_PER_GRAM = 5


def maturity_limit(completed_positions: int) -> tuple[int, int | None, int | None]:
    current = LADDER_GRAM[0]
    next_rung: int | None = None
    for rung in LADDER_GRAM[1:]:
        if completed_positions >= rung * COMPLETIONS_PER_GRAM:
            current = rung
        elif next_rung is None:
            next_rung = rung
    if next_rung is None:
        return current * GRAM, None, None
    needed = next_rung * COMPLETIONS_PER_GRAM - completed_positions
    return current * GRAM, next_rung * GRAM, needed


async def bank_limit(db: Db, settings: Config) -> BankLimitView:
    completed = int(
        await db.scalar(
            select(func.count(BankPayout.id))
            .join(BankPosition, BankPayout.position_id == BankPosition.id)
            .where(
                BankPosition.network == settings.ton_network_id,
                BankPosition.contract_address == settings.bank_contract_address,
            )
        )
        or 0
    )
    current, next_limit, remaining = maturity_limit(completed)
    # What the screen shows must be what validation enforces: the smaller of
    # the contract's maturity limit and the application's launch cap. While the
    # cap is the binding one, growth is not reachable, so it is not promised.
    cap = settings.bank_max_principal_nano
    if cap:
        current = min(current, cap)
        if next_limit is not None:
            next_limit = min(next_limit, cap)
            if next_limit <= current:
                next_limit, remaining = None, None
    return BankLimitView(
        completed_positions=completed,
        principal_limit_nano=current,
        next_limit_nano=next_limit,
        completions_until_next=remaining,
    )


async def validate_principal(db: Db, settings: Config, principal_nano: int) -> BankLimitView:
    limit = await bank_limit(db, settings)
    maximum = min(settings.bank_max_principal_nano, limit.principal_limit_nano)
    if not settings.bank_min_principal_nano <= principal_nano <= maximum:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Сейчас можно внести от 1 до {maximum // GRAM} GRAM",
        )
    return limit


async def position_view(
    db: Db,
    position: BankPosition,
    *,
    debug_progress_bps: int | None = None,
) -> BankPositionView:
    progress = min(
        position.funded_amount_nano * 10_000 // max(position.target_payout_nano, 1),
        10_000,
    )
    funded_amount = position.funded_amount_nano
    remaining_amount = position.remaining_amount_nano
    if debug_progress_bps is not None and position.current_status in ACTIVE_POSITION_STATES:
        # Debug progress is a response projection only. Never hide real chain
        # progress if it has already moved beyond the configured preview.
        progress = max(progress, debug_progress_bps)
        funded_amount = max(
            funded_amount,
            position.target_payout_nano * progress // 10_000,
        )
        remaining_amount = max(position.target_payout_nano - funded_amount, 0)
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
        funded_amount_nano=funded_amount,
        remaining_amount_nano=remaining_amount,
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
        raise HTTPException(status.HTTP_409_CONFLICT, "Подтверди поддерживаемый кошелёк TON")
    return wallet


@router.post("/positions/preview", response_model=BankPositionPreviewResponse)
async def preview_position(
    body: BankPositionPreviewRequest,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> BankPositionPreviewResponse:
    await ensure_mode_enabled(db, "bank")
    if not settings.ton_transactions_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Выбранная сеть кошелька пока не поддерживается"
        )
    if not settings.bank_contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "BANK contract is not configured")
    await validate_principal(db, settings, body.principal_nano)
    await active_wallet(db, user.id, settings.ton_network_id)
    fee_bps = await effective_contract_fee(
        db,
        mode="bank",
        network=settings.ton_network_id,
        address=settings.bank_contract_address,
        fallback=settings.bank_fee_bps,
    )
    fee = body.principal_nano * fee_bps // 10_000
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
    request: Request,
    settings: Config,
) -> BankPositionQuoteResponse:
    await ensure_mode_enabled(db, "bank")
    if not settings.ton_transactions_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Выбранная сеть кошелька пока не поддерживается"
        )
    if not settings.bank_contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "BANK contract is not configured")
    # A paused contract rejects every deposit and bounces it back minus gas.
    # Pausing is a routine owner action — the panel requires it to change the
    # fee, the treasury or to withdraw — so this must refuse before a wallet is
    # ever opened. Fail closed: a contract we could not ask counts as closed.
    try:
        admin = await request.app.state.ton_client.get_contract_admin_state(
            "bank", settings.bank_contract_address
        )
    except TonProviderError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "BANK временно недоступен"
        ) from exc
    if admin.paused:
        raise HTTPException(status.HTTP_409_CONFLICT, "BANK сейчас закрыт")
    await validate_principal(db, settings, body.principal_nano)
    wallet = await active_wallet(db, user.id, settings.ton_network_id)
    await db.execute(
        update(BankPosition)
        .where(
            BankPosition.wallet_id == wallet.id,
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
            BankPosition.current_status == BankPositionStatus.PENDING_CONFIRMATION.value,
            # The quote's valid_until is five minutes; past six the intent is
            # unsignable and only blocks the wallet's single position slot.
            BankPosition.created_at < datetime.now(UTC) - timedelta(minutes=6),
        )
        .values(
            current_status=BankPositionStatus.FAILED.value,
            failure_reason="funding intent expired before on-chain confirmation",
        )
    )
    active = await db.scalar(
        select(BankPosition.id).where(
            BankPosition.wallet_id == wallet.id,
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
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
    fee_bps = await effective_contract_fee(
        db,
        mode="bank",
        network=settings.ton_network_id,
        address=settings.bank_contract_address,
        fallback=settings.bank_fee_bps,
    )
    fee = body.principal_nano * fee_bps // 10_000
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


@router.post("/positions/{position_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
async def discard_unfunded_position(
    position_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> Response:
    """Drop a quote the player never signed.

    A quote takes the wallet's only position slot before the wallet is even
    opened. Refusing in the wallet has to cost nothing, and it costs nothing to
    undo: without a funding transaction this row has no counterpart on chain.
    """
    position = await db.scalar(
        select(BankPosition).where(
            BankPosition.position_id == position_id,
            BankPosition.user_id == user.id,
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
        )
    )
    if position is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "position not found")
    # Anything the chain has already seen belongs to the chain, not to a button.
    if (
        position.current_status != BankPositionStatus.PENDING_CONFIRMATION.value
        or position.funding_transaction
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "position is already funded")
    position.current_status = BankPositionStatus.FAILED.value
    position.failure_reason = "wallet signature declined"
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/limits", response_model=BankLimitView)
async def limits(db: Db, settings: Config) -> BankLimitView:
    return await bank_limit(db, settings)


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
            BankPosition.contract_address == settings.bank_contract_address,
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
    return (
        await position_view(
            db,
            position,
            debug_progress_bps=settings.bank_debug_progress_for(user.telegram_id),
        )
        if position
        else None
    )


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
                BankPosition.contract_address == settings.bank_contract_address,
            )
            .order_by(BankPosition.created_at.desc())
            .limit(50)
        )
    ).all()
    debug_progress = settings.bank_debug_progress_for(user.telegram_id)
    return [
        await position_view(db, position, debug_progress_bps=debug_progress)
        for position in positions
    ]
