import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.orm import aliased

from ...dependencies import Config, CurrentUser, Db
from ...models import Wallet
from ...schemas import (
    ActionIntent,
    ContractCall,
    DuelView,
    OfferQuoteRequest,
    OfferQuoteResponse,
    OfferView,
)
from ...ton import explorer_transaction_url, sign_direct_accept_permit
from .math import canonical_duel_terms, payout_after_fee
from .models import ChallengeState, Duel, DuelInvitation, DuelOffer, DuelState, OfferState

router = APIRouter(prefix="/duels", tags=["DUEL"])
ACTION_GAS_NANO = 30_000_000


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def offer_view(offer: DuelOffer) -> OfferView:
    return OfferView(
        id=offer.id,
        onchain_offer_id=offer.onchain_offer_id,
        chance_bps=offer.chance_bps,
        total_pool_nano=offer.total_pool_nano,
        stake_nano=offer.stake_nano,
        opponent_stake_nano=offer.opponent_stake_nano,
        fee_bps=offer.fee_bps,
        payout_nano=offer.payout_nano,
        net_profit_nano=offer.payout_nano - offer.stake_nano,
        mode=offer.mode,
        direct_opponent_wallet=offer.direct_opponent_wallet,
        state=offer.state,
        expires_at=offer.expires_at,
        funding_tx_hash=offer.funding_tx_hash,
        funding_proof_url=(
            explorer_transaction_url(offer.network, offer.funding_tx_hash)
            if offer.funding_tx_hash
            else None
        ),
    )


def action_intent(
    operation: str,
    contract_address: str,
    network: int,
    *,
    offer_id: int = 0,
    duel_id: int = 0,
) -> ActionIntent:
    return ActionIntent(
        operation=operation,
        query_id=secrets.randbelow(9_007_199_254_740_990) + 1,
        offer_id=offer_id,
        duel_id=duel_id,
        contract_address=contract_address,
        amount_nano=str(ACTION_GAS_NANO),
        valid_until=int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        network=network,
    )


