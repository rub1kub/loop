import secrets
from datetime import UTC, datetime, timedelta

import httpx
from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select, update
from sqlalchemy.orm import aliased

from ...control_state import effective_contract_fee, ensure_mode_enabled
from ...dependencies import Config, CurrentUser, Db, require_full_access
from ...models import User, Wallet
from ...referrals import get_or_create_referral_code
from ...result_cards import build_duel_invite_inline
from ...schemas import (
    ActionIntent,
    ContractCall,
    DuelBoostIntent,
    DuelBoostRequest,
    DuelBoostView,
    DuelChallengePreviewView,
    DuelView,
    OfferQuoteRequest,
    OfferQuoteResponse,
    OfferView,
    PreparedResultShareView,
)
from ...ton import (
    TonProviderError,
    explorer_transaction_url,
    sign_direct_accept_permit,
    sign_holder_fee_permit,
)
from .math import canonical_duel_terms, payout_after_fee
from .models import (
    ChallengeState,
    Duel,
    DuelBoost,
    DuelInvitation,
    DuelOffer,
    DuelState,
    OfferState,
)
from .reservations import expire_unfunded_quote


def _format_gram(nano: int) -> str:
    rendered = f"{nano / 1_000_000_000:.3f}".rstrip("0").rstrip(".")
    return rendered.replace(".", ",")


