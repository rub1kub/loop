from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChallengeState, DuelInvitation, DuelOffer, OfferState


async def release_quote_reservation(db: AsyncSession, quote: DuelOffer) -> bool:
    """Release the opponent held by an unfunded quote.

    Reserving the counter before the wallet opens prevents two quotes from
    promising the same opponent. The inverse must be just as atomic: if the
    quote never reaches the contract, its counter has to become discoverable
    again. Otherwise both players can be funded on chain while matchmaking
    keeps returning "no opponent" until the five-minute reservation expires.
    """
    if quote.counter_offer_id <= 0:
        return False

    counter = await db.scalar(
        select(DuelOffer)
        .where(
            DuelOffer.network == quote.network,
            DuelOffer.onchain_offer_id == quote.counter_offer_id,
        )
        .with_for_update()
    )
    if counter is None or counter.state not in {
        OfferState.OPEN.value,
        OfferState.RESERVED.value,
    }:
        return False

    # Be defensive if a legacy race produced more than one local quote for the
    # same counter. The last live quote keeps the reservation.
    another_live_quote = await db.scalar(
        select(DuelOffer.id).where(
            DuelOffer.id != quote.id,
            DuelOffer.network == quote.network,
            DuelOffer.counter_offer_id == quote.counter_offer_id,
            DuelOffer.state == OfferState.PENDING_FUNDING.value,
            DuelOffer.expires_at > datetime.now(UTC),
        )
    )
    if another_live_quote is not None:
        return False

    if counter.state == OfferState.RESERVED.value:
        counter.state = OfferState.OPEN.value
        counter.reserved_until = None

    # A direct challenge remains accepted by the same person; only its
    # transient "wallet funding" state is rolled back so they can retry.
    if quote.mode == "direct":
        invitation = await db.scalar(
            select(DuelInvitation)
            .where(
                DuelInvitation.creator_offer_id == counter.id,
                DuelInvitation.state == ChallengeState.FUNDING.value,
                DuelInvitation.accepted_by_user_id == quote.user_id,
            )
            .with_for_update()
        )
        if invitation is not None:
            invitation.state = ChallengeState.ACCEPTED.value

    return True


async def expire_unfunded_quote(db: AsyncSession, quote: DuelOffer) -> bool:
    """Expire one local-only quote and undo every reservation it made."""
    if quote.state != OfferState.PENDING_FUNDING.value or quote.funding_tx_hash:
        return False
    quote.state = OfferState.EXPIRED.value
    await release_quote_reservation(db, quote)
    return True