@router.post(
    "/offers/quote",
    response_model=OfferQuoteResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post("/quote", response_model=OfferQuoteResponse, include_in_schema=False)
async def create_offer_quote(
    body: OfferQuoteRequest,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> OfferQuoteResponse:
    if settings.ton_network_id != -3:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Выбранная сеть кошелька пока не поддерживается"
        )
    contract_address = settings.effective_duel_contract_address
    if not contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DUEL contract is not configured")
    if body.chance_bps != 5_000 and not body.challenge_code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "new DUEL offers must use equal 50/50 terms",
        )
    stake, opponent_stake, total_pool = canonical_duel_terms(body.stake_nano, body.chance_bps)
    if not settings.min_pool_nano <= total_pool <= settings.max_pool_nano:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "pool is outside limits")
    wallet = await db.scalar(
        select(Wallet).where(
            Wallet.user_id == user.id,
            Wallet.network == settings.ton_network_id,
            Wallet.active.is_(True),
        )
    )
    if wallet is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Подтверди поддерживаемый кошелёк TON")
    now = datetime.now(UTC)
    await db.execute(
        update(DuelOffer)
        .where(
            DuelOffer.wallet_id == wallet.id,
            DuelOffer.state == OfferState.PENDING_FUNDING.value,
            DuelOffer.expires_at < now,
        )
        .values(state=OfferState.EXPIRED.value)
    )
    active = await db.scalar(
        select(DuelOffer.id).where(
            DuelOffer.wallet_id == wallet.id,
            DuelOffer.state.in_(
                [
                    OfferState.PENDING_FUNDING.value,
                    OfferState.OPEN.value,
                    OfferState.RESERVED.value,
                    OfferState.MATCHED.value,
                ]
            ),
        )
    )
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "wallet already has an active DUEL")

    await db.execute(
        update(DuelOffer)
        .where(
            DuelOffer.state == OfferState.RESERVED.value,
            DuelOffer.reserved_until < now,
        )
        .values(state=OfferState.OPEN.value, reserved_until=None)
    )
    invitation: DuelInvitation | None = None
    counter: DuelOffer | None = None
    creator_invite_id: str | None = None
    if body.challenge_code:
        invitation = await db.scalar(
            select(DuelInvitation)
            .where(DuelInvitation.code == body.challenge_code)
            .with_for_update()
        )
        if invitation is None or as_utc(invitation.expires_at) <= now:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "challenge not found")
        if (
            invitation.accepted_by_user_id != user.id
            or invitation.state != ChallengeState.ACCEPTED.value
            or invitation.accepted_wallet_address != wallet.address
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "challenge is not reserved for this user")
        counter = await db.get(DuelOffer, invitation.creator_offer_id)
        if (
            counter is None
            or counter.state != OfferState.OPEN.value
            or counter.user_id == user.id
            or counter.owner_wallet == wallet.address
            or counter.total_pool_nano != total_pool
            or counter.chance_bps + body.chance_bps != 10_000
        ):
            raise HTTPException(status.HTTP_409_CONFLICT, "challenge terms are no longer available")
        if not counter.invite_id_hex or counter.invite_id_hex != invitation.invite_id_hex:
            raise HTTPException(status.HTTP_409_CONFLICT, "challenge permit context is invalid")
    elif body.mode == "afk":
        counter = await db.scalar(
            select(DuelOffer)
            .where(
                DuelOffer.network == settings.ton_network_id,
                DuelOffer.contract_address == contract_address,
                DuelOffer.total_pool_nano == total_pool,
                DuelOffer.chance_bps == 10_000 - body.chance_bps,
                DuelOffer.state == OfferState.OPEN.value,
                DuelOffer.mode == "afk",
                DuelOffer.wallet_id != wallet.id,
                DuelOffer.user_id != user.id,
                DuelOffer.expires_at > now,
            )
            .order_by(DuelOffer.created_at)
            .with_for_update(skip_locked=True)
        )

    duplicate = await db.scalar(
        select(DuelOffer.id).where(
            DuelOffer.network == settings.ton_network_id,
            DuelOffer.onchain_offer_id == body.offer_id,
        )
    )
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, "offer id already exists")
    expires = now + timedelta(seconds=settings.offer_ttl_seconds)
    fee_bps = settings.duel_fee_bps
    payout = payout_after_fee(total_pool, fee_bps)
    if body.mode == "direct" and invitation is None:
        creator_invite_id = secrets.token_hex(32)
    offer = DuelOffer(
        onchain_offer_id=body.offer_id,
        query_id=body.offer_id,
        user_id=user.id,
        wallet_id=wallet.id,
        owner_wallet=wallet.address,
        network=settings.ton_network_id,
        contract_address=contract_address,
        chance_bps=body.chance_bps,
        total_pool_nano=total_pool,
        stake_nano=stake,
        opponent_stake_nano=opponent_stake,
        fee_bps=fee_bps,
        payout_nano=payout,
        commitment_hex=body.commitment_hex,
        invite_id_hex=creator_invite_id,
        direct_opponent_wallet=counter.owner_wallet if invitation and counter else None,
        counter_offer_id=counter.onchain_offer_id if counter else 0,
        mode="direct" if invitation or body.mode == "direct" else "afk",
        expires_at=expires,
    )
    db.add(offer)
    await db.flush()
    if creator_invite_id:
        invitation = DuelInvitation(
            code=secrets.token_urlsafe(9),
            creator_user_id=user.id,
            creator_offer_id=offer.id,
            invite_id_hex=creator_invite_id,
            expires_at=expires,
        )
        db.add(invitation)
    if counter:
        counter.state = OfferState.RESERVED.value
        counter.reserved_until = now + timedelta(minutes=5)
    if invitation and counter:
        invitation.state = ChallengeState.FUNDING.value
    operation = "open_offer"
    direct_valid_until = 0
    direct_signature_hex: str | None = None
    if creator_invite_id:
        operation = "open_direct_offer"
    elif invitation and counter:
        operation = "accept_direct_offer"
        direct_valid_until = int(
            min(
                expires,
                as_utc(invitation.expires_at),
                as_utc(counter.expires_at),
                now + timedelta(minutes=5),
            ).timestamp()
        )
        direct_signature_hex = sign_direct_accept_permit(
            settings.duel_invite_signing_key.get_secret_value(),
            network=offer.network,
            contract_address=offer.contract_address,
            invite_id_hex=invitation.invite_id_hex,
            counter_offer_id=counter.onchain_offer_id,
            invited_address=wallet.address,
            valid_until=direct_valid_until,
        )
    await db.commit()
    await db.refresh(offer)
    return OfferQuoteResponse(
        offer=offer_view(offer),
        transaction=ContractCall(
            operation=operation,
            query_id=offer.query_id,
            offer_id=offer.onchain_offer_id,
            counter_offer_id=offer.counter_offer_id,
            contract_address=offer.contract_address,
            amount_nano=str(offer.stake_nano + settings.offer_gas_nano),
            valid_until=int((now + timedelta(minutes=5)).timestamp()),
            network=offer.network,
            chance_bps=offer.chance_bps,
            stake_nano=str(offer.stake_nano),
            opponent_stake_nano=str(offer.opponent_stake_nano),
            total_pool_nano=str(offer.total_pool_nano),
            commitment_hex=offer.commitment_hex,
            expires_at=int(offer.expires_at.timestamp()),
            commitment_domain=0x4C4F4F60,
            fee_bps=offer.fee_bps,
            invite_id_hex=creator_invite_id,
            direct_counter_offer_id=(counter.onchain_offer_id if invitation and counter else 0),
            direct_valid_until=direct_valid_until,
            direct_signature_hex=direct_signature_hex,
        ),
    )


@router.get("/offers", response_model=list[OfferView])
async def list_offers(user: CurrentUser, db: Db, settings: Config) -> list[OfferView]:
    offers = (
        await db.scalars(
            select(DuelOffer)
            .where(
                DuelOffer.user_id == user.id,
                DuelOffer.network == settings.ton_network_id,
            )
            .order_by(DuelOffer.created_at.desc())
            .limit(50)
        )
    ).all()
    return [offer_view(offer) for offer in offers]