router = APIRouter(
    prefix="/duels",
    tags=["DUEL"],
    # Signing in is open to everyone before launch; the product is not.
    dependencies=[Depends(require_full_access)],
)
ACTION_GAS_NANO = 30_000_000
BOOST_GAS_NANO = 50_000_000
MAX_DUEL_CHANCE_BPS = 9_000


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
        fee_exempt=offer.fee_exempt,
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
    counter_offer_id: int = 0,
) -> ActionIntent:
    return ActionIntent(
        operation=operation,
        query_id=secrets.randbelow(9_007_199_254_740_990) + 1,
        offer_id=offer_id,
        duel_id=duel_id,
        counter_offer_id=counter_offer_id,
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
    request: Request,
    settings: Config,
) -> OfferQuoteResponse:
    await ensure_mode_enabled(db, "duel")
    if not settings.ton_transactions_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Выбранная сеть кошелька пока не поддерживается"
        )
    contract_address = settings.effective_duel_contract_address
    if not contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DUEL contract is not configured")
    # A paused contract rejects every deposit with exit code 101 and bounces the
    # stake back minus gas. Quoting one builds a transaction that cannot succeed,
    # so this refuses before a wallet is ever opened. Fail closed: a contract we
    # could not ask is treated as closed rather than assumed open.
    try:
        admin = await request.app.state.ton_client.get_contract_admin_state(
            "duel", contract_address
        )
    except TonProviderError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "DUEL временно недоступен"
        ) from exc
    if admin.paused:
        raise HTTPException(status.HTTP_409_CONFLICT, "DUEL сейчас закрыт")
    if body.chance_bps != 5_000 and not body.challenge_code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "new DUEL offers must use equal 50/50 terms",
        )
    stake, opponent_stake, total_pool = canonical_duel_terms(body.stake_nano, body.chance_bps)
    if not settings.min_pool_nano <= total_pool <= settings.max_pool_nano:
        # This reaches the player, so it says what to do rather than what failed.
        low = _format_gram(2 * ((settings.min_pool_nano + 3) // 4))
        high = _format_gram(2 * (settings.max_pool_nano // 4))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Сейчас ставка — ровно {low} GRAM"
            if low == high
            else f"Ставка должна быть от {low} до {high} GRAM",
        )
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
    stale_quotes = (
        await db.scalars(
            select(DuelOffer)
            .where(
                DuelOffer.wallet_id == wallet.id,
                DuelOffer.state == OfferState.PENDING_FUNDING.value,
                # The transaction itself is valid for five minutes. After one
                # extra minute it cannot still arrive, even though the eventual
                # on-chain offer would have had a longer lifetime.
                or_(
                    DuelOffer.expires_at < now,
                    DuelOffer.created_at < now - timedelta(minutes=6),
                ),
            )
            .with_for_update()
        )
    ).all()
    for stale in stale_quotes:
        await expire_unfunded_quote(db, stale)
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
    fee_bps = await effective_contract_fee(
        db,
        mode="duel",
        network=settings.ton_network_id,
        address=contract_address,
        fallback=settings.duel_fee_bps,
    )
    fee_exempt = False
    if settings.duel_holder_fee_enabled:
        # The exemption is proven on chain by a signed permit, so the quote
        # verifies mainnet PLUSH BRICK ownership before promising a fee-free
        # payout. A provider outage fails open to the normal fee: the player
        # keeps the exact terms shown, never better on screen than on chain.
        try:
            balance = await request.app.state.plush_ton_client.verified_jetton_balance(
                wallet.address, settings.plush_brick_master
            )
            fee_exempt = balance >= settings.holder_min_balance_nano
        except TonProviderError:
            fee_exempt = False
    payout = total_pool if fee_exempt else payout_after_fee(total_pool, fee_bps)
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
        fee_exempt=fee_exempt,
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
    holder_valid_until = 0
    holder_signature_hex: str | None = None
    if fee_exempt:
        holder_valid_until = int((now + timedelta(minutes=5)).timestamp())
        holder_signature_hex = sign_holder_fee_permit(
            settings.duel_invite_signing_key.get_secret_value(),
            network=offer.network,
            contract_address=offer.contract_address,
            offer_id=offer.onchain_offer_id,
            owner_address=wallet.address,
            valid_until=holder_valid_until,
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
            holder_fee_supported=getattr(
                request.app.state,
                "duel_holder_fee_supported",
                settings.duel_holder_fee_enabled,
            ),
            holder_valid_until=holder_valid_until,
            holder_signature_hex=holder_signature_hex,
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
    opponent_ids = {
        (second if first.user_id == user.id else first).user_id
        for _, first, second in rows
        if (second if first.user_id == user.id else first).user_id is not None
    }
    opponents: dict[str, User] = {}
    if opponent_ids:
        found = (await db.scalars(select(User).where(User.id.in_(opponent_ids)))).all()
        opponents = {person.id: person for person in found}
    duel_ids = [duel.id for duel, _, _ in rows]
    boosts = (
        (
            await db.scalars(
                select(DuelBoost)
                .where(DuelBoost.duel_id.in_(duel_ids))
                .order_by(DuelBoost.created_at)
            )
        ).all()
        if duel_ids
        else []
    )
    boosts_by_duel: dict[str, list[DuelBoost]] = {}
    for boost in boosts:
        boosts_by_duel.setdefault(boost.duel_id, []).append(boost)
    result: list[DuelView] = []
    for duel, first, second in rows:
        own_offer = first if first.user_id == user.id else second
        other_offer = second if own_offer is first else first
        opponent = opponents.get(other_offer.user_id) if other_offer.user_id else None
        boost_views = []
        for boost in boosts_by_duel.get(duel.id, []):
            boost_is_first = boost.offer_id == first.id
            boost_views.append(
                DuelBoostView(
                    revision=boost.revision,
                    side="you" if boost.offer_id == own_offer.id else "opponent",
                    amount_nano=boost.amount_nano,
                    chance_bps=boost.chance_a_bps if boost_is_first else boost.chance_b_bps,
                    tx_hash=boost.tx_hash,
                    proof_url=explorer_transaction_url(duel.network, boost.tx_hash),
                    created_at=boost.created_at,
                )
            )
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
                fee_exempt=own_offer.fee_exempt,
                payout_nano=own_offer.payout_nano,
                boost_deadline=duel.boost_deadline,
                hard_deadline=duel.hard_deadline,
                boost_revision=duel.boost_revision,
                reveal_deadline=duel.reveal_deadline,
                boost_events=boost_views,
                opponent_first_name=opponent.first_name if opponent else None,
                opponent_username=opponent.username if opponent else None,
                opponent_has_photo=bool(opponent and opponent.photo_url),
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


@router.post("/{duel_id}/boost-intent", response_model=DuelBoostIntent)
async def boost_intent(
    duel_id: int,
    body: DuelBoostRequest,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> DuelBoostIntent:
    duel, offer = await owned_offer_for_duel(db, duel_id, user.id, settings.ton_network_id)
    now = datetime.now(UTC)
    if (
        duel.state != DuelState.BOOSTING.value
        or duel.boost_deadline is None
        or duel.hard_deadline is None
        or as_utc(duel.boost_deadline) < now
        or as_utc(duel.hard_deadline) < now
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Время усиления закончилось")
    if duel.boost_revision != body.expected_revision:
        raise HTTPException(status.HTTP_409_CONFLICT, "Состояние изменилось. Обнови DUEL")

    first = await db.get(DuelOffer, duel.offer_a_id)
    second = await db.get(DuelOffer, duel.offer_b_id)
    if first is None or second is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "DUEL ещё не подтверждён")
    boosted_stake = offer.stake_nano + body.amount_nano
    total_pool = first.stake_nano + second.stake_nano + body.amount_nano
    chance_bps = boosted_stake * 10_000 // total_pool
    if chance_bps > MAX_DUEL_CHANCE_BPS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Максимальный перевес — 90%")
    if chance_bps < body.min_chance_bps:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сумма уже изменилась. Проверь новый шанс")

    valid_until = min(
        int(as_utc(duel.hard_deadline).timestamp()),
        int((now + timedelta(seconds=45)).timestamp()),
    )
    if valid_until <= int(now.timestamp()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Время усиления закончилось")
    return DuelBoostIntent(
        operation="boost_duel",
        query_id=secrets.randbelow(9_007_199_254_740_990) + 1,
        offer_id=offer.onchain_offer_id,
        duel_id=duel.onchain_duel_id,
        contract_address=offer.contract_address,
        amount_nano=str(body.amount_nano + BOOST_GAS_NANO),
        boost_nano=str(body.amount_nano),
        expected_revision=body.expected_revision,
        min_chance_bps=body.min_chance_bps,
        valid_until=valid_until,
        network=offer.network,
    )


@router.post("/{duel_id}/reveal-intent", response_model=ActionIntent)
async def reveal_intent(
    duel_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ActionIntent:
    duel, offer = await owned_offer_for_duel(db, duel_id, user.id, settings.ton_network_id)
    now = datetime.now(UTC)
    boost_finished = duel.boost_deadline is None or as_utc(duel.boost_deadline) < now
    if (
        duel.state not in {DuelState.BOOSTING.value, DuelState.REVEALING.value}
        or not boost_finished
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "DUEL ещё можно усилить")
    if offer.revealed:
        raise HTTPException(status.HTTP_409_CONFLICT, "DUEL cannot be revealed")
    if as_utc(duel.reveal_deadline) <= now:
        raise HTTPException(status.HTTP_409_CONFLICT, "reveal deadline passed")
    return action_intent(
        "reveal",
        offer.contract_address,
        offer.network,
        offer_id=offer.onchain_offer_id,
        duel_id=duel.onchain_duel_id,
    )


@router.post("/offers/{offer_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
async def discard_unfunded_offer(
    offer_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> Response:
    """Drop a quote after an explicit wallet refusal.

    A quote reserves the wallet's single offer slot before the wallet is even
    opened, so a declined signature used to leave the player "searching" for
    fifteen minutes against nothing, unable to start again. Ambiguous wallet
    responses must not call this endpoint: only the chain projection can prove
    whether a message broadcast just before an SDK error was accepted.
    """
    offer = await db.scalar(
        select(DuelOffer)
        .where(
            DuelOffer.onchain_offer_id == offer_id,
            DuelOffer.user_id == user.id,
            DuelOffer.network == settings.ton_network_id,
        )
        .with_for_update()
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "offer not found")
    # Anything the chain has already seen belongs to the chain, not to a button.
    if offer.state != OfferState.PENDING_FUNDING.value or offer.funding_tx_hash:
        raise HTTPException(status.HTTP_409_CONFLICT, "offer is already funded")
    await expire_unfunded_quote(db, offer)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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

@router.post("/offers/{offer_id}/match-intent", response_model=ActionIntent)
async def match_offer_intent(
    offer_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ActionIntent:
    """Marry two open offers that quoted past each other.

    Matching normally happens at quote time: the newcomer's transaction carries
    the id of an already-open counter offer. Two people who tap within the
    funding window each see an empty room, both open parallel offers, and then
    stand side by side unable to see each other for fifteen minutes. The
    contract's MatchOffers is permissionless — either player may send it for
    gas money — so the app offers exactly that the moment a complement appears.
    """
    mine = await db.scalar(
        select(DuelOffer).where(
            DuelOffer.onchain_offer_id == offer_id,
            DuelOffer.user_id == user.id,
            DuelOffer.network == settings.ton_network_id,
        )
    )
    now = datetime.now(UTC)
    if (
        mine is None
        or mine.state != OfferState.OPEN.value
        or mine.mode != "afk"
        or as_utc(mine.expires_at) <= now
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ставка не ждёт соперника")
    counter = await db.scalar(
        select(DuelOffer)
        .where(
            DuelOffer.network == settings.ton_network_id,
            DuelOffer.contract_address == mine.contract_address,
            DuelOffer.user_id != user.id,
            DuelOffer.mode == "afk",
            DuelOffer.state == OfferState.OPEN.value,
            DuelOffer.funding_tx_hash.is_not(None),
            DuelOffer.total_pool_nano == mine.total_pool_nano,
            DuelOffer.chance_bps == 10_000 - mine.chance_bps,
            DuelOffer.expires_at > now,
        )
        .order_by(DuelOffer.created_at)
    )
    if counter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Соперника пока нет")
    return action_intent(
        "match_offers",
        mine.contract_address,
        mine.network,
        offer_id=mine.onchain_offer_id,
        counter_offer_id=counter.onchain_offer_id,
    )


@router.get("/offers/{offer_id}/preview", response_model=DuelChallengePreviewView)
async def duel_offer_preview(
    offer_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> DuelChallengePreviewView:
    del user  # any signed-in person may look at a challenge they were sent
    offer = await db.scalar(
        select(DuelOffer).where(
            DuelOffer.onchain_offer_id == offer_id,
            DuelOffer.network == settings.ton_network_id,
        )
    )
    if offer is None or offer.user_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вызов не найден")
    creator = await db.get(User, offer.user_id)
    if creator is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вызов не найден")
    still_open = as_utc(offer.expires_at) > datetime.now(UTC) and (
        offer.state == OfferState.OPEN.value
        or (offer.mode == "afk" and offer.state == OfferState.RESERVED.value)
    )
    return DuelChallengePreviewView(
        creator_first_name=creator.first_name,
        creator_username=creator.username,
        stake_nano=offer.opponent_stake_nano,
        receiver_chance_bps=10_000 - offer.chance_bps,
        open=still_open,
    )


@router.post("/offers/{offer_id}/share", response_model=PreparedResultShareView)
async def prepare_duel_share(
    offer_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
    request: Request,
) -> PreparedResultShareView:
    """A ready-made challenge card, so inviting somebody is one tap.

    The old button either dropped the player out of the app into an inline
    query with `duel 12345` visible in the input, or sent a bare link with no
    stake, no odds and no button. Both closed the app to do it. This is the
    same machinery the result card already uses: Telegram opens a chat picker
    over the app and one tap sends the card.
    """
    offer = await db.scalar(
        select(DuelOffer).where(
            DuelOffer.onchain_offer_id == offer_id,
            DuelOffer.user_id == user.id,
            DuelOffer.network == settings.ton_network_id,
        )
    )
    if offer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вызов не найден")
    shareable = offer.state == OfferState.OPEN.value or (
        offer.mode == "afk" and offer.state == OfferState.RESERVED.value
    )
    if not shareable or as_utc(offer.expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_409_CONFLICT, "Вызов уже неактуален")
    bot = request.app.state.bot
    if bot is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram сейчас недоступен")

    # The card's button says "принять вызов", so the link has to land the
    # reader on that exact challenge — not on a bare search screen where the
    # promise quietly evaporates.
    intent = f"duel_o{offer.onchain_offer_id}"
    if offer.mode == "direct":
        challenge = await db.scalar(
            select(DuelInvitation).where(DuelInvitation.creator_offer_id == offer.id)
        )
        # The address-bound flow mints the code only once the creator has signed
        # on chain; without it the contract would refuse the acceptance permit.
        if challenge is None or challenge.state != ChallengeState.OPEN.value:
            raise HTTPException(status.HTTP_409_CONFLICT, "Вызов ещё не подтверждён сетью")
        intent = f"duel_{challenge.code}"
    referral = await get_or_create_referral_code(db, user.id)
    accept_url = (
        f"https://t.me/{settings.bot_username.removeprefix('@')}"
        f"?startapp={intent}-ref_{referral.code}"
    )
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user.telegram_id,
            result=build_duel_invite_inline(
                settings=settings,
                offer_id=offer.id,
                accept_url=accept_url,
                opponent_stake_nano=offer.opponent_stake_nano,
                receiver_chance_bps=10_000 - offer.chance_bps,
                profit_nano=max(offer.payout_nano - offer.opponent_stake_nano, 0),
                first_name=user.first_name,
            ),
            allow_user_chats=True,
            allow_bot_chats=False,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except TelegramAPIError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram сейчас недоступен"
        ) from exc
    expiration = prepared.expiration_date
    if isinstance(expiration, int):
        expiration = datetime.fromtimestamp(expiration, UTC)
    elif isinstance(expiration, timedelta):
        expiration = datetime.now(UTC) + expiration
    elif expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    await db.commit()
    return PreparedResultShareView(
        prepared_message_id=prepared.id,
        expiration_date=expiration,
        fallback_query=f"duel {offer.onchain_offer_id}",
    )

@router.get(
    "/{duel_id}/opponent-avatar",
    response_class=Response,
    include_in_schema=False,
)
async def opponent_avatar(
    duel_id: int,
    user: CurrentUser,
    db: Db,
    settings: Config,
    request: Request,
) -> Response:
    """The other player's Telegram avatar, for one's own duel only.

    A duel is a person against a person, and a face makes that true on the
    screen. Proxied exactly like one's own avatar — same trusted hosts, same
    size ceiling — and reachable only by a participant of this duel, so it
    leaks nothing an opponent has not already shown by fighting you.
    """
    duel, own_offer = await owned_offer_for_duel(db, duel_id, user.id, settings.ton_network_id)
    other_id = duel.offer_b_id if own_offer.id == duel.offer_a_id else duel.offer_a_id
    other_offer = await db.get(DuelOffer, other_id)
    opponent = (
        await db.get(User, other_offer.user_id)
        if other_offer and other_offer.user_id
        else None
    )
    from ...routes import is_telegram_photo_url

    if opponent is None or not opponent.photo_url or not is_telegram_photo_url(opponent.photo_url):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "avatar unavailable")
    try:
        upstream = await request.app.state.http.get(opponent.photo_url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "avatar unavailable") from exc
    media_type = upstream.headers.get("content-type", "").split(";", 1)[0].lower()
    if (
        upstream.status_code != status.HTTP_200_OK
        or not is_telegram_photo_url(str(upstream.url))
        or media_type not in {"image/jpeg", "image/png", "image/webp"}
        or len(upstream.content) > 1_000_000
    ):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "avatar unavailable")
    return Response(
        content=upstream.content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )
