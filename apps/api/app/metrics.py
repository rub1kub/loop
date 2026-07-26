import time
from datetime import UTC, datetime, timedelta
from typing import Any

from prometheus_client import Gauge
from redis.exceptions import RedisError
from sqlalchemy import func, select

from .models import ChainCheckpoint
from .modules.duel.models import Duel, DuelOffer, DuelState, OfferState

DUEL_CANARY_REDIS_KEY = "loop:duel:canary:last_success"
DUEL_CANARY_PROOF_REDIS_KEY = "loop:duel:canary:last_proof"

DUEL_OFFERS = Gauge(
    "loop_duel_offers",
    "Current DUEL offer projection by mode and state.",
    ["mode", "state"],
)
DUEL_REVEALING = Gauge("loop_duel_revealing", "DUELs currently waiting for reveals.")
DUEL_OVERDUE_REVEALS = Gauge(
    "loop_duel_overdue_reveals",
    "DUELs whose reveal deadline passed without terminal projection.",
)
DUEL_STALE_FUNDING = Gauge(
    "loop_duel_stale_funding",
    "Funding intents older than the expected confirmation window.",
)
DUEL_UNBOUND_DIRECT = Gauge(
    "loop_duel_unbound_direct",
    "Matched direct offers lacking the on-chain opponent projection.",
)
DUEL_WORKER_HEALTHY = Gauge(
    "loop_duel_worker_healthy",
    "1 when the DUEL projection checkpoint heartbeat is fresh.",
)
DUEL_WORKER_HEARTBEAT_AGE = Gauge(
    "loop_duel_worker_heartbeat_age_seconds",
    "Age of the newest DUEL projection checkpoint heartbeat.",
)
DUEL_CANARY_SUCCESS = Gauge(
    "loop_duel_canary_success",
    "1 after a verified two-wallet DUEL canary has reported successfully.",
)
DUEL_CANARY_AGE = Gauge(
    "loop_duel_canary_age_seconds",
    "Age of the last verified two-wallet DUEL canary.",
)
DUEL_CANARY_MIN_WALLET_BALANCE = Gauge(
    "loop_duel_canary_min_wallet_balance_nano",
    "Lowest reported balance across the two DUEL canary wallets.",
)
DUEL_FEE_EXEMPT_SETTLEMENTS = Gauge(
    "loop_duel_fee_exempt_settlements",
    "Settled offers that waived the protocol fee with a PLUSH BRICK holder permit.",
)
DUEL_FEE_EXEMPT_OPEN = Gauge(
    "loop_duel_fee_exempt_open",
    "Offers currently holding a fee exemption that has not settled yet.",
)


async def refresh_duel_metrics(session_factory: Any, redis_client: Any) -> None:
    now = datetime.now(UTC)
    DUEL_OFFERS.clear()
    async with session_factory() as db:
        rows = (
            await db.execute(
                select(DuelOffer.mode, DuelOffer.state, func.count())
                .group_by(DuelOffer.mode, DuelOffer.state)
                .order_by(DuelOffer.mode, DuelOffer.state)
            )
        ).all()
        for mode, state, count in rows:
            DUEL_OFFERS.labels(mode=str(mode), state=str(state)).set(int(count))
        revealing = await db.scalar(
            select(func.count())
            .select_from(Duel)
            .where(Duel.state.in_([DuelState.BOOSTING.value, DuelState.REVEALING.value]))
        )
        overdue = await db.scalar(
            select(func.count())
            .select_from(Duel)
            .where(
                Duel.state.in_([DuelState.BOOSTING.value, DuelState.REVEALING.value]),
                Duel.reveal_deadline < now,
            )
        )
        stale_funding = await db.scalar(
            select(func.count())
            .select_from(DuelOffer)
            .where(
                DuelOffer.state == OfferState.PENDING_FUNDING.value,
                DuelOffer.created_at < now - timedelta(minutes=15),
            )
        )
        unbound_direct = await db.scalar(
            select(func.count())
            .select_from(DuelOffer)
            .where(
                DuelOffer.mode == "direct",
                DuelOffer.state == OfferState.MATCHED.value,
                DuelOffer.direct_opponent_wallet.is_(None),
            )
        )
        # The invite signer also authorises fee exemptions, so a leaked key
        # shows up as exempt settlements nobody sold. Volume is the detection
        # signal for a risk whose ceiling is lost protocol revenue.
        exempt_settled = await db.scalar(
            select(func.count())
            .select_from(DuelOffer)
            .where(
                DuelOffer.fee_exempt.is_(True),
                DuelOffer.state == OfferState.SETTLED.value,
            )
        )
        exempt_open = await db.scalar(
            select(func.count())
            .select_from(DuelOffer)
            .where(
                DuelOffer.fee_exempt.is_(True),
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
        heartbeat = await db.scalar(
            select(func.max(ChainCheckpoint.heartbeat_at)).where(ChainCheckpoint.key.like("duel:%"))
        )

    DUEL_REVEALING.set(int(revealing or 0))
    DUEL_OVERDUE_REVEALS.set(int(overdue or 0))
    DUEL_STALE_FUNDING.set(int(stale_funding or 0))
    DUEL_UNBOUND_DIRECT.set(int(unbound_direct or 0))
    DUEL_FEE_EXEMPT_SETTLEMENTS.set(int(exempt_settled or 0))
    DUEL_FEE_EXEMPT_OPEN.set(int(exempt_open or 0))
    if heartbeat:
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
        heartbeat_age = max(0.0, (now - heartbeat).total_seconds())
        DUEL_WORKER_HEARTBEAT_AGE.set(heartbeat_age)
        DUEL_WORKER_HEALTHY.set(1 if heartbeat_age < 120 else 0)
    else:
        DUEL_WORKER_HEARTBEAT_AGE.set(float("inf"))
        DUEL_WORKER_HEALTHY.set(0)

    try:
        async with redis_client.pipeline(transaction=False) as pipeline:
            pipeline.get(DUEL_CANARY_REDIS_KEY)
            pipeline.hget(DUEL_CANARY_PROOF_REDIS_KEY, "min_wallet_balance_nano")
            canary_timestamp, canary_min_balance = await pipeline.execute()
    except RedisError:
        canary_timestamp = None
        canary_min_balance = None
    try:
        canary_age = max(0.0, time.time() - float(canary_timestamp))
    except (TypeError, ValueError):
        DUEL_CANARY_SUCCESS.set(0)
        DUEL_CANARY_AGE.set(float("inf"))
    else:
        DUEL_CANARY_SUCCESS.set(1)
        DUEL_CANARY_AGE.set(canary_age)
    try:
        DUEL_CANARY_MIN_WALLET_BALANCE.set(float(canary_min_balance))
    except (TypeError, ValueError):
        DUEL_CANARY_MIN_WALLET_BALANCE.set(0)