@router.get("", response_model=list[DuelView])
async def list_duels(user: CurrentUser, db: Db, settings: Config) -> list[DuelView]:
    offer_a = aliased(DuelOffer)
    offer_b = aliased(DuelOffer)
    rows = (
        await db.execute(
            select(Duel, offer_a, offer_b)
            .join(offer_a, Duel.offer_a_id == offer_a.id)
            .join(offer_b, Duel.offer_b_id == offer_b.id)
            .where(
                Duel.network == settings.ton_network_id,
                or_(offer_a.user_id == user.id, offer_b.user_id == user.id),
            )
            .order_by(Duel.created_at.desc())
            .limit(50)
        )
    ).all()
    result: list[DuelView] = []
    for duel, first, second in rows:
        own_offer = first if first.user_id == user.id else second
        result.append(
            DuelView(
                id=duel.id,
                onchain_duel_id=duel.onchain_duel_id,
                state=duel.state,
                offer_id=own_offer.onchain_offer_id,
                own_revealed=own_offer.revealed,
                chance_bps=own_offer.chance_bps,
                stake_nano=own_offer.stake_nano,
                opponent_stake_nano=own_offer.opponent_stake_nano,
                total_pool_nano=own_offer.total_pool_nano,
                payout_nano=own_offer.payout_nano,
                reveal_deadline=duel.reveal_deadline,
                winner_wallet=duel.winner_wallet,
                settled_tx_hash=duel.settled_tx_hash,
                settlement_proof_url=(
                    explorer_transaction_url(duel.network, duel.settled_tx_hash)
                    if duel.settled_tx_hash
                    else None
                ),
            )
        )
    return result


async def owned_offer_for_duel(
    db: Db,
    duel_id: int,
    user_id: str,
    network: int,
) -> tuple[Duel, DuelOffer]:
    duel = await db.scalar(
        select(Duel).where(Duel.onchain_duel_id == duel_id, Duel.network == network)
    )
    if duel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "duel not found")
    first = await db.get(DuelOffer, duel.offer_a_id)
    second = await db.get(DuelOffer, duel.offer_b_id)
    own_offer = first if first and first.user_id == user_id else second
    if own_offer is None or own_offer.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "duel not found")
    return duel, own_offer


@router.post("/{duel_id}/reveal-intent", response_model=ActionIntent)
async def reveal_intent(
    duel_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ActionIntent:
    duel, offer = await owned_offer_for_duel(db, duel_id, user.id, settings.ton_network_id)
    if duel.state != DuelState.REVEALING.value or offer.revealed:
        raise HTTPException(status.HTTP_409_CONFLICT, "DUEL cannot be revealed")
    if as_utc(duel.reveal_deadline) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "reveal deadline passed")
    return action_intent(
        "reveal",
        offer.contract_address,
        offer.network,
        offer_id=offer.onchain_offer_id,
        duel_id=duel.onchain_duel_id,
    )


@router.post("/offers/{offer_id}/cancel-intent", response_model=ActionIntent)
async def cancel_offer_intent(
    offer_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ActionIntent:
    offer = await db.scalar(
        select(DuelOffer).where(
            DuelOffer.onchain_offer_id == offer_id,
            DuelOffer.user_id == user.id,
            DuelOffer.network == settings.ton_network_id,
        )
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "offer not found")
    if offer.state not in {OfferState.OPEN.value, OfferState.RESERVED.value}:
        raise HTTPException(status.HTTP_409_CONFLICT, "offer cannot be cancelled")
    return action_intent(
        "cancel_offer", offer.contract_address, offer.network, offer_id=offer.onchain_offer_id
    )


@router.post("/offers/{offer_id}/expire-intent", response_model=ActionIntent)
async def expire_offer_intent(
    offer_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ActionIntent:
    offer = await db.scalar(
        select(DuelOffer).where(
            DuelOffer.onchain_offer_id == offer_id,
            DuelOffer.user_id == user.id,
            DuelOffer.network == settings.ton_network_id,
        )
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "offer not found")
    if offer.state not in {OfferState.OPEN.value, OfferState.RESERVED.value} or as_utc(
        offer.expires_at
    ) >= datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "offer is not ready for expiry")
    return action_intent(
        "expire_offer", offer.contract_address, offer.network, offer_id=offer.onchain_offer_id
    )


@router.post("/{duel_id}/expire-intent", response_model=ActionIntent)
async def expire_duel_intent(
    duel_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ActionIntent:
    duel, offer = await owned_offer_for_duel(db, duel_id, user.id, settings.ton_network_id)
    if duel.state != DuelState.REVEALING.value or as_utc(duel.reveal_deadline) >= datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "DUEL is not ready for expiry")
    return action_intent(
        "expire_duel",
        offer.contract_address,
        offer.network,
        offer_id=offer.onchain_offer_id,
        duel_id=duel.onchain_duel_id,
    )
