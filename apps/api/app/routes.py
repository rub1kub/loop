import secrets
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
import structlog
from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from .control_state import effective_contract_fee, ensure_mode_enabled
from .dependencies import Config, CurrentUser, Db
from .models import (
    AuthExchange,
    ReferralAttribution,
    ReferralCode,
    ReferralPayoutRequest,
    ReferralReward,
    User,
    Wallet,
)
from .modules.bank.models import BankPosition, BankPositionStatus
from .modules.duel.models import (
    ChallengeState,
    DuelInvitation,
    MatchmakingOffer,
    OfferState,
)
from .rating import build_rating
from .chain_worker import REFERRAL_FEE_SHARE_BPS
from .referrals import get_or_create_referral_code
from .result_cards import (
    INVITE_VARIANTS,
    build_invite_inline,
    render_duel_invite_card,
    render_invite_card,
)
from .schemas import (
    AnnouncementView,
    AuthResponse,
    ContractStateView,
    DuelStakeLimitsView,
    InviteView,
    JettonBalanceView,
    ModeStatsView,
    PlushBrickView,
    PrelaunchLeaderView,
    PrelaunchView,
    PreparedResultShareView,
    ProfileView,
    RatingView,
    ReferralPayoutRequestBody,
    ReferralPayoutRequestView,
    ReferralRewardView,
    ReferralView,
    SettingsUpdate,
    TelegramAuthRequest,
    UserView,
    WalletChallengeResponse,
    WalletVerifyRequest,
    WalletView,
)
from .security import (
    AuthenticationError,
    issue_session,
    validate_telegram_init_data,
    verify_ton_proof,
)
from .ton import TonProviderError, explorer_transaction_url, normalize_address

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1")
# How long a confirmed PLUSH BRICK balance answers for the profile before the
# indexer is asked again. Long enough to keep polling clients off the rate
# limit, short enough that a fresh purchase shows within a minute.
PLUSH_HOLDER_CACHE_TTL = 60.0
MAX_TELEGRAM_AVATAR_BYTES = 1_000_000
TELEGRAM_PHOTO_HOSTS = ("t.me", "telegram.me", "telegram.org", "telesco.pe", "cdn-telegram.org")


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_telegram_photo_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    trusted_host = any(
        host == suffix or host.endswith(f".{suffix}") for suffix in TELEGRAM_PHOTO_HOSTS
    )
    return (
        parsed.scheme == "https"
        and trusted_host
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
    )


def user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        photo_url=user.photo_url,
        onboarding_seen=user.onboarding_seen,
        onboarding_enabled=user.onboarding_enabled,
        result_notifications_enabled=user.result_notifications_enabled,
    )


async def record_referral_attribution(
    db: Db,
    user: User,
    start_param: str | None,
) -> None:
    # A start parameter carries an intention as well as an invitation, and until
    # now only the bare invitation counted. Every duel ever shared arrived as
    # `duel` or `duel_<challenge>`, so the player who brought a friend in was
    # credited with nothing — on the most viral action in the product. The
    # referral may now ride along at the end, after `-ref_`, which cannot
    # collide with the hex challenge code in front of it.
    if not start_param:
        return
    _, separator, trailing = start_param.rpartition("-ref_")
    if separator:
        code = trailing
    elif start_param.startswith("ref_"):
        code = start_param[4:]
    else:
        return
    referral = await db.get(ReferralCode, code)
    if referral is None or referral.owner_user_id == user.id:
        return
    owner = await db.get(User, referral.owner_user_id)
    if owner is None or owner.telegram_id == user.telegram_id:
        return
    existing = await db.scalar(
        select(ReferralAttribution.id).where(ReferralAttribution.invitee_user_id == user.id)
    )
    if existing is not None:
        return
    user.referred_by_id = owner.id
    db.add(
        ReferralAttribution(
            inviter_user_id=owner.id,
            invitee_user_id=user.id,
            code=code,
        )
    )


@router.post("/auth/telegram", response_model=AuthResponse)
async def authenticate(body: TelegramAuthRequest, db: Db, settings: Config) -> AuthResponse:
    try:
        identity = validate_telegram_init_data(
            body.init_data, settings.bot_token.get_secret_value(), settings
        )
    except AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    # Everyone signs in, whitelisted or not: recording who invited whom only
    # happens here, and a closed door would leave the whole warm-up week
    # counting nothing. What the whitelist still gates is the product — see
    # require_full_access.
    user = await db.scalar(select(User).where(User.telegram_id == identity.telegram_id))
    if user is None:
        user = User(
            telegram_id=identity.telegram_id,
            username=identity.username,
            first_name=identity.first_name,
            last_name=identity.last_name,
            language_code=identity.language_code,
            photo_url=identity.photo_url,
        )
        db.add(user)
        await db.flush()
        await record_referral_attribution(db, user, identity.start_param)
    else:
        user.username = identity.username
        user.first_name = identity.first_name
        user.last_name = identity.last_name
        user.language_code = identity.language_code
        user.photo_url = identity.photo_url

    issued_at = identity.auth_date
    session_id = identity.digest.hex()[:32]
    token, expires = issue_session(user.id, user.telegram_id, session_id, settings, issued_at)
    exchange = await db.get(AuthExchange, identity.digest)
    if exchange is None:
        db.add(
            AuthExchange(
                digest=identity.digest,
                user_id=user.id,
                auth_date=identity.auth_date,
                expires_at=expires,
            )
        )
    elif exchange.user_id != user.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "initData replay rejected")
    else:
        exchange.expires_at = expires
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = await db.get(AuthExchange, identity.digest)
        if existing is None or existing.user_id != user.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "initData replay rejected") from exc
    return AuthResponse(access_token=token, expires_at=expires, user=user_view(user))


@router.get("/me", response_model=ProfileView)
async def get_me(user: CurrentUser, db: Db, request: Request, settings: Config) -> ProfileView:
    wallet = await db.scalar(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.active.is_(True))
    )
    bank_total = await db.scalar(
        select(func.count()).select_from(BankPosition).where(BankPosition.user_id == user.id)
    )
    bank_completed = await db.scalar(
        select(func.count())
        .select_from(BankPosition)
        .where(
            BankPosition.user_id == user.id,
            BankPosition.current_status == BankPositionStatus.PAYOUT_SENT.value,
        )
    )
    bank_active = await db.scalar(
        select(func.count())
        .select_from(BankPosition)
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
    )
    duel_total = await db.scalar(
        select(func.count())
        .select_from(MatchmakingOffer)
        .where(MatchmakingOffer.user_id == user.id)
    )
    duel_completed = await db.scalar(
        select(func.count())
        .select_from(MatchmakingOffer)
        .where(
            MatchmakingOffer.user_id == user.id,
            MatchmakingOffer.state.in_([OfferState.SETTLED.value, OfferState.REFUNDED.value]),
        )
    )
    duel_active = await db.scalar(
        select(func.count())
        .select_from(MatchmakingOffer)
        .where(
            MatchmakingOffer.user_id == user.id,
            MatchmakingOffer.state.in_(
                [
                    OfferState.PENDING_FUNDING.value,
                    OfferState.OPEN.value,
                    OfferState.RESERVED.value,
                    OfferState.MATCHED.value,
                ]
            ),
        )
    )
    plush_balance = 0
    plush_verified = False
    if wallet is not None and hasattr(request.app.state, "plush_ton_client"):
        # Every open client polls this endpoint every few seconds, and each
        # poll used to ask the indexer afresh. Past a handful of users that is
        # a rate limit, the lookup fails, and the failure silently erased the
        # holder flag: a person whose duels genuinely settle fee-free watched
        # the screen claim 10% off them. Money never moved wrongly — the quote
        # path verifies on its own — but a display should not flicker between
        # truths depending on the provider's mood. So the last confirmed answer
        # is kept per wallet: served while fresh, refreshed after a minute, and
        # held onto when the provider fails, because ownership of a token does
        # not vanish with a timeout.
        cache: dict[str, tuple[float, int]] = request.app.state.plush_holder_cache
        cached = cache.get(wallet.address)
        age = (time.monotonic() - cached[0]) if cached else None
        if cached is not None and age is not None and age < PLUSH_HOLDER_CACHE_TTL:
            plush_balance, plush_verified = cached[1], True
        else:
            try:
                plush = await request.app.state.plush_ton_client.get_jetton_wallet(
                    wallet.address, settings.plush_brick_master
                )
                plush_balance = plush.balance_nano
                plush_verified = True
                cache[wallet.address] = (time.monotonic(), plush_balance)
            except TonProviderError:
                if cached is not None:
                    plush_balance, plush_verified = cached[1], True
    holder = plush_verified and plush_balance >= settings.holder_min_balance_nano
    duel_fee_bps = await effective_contract_fee(
        db,
        mode="duel",
        network=settings.ton_network_id,
        address=settings.effective_duel_contract_address,
        fallback=settings.duel_fee_bps,
    )
    return ProfileView(
        user=user_view(user),
        app_open=settings.app_open_for(user.telegram_id),
        launch_at=settings.launch_at,
        wallet=(
            WalletView(
                address=wallet.address,
                network=wallet.network,
                verified_at=wallet.verified_at,
            )
            if wallet
            else None
        ),
        bank=ModeStatsView(
            active=bank_active or 0,
            completed=bank_completed or 0,
            total=bank_total or 0,
        ),
        duel=ModeStatsView(
            active=duel_active or 0,
            completed=duel_completed or 0,
            total=duel_total or 0,
        ),
        announcement=(
            AnnouncementView(text=announcement[0], url=announcement[1] or None)
            if (announcement := settings.announcement_for(user.telegram_id))
            else None
        ),
        duel_stake=DuelStakeLimitsView(
            # An equal duel pools four quarter units, so a stake always lands on
            # an even number of them; round the bounds onto that grid.
            min_stake_nano=2 * ((settings.min_pool_nano + 3) // 4),
            max_stake_nano=2 * (settings.max_pool_nano // 4),
        ),
        plush_brick=PlushBrickView(
            verified=plush_verified,
            balance_nano=plush_balance,
            holder=holder,
            duel_fee_bps=duel_fee_bps,
            # Active only when DuelEscrow v1.4 holder permits are enabled:
            # against v1.3 bytecode a reported discount would disagree with
            # the actual settlement, so startup refuses that combination.
            fee_discount_active=settings.duel_holder_fee_enabled and holder,
        ),
    )


@router.get(
    "/me/avatar",
    response_class=Response,
    responses={
        status.HTTP_200_OK: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}},
        status.HTTP_404_NOT_FOUND: {"description": "Telegram avatar is unavailable"},
    },
)
async def get_my_avatar(user: CurrentUser, request: Request) -> Response:
    if not user.photo_url or not is_telegram_photo_url(user.photo_url):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram avatar is unavailable")
    try:
        upstream = await request.app.state.http.get(user.photo_url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Telegram avatar is temporarily unavailable"
        ) from exc
    media_type = upstream.headers.get("content-type", "").split(";", 1)[0].lower()
    if (
        upstream.status_code != status.HTTP_200_OK
        or not is_telegram_photo_url(str(upstream.url))
        or media_type not in {"image/jpeg", "image/png", "image/webp"}
        or len(upstream.content) > MAX_TELEGRAM_AVATAR_BYTES
    ):
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Telegram avatar is temporarily unavailable"
        )
    return Response(
        content=upstream.content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.patch("/me/settings", response_model=UserView)
async def update_settings(body: SettingsUpdate, user: CurrentUser, db: Db) -> UserView:
    if body.onboarding_seen is not None:
        user.onboarding_seen = body.onboarding_seen
    if body.onboarding_enabled is not None:
        user.onboarding_enabled = body.onboarding_enabled
    if body.result_notifications_enabled is not None:
        user.result_notifications_enabled = body.result_notifications_enabled
    await db.commit()
    return user_view(user)


@router.post("/wallet/challenge", response_model=WalletChallengeResponse)
async def wallet_challenge(
    user: CurrentUser,
    request: Request,
    settings: Config,
) -> WalletChallengeResponse:
    payload = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(seconds=settings.ton_proof_ttl_seconds)
    await request.app.state.challenge_store.put(
        payload,
        {
            "user_id": user.id,
            "network": settings.ton_network_id,
            "domain": settings.public_origin.removeprefix("https://").removeprefix("http://"),
        },
        settings.ton_proof_ttl_seconds,
    )
    return WalletChallengeResponse(payload=payload, expires_at=expires)


@router.post("/wallet/verify", response_model=WalletView)
async def wallet_verify(
    body: WalletVerifyRequest,
    user: CurrentUser,
    db: Db,
    request: Request,
    settings: Config,
) -> WalletView:
    if body.network != settings.ton_network_id or not settings.ton_transactions_enabled:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Выбранная сеть кошелька пока не поддерживается"
        )
    challenge = await request.app.state.challenge_store.consume(body.proof.payload)
    if not challenge or challenge.get("user_id") != user.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wallet challenge is invalid or used")
    try:
        onchain_key = await request.app.state.ton_client.get_wallet_public_key(body.address)
        if not secrets.compare_digest(onchain_key.lower(), body.public_key.lower()):
            raise AuthenticationError("wallet public key mismatch")
        address = verify_ton_proof(
            address=body.address,
            network=body.network,
            public_key_hex=onchain_key,
            timestamp=body.proof.timestamp,
            domain=body.proof.domain.value,
            domain_length=body.proof.domain.length_bytes,
            signature_b64=body.proof.signature,
            payload=body.proof.payload,
            expected_payload=body.proof.payload,
            settings=settings,
        )
    except (AuthenticationError, TonProviderError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    existing = await db.scalar(
        select(Wallet).where(Wallet.network == body.network, Wallet.address == address)
    )
    if existing and existing.user_id != user.id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Этот кошелёк уже привязан к другому аккаунту"
        )
    current = await db.scalar(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.active.is_(True)).with_for_update()
    )
    if current and current.address != address:
        bank_active = await db.scalar(
            select(BankPosition.id).where(
                BankPosition.wallet_id == current.id,
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
        # Scoped to the current network like the BANK check above it. Without
        # that, an offer left open on a network the application has since moved
        # away from blocks the user from ever linking a wallet again — and it
        # cannot be settled, because nothing here talks to that network anymore.
        duel_active = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.wallet_id == current.id,
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.state.in_(
                    [
                        OfferState.PENDING_FUNDING.value,
                        OfferState.OPEN.value,
                        OfferState.RESERVED.value,
                        OfferState.MATCHED.value,
                    ]
                ),
            )
        )
        if bank_active or duel_active:
            # Written in Russian on purpose: the interface only shows a message
            # it recognises as written for people, and an English one arrived as
            # the blank "не удалось подтвердить кошелёк". A refusal this
            # legitimate has to say which side is holding the wallet.
            #
            # And it has to say the right thing to do. An offer whose time has
            # run out is never going to settle, so telling that player to wait
            # is telling them to wait forever: the stake is theirs to take back,
            # with a signature from the wallet that placed it.
            if duel_active is not None and as_utc(duel_active.expires_at) <= datetime.now(UTC):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Ставка в DUEL просрочена и ждёт возврата. Верни её на этот кошелёк "
                    "в разделе DUEL, потом подключай новый.",
                )
            waiting = " и ".join(
                name for name, held in (("BANK", bank_active), ("DUEL", duel_active)) if held
            )
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Кошелёк занят: {waiting} ещё не завершён. "
                "Дождись выплаты или расчёта, потом меняй кошелёк.",
            )
        current.active = False
        # One active wallet per user is a unique index, and a single flush lets
        # SQLAlchemy order the two UPDATEs however it likes. When it activates
        # the new row before releasing the old one the database sees two active
        # wallets and rejects the write, which surfaced as a bare 500 and read
        # to the user as a connection error.
        await db.flush()
    wallet = existing or Wallet(
        user_id=user.id,
        network=body.network,
        address=address,
        public_key=onchain_key.lower(),
    )
    wallet.active = True
    wallet.verified_at = datetime.now(UTC)
    db.add(wallet)
    await db.flush()
    await db.execute(
        update(BankPosition)
        .where(
            BankPosition.user_id.is_(None),
            BankPosition.wallet_id.is_(None),
            BankPosition.network == body.network,
            BankPosition.contract_address == settings.bank_contract_address,
            func.lower(BankPosition.owner_wallet) == address.lower(),
        )
        .values(user_id=user.id, wallet_id=wallet.id)
    )
    await db.commit()
    return WalletView(
        address=wallet.address,
        network=wallet.network,
        verified_at=wallet.verified_at,
    )


async def contract_state(
    mode: str,
    user: User,
    db: Db,
    request: Request,
    settings: Config,
) -> ContractStateView:
    if mode == "bank":
        address = settings.bank_contract_address
        expected = settings.bank_contract_code_hash
    elif mode == "duel":
        address = settings.effective_duel_contract_address
        expected = settings.effective_duel_contract_code_hash
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown contract mode")
    if not address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "contract is not configured")
    wallet = await db.scalar(
        select(Wallet).where(
            Wallet.user_id == user.id,
            Wallet.network == settings.ton_network_id,
            Wallet.active.is_(True),
        )
    )
    try:
        contract = await request.app.state.ton_client.get_contract_state(address)
        wallet_balance = (
            await request.app.state.ton_client.get_native_balance(wallet.address)
            if wallet
            else None
        )
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    try:
        paused: bool | None = (
            await request.app.state.ton_client.get_contract_admin_state(mode, address)
        ).paused
    except TonProviderError:
        # Reported as unknown rather than as open: the caller decides how much
        # to trust a contract it could not ask.
        paused = None
    expected_hash = expected.removeprefix("0x").upper()
    return ContractStateView(
        mode=mode,
        network=settings.ton_network_id,
        address=contract.address,
        status=contract.status,
        balance_nano=contract.balance_nano,
        code_hash=contract.code_hash,
        code_hash_matches=bool(expected_hash)
        and secrets.compare_digest(contract.code_hash, expected_hash),
        paused=paused,
        last_transaction_hash=contract.last_transaction_hash,
        last_transaction_url=(
            explorer_transaction_url(settings.ton_network_id, contract.last_transaction_hash)
            if contract.last_transaction_hash
            else None
        ),
        wallet_balance_nano=wallet_balance,
    )


@router.get("/onchain/contracts/{mode}", response_model=ContractStateView)
async def onchain_contract(
    mode: str,
    user: CurrentUser,
    db: Db,
    request: Request,
    settings: Config,
) -> ContractStateView:
    return await contract_state(mode, user, db, request, settings)


@router.get("/onchain/contract", response_model=ContractStateView, include_in_schema=False)
async def legacy_onchain_contract(
    user: CurrentUser,
    db: Db,
    request: Request,
    settings: Config,
) -> ContractStateView:
    return await contract_state("duel", user, db, request, settings)


@router.get("/onchain/jettons/{jetton_master}", response_model=JettonBalanceView)
async def onchain_jetton(
    jetton_master: str,
    user: CurrentUser,
    db: Db,
    request: Request,
    settings: Config,
) -> JettonBalanceView:
    if jetton_master != settings.plush_brick_master:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Этот токен не поддерживается")
    wallet = await db.scalar(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.active.is_(True))
    )
    if wallet is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "verified wallet required")
    try:
        state = await request.app.state.plush_ton_client.get_jetton_wallet(
            wallet.address, jetton_master
        )
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return JettonBalanceView(
        network=settings.plush_brick_network_id,
        owner_address=state.owner_address,
        jetton_master=state.jetton_master,
        jetton_wallet=state.wallet_address,
        balance_nano=state.balance_nano,
        verified=True,
    )


@router.get("/referrals", response_model=ReferralView)
async def referrals(user: CurrentUser, db: Db, settings: Config) -> ReferralView:
    try:
        referral = await get_or_create_referral_code(db, user.id)
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "could not create referral code",
        ) from exc
    invited = await db.scalar(
        select(func.count())
        .select_from(ReferralAttribution)
        .where(ReferralAttribution.inviter_user_id == user.id)
    )
    qualified = await db.scalar(
        select(func.count())
        .select_from(ReferralAttribution)
        .where(
            ReferralAttribution.inviter_user_id == user.id,
            ReferralAttribution.status == "qualified",
        )
    )
    # Totals over everything ever accrued. They used to be summed over the
    # fifty rows the feed happens to show, so the headline figure silently
    # stopped growing at whatever the fifty-first reward brought.
    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(ReferralReward.reward_points), 0),
                func.coalesce(func.sum(ReferralReward.reward_nano), 0),
            )
            .select_from(ReferralReward)
            .join(
                ReferralAttribution,
                ReferralReward.attribution_id == ReferralAttribution.id,
            )
            .where(ReferralAttribution.inviter_user_id == user.id)
        )
    ).one()
    rewards = (
        await db.execute(
            select(ReferralReward, User)
            .join(
                ReferralAttribution,
                ReferralReward.attribution_id == ReferralAttribution.id,
            )
            .join(User, User.id == ReferralAttribution.invitee_user_id)
            .where(ReferralAttribution.inviter_user_id == user.id)
            .order_by(ReferralReward.created_at.desc())
            .limit(50)
        )
    ).all()
    # A fee-share reward is caused by one confirmed deposit, and naming that
    # deposit is what turns the feed from bookkeeping into proof: "Иван внёс
    # 3 GRAM → тебе +0,06". The cause carries the position id.
    position_ids = [
        reward.cause.removeprefix("fee_share:")
        for reward, _ in rewards
        if reward.cause.startswith("fee_share:")
    ]
    principals: dict[str, int] = {}
    if position_ids:
        rows = (
            await db.execute(
                select(BankPosition.id, BankPosition.principal_nano).where(
                    BankPosition.id.in_(position_ids)
                )
            )
        ).all()
        principals = {row[0]: row[1] for row in rows}
    paid = await db.scalar(
        select(func.coalesce(func.sum(ReferralReward.reward_nano), 0))
        .select_from(ReferralReward)
        .join(
            ReferralAttribution,
            ReferralReward.attribution_id == ReferralAttribution.id,
        )
        .where(
            ReferralAttribution.inviter_user_id == user.id,
            ReferralReward.payout_tx_hash.is_not(None),
        )
    )
    pending = await db.scalar(
        select(ReferralPayoutRequest).where(
            ReferralPayoutRequest.user_id == user.id,
            ReferralPayoutRequest.state == "requested",
        )
    )
    available = max(int(totals[1]) - int(paid or 0) - (pending.amount_nano if pending else 0), 0)
    return ReferralView(
        code=referral.code,
        url=f"https://t.me/{settings.bot_username}?startapp=ref_{referral.code}",
        invited=invited or 0,
        qualified=qualified or 0,
        reward_points=int(totals[0]),
        reward_nano=int(totals[1]),
        # The screen used to print a bare "3%" for everybody. Two inviters were
        # promised 10%, and nothing told them or the screen that it changed —
        # the rate here is the one that will actually apply to their next
        # accrual, not the standard one.
        share_bps=settings.referral_share_bps_for(user.telegram_id, REFERRAL_FEE_SHARE_BPS),
        available_nano=available,
        minimum_payout_nano=settings.referral_min_payout_nano,
        pending_payout=(
            ReferralPayoutRequestView(
                id=pending.id,
                address=pending.address,
                amount_nano=pending.amount_nano,
                state=pending.state,
                created_at=pending.created_at,
            )
            if pending
            else None
        ),
        history=[
            ReferralRewardView(
                cause=reward.cause,
                reward_points=reward.reward_points,
                reward_nano=reward.reward_nano,
                payout_tx_hash=reward.payout_tx_hash,
                created_at=reward.created_at,
                invitee_first_name=invitee.first_name,
                invitee_username=invitee.username,
                deposit_nano=principals.get(reward.cause.removeprefix("fee_share:"), 0),
            )
            for reward, invitee in rewards
        ],
    )


@router.post("/referrals/payout", response_model=ReferralPayoutRequestView)
async def request_referral_payout(
    body: ReferralPayoutRequestBody,
    user: CurrentUser,
    db: Db,
    settings: Config,
    request: Request,
) -> ReferralPayoutRequestView:
    """Ask for the referral share to be sent to a wallet.

    Paying is still done by hand from the treasury; what this adds is a place
    to ask. The amount is fixed at the moment of asking, so later accruals do
    not silently change what was agreed, and one open request at a time keeps
    the same money from being requested twice.
    """
    try:
        address = normalize_address(body.address)
    except TonProviderError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Проверь адрес кошелька"
        ) from exc
    open_request = await db.scalar(
        select(ReferralPayoutRequest).where(
            ReferralPayoutRequest.user_id == user.id,
            ReferralPayoutRequest.state == "requested",
        )
    )
    if open_request is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Заявка уже отправлена. Дождись выплаты, потом можно подать новую.",
        )
    earned = await db.scalar(
        select(func.coalesce(func.sum(ReferralReward.reward_nano), 0))
        .select_from(ReferralReward)
        .join(
            ReferralAttribution,
            ReferralReward.attribution_id == ReferralAttribution.id,
        )
        .where(
            ReferralAttribution.inviter_user_id == user.id,
            ReferralReward.payout_tx_hash.is_(None),
        )
    )
    amount = int(earned or 0)
    if amount < settings.referral_min_payout_nano:
        floor = settings.referral_min_payout_nano / 1_000_000_000
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Вывести можно от {floor:.2f}".replace(".", ",").rstrip("0").rstrip(",")
            + " GRAM. Приглашай ещё.",
        )
    payout = ReferralPayoutRequest(
        user_id=user.id,
        address=address,
        amount_nano=amount,
    )
    db.add(payout)
    try:
        await db.commit()
    except IntegrityError as exc:
        # Две вкладки нажали одновременно: открытая заявка ровно одна.
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Заявка уже отправлена.") from exc
    await db.refresh(payout)

    bot = request.app.state.bot
    if bot is not None and settings.alert_chat_id:
        who = f"@{user.username}" if user.username else user.first_name
        try:
            await bot.send_message(
                settings.alert_chat_id,
                "💸 Заявка на вывод рефералки\n\n"
                f"{who} (id {user.telegram_id})\n"
                f"Сумма: {amount / 1_000_000_000:.3f} GRAM\n"
                f"Кошелёк: {body.address}",
            )
        except TelegramAPIError:
            # Заявка уже записана; недоставленное уведомление её не отменяет.
            logger.warning("referral_payout_alert_failed", user_id=user.id)
    return ReferralPayoutRequestView(
        id=payout.id,
        address=payout.address,
        amount_nano=payout.amount_nano,
        state=payout.state,
        created_at=payout.created_at,
    )


@router.get("/prelaunch", response_model=PrelaunchView)
async def prelaunch(user: CurrentUser, db: Db, settings: Config) -> PrelaunchView:
    """Everything the waiting screen shows: the clock, my link, the race.

    Deliberately reachable by people the whitelist keeps out of the product —
    they are exactly who it is for.
    """
    try:
        referral = await get_or_create_referral_code(db, user.id)
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "could not create referral code",
        ) from exc
    counts = (
        await db.execute(
            select(
                ReferralAttribution.inviter_user_id,
                func.count().label("invited"),
            ).group_by(ReferralAttribution.inviter_user_id)
        )
    ).all()
    by_inviter = {row[0]: int(row[1]) for row in counts}
    mine = by_inviter.get(user.id, 0)
    top_ids = sorted(by_inviter, key=lambda key: (-by_inviter[key], key))[:10]
    leaders = {
        leader.id: leader
        for leader in (
            await db.scalars(select(User).where(User.id.in_(top_ids)))
        ).all()
    }
    participants = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    return PrelaunchView(
        launch_at=settings.launch_at,
        referral_code=referral.code,
        referral_url=f"https://t.me/{settings.bot_username}?startapp=ref_{referral.code}",
        invited=mine,
        rank=(
            sum(1 for count in by_inviter.values() if count > mine) + 1 if mine > 0 else None
        ),
        leaderboard=[
            PrelaunchLeaderView(
                first_name=leaders[leader_id].first_name,
                username=leaders[leader_id].username,
                invited=by_inviter[leader_id],
                is_me=leader_id == user.id,
            )
            for leader_id in top_ids
            if leader_id in leaders
        ],
        participants=participants,
    )


@router.get("/duels/cards/{offer_id}.jpg", include_in_schema=False)
async def duel_invite_card_image(offer_id: str, db: Db, settings: Config) -> Response:
    """The challenge card, addressable by offer id.

    Public on purpose: Telegram's servers fetch this URL to build the shared
    message, and they arrive without a session. The id is a uuid nobody can
    guess, and the card resolves to a stake, odds and a first name — the same
    three facts the message itself carries.
    """
    offer = await db.get(MatchmakingOffer, offer_id)
    if offer is None or offer.state not in {OfferState.OPEN.value, OfferState.RESERVED.value}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    creator = await db.get(User, offer.user_id)
    if creator is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    content = await run_in_threadpool(
        render_duel_invite_card,
        first_name=creator.first_name,
        username=creator.username,
        opponent_stake_nano=offer.opponent_stake_nano,
        receiver_chance_bps=10_000 - offer.chance_bps,
        profit_nano=max(offer.payout_nano - offer.opponent_stake_nano, 0),
    )
    # An offer lives fifteen minutes, so the card can be held for its lifetime
    # and no longer: the terms on it stop being true when the duel is answered.
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=900"},
    )


@router.get("/prelaunch/cards/{slug}.jpg", include_in_schema=False)
async def prelaunch_card_image(slug: str, db: Db, settings: Config) -> Response:
    """The invite card, addressable by referral code.

    Public on purpose: Telegram's servers fetch this URL to build the shared
    message, and the code is the one piece of the referral that is already
    meant to travel. It resolves to nothing but a first name and a username.
    """
    code, _, variant = slug.rpartition("-")
    if not code or not variant.isdigit():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    if not 4 <= len(code) <= 24 or not all(
        character.isalnum() or character in "-_" for character in code
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    referral = await db.get(ReferralCode, code)
    if referral is None or settings.launch_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    owner = await db.get(User, referral.owner_user_id)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "card not found")
    content = await run_in_threadpool(
        render_invite_card,
        first_name=owner.first_name,
        username=owner.username,
        launch_at=settings.launch_at,
        variant_index=int(variant),
    )
    # The name on it can change and the date is env-driven — cache briefly.
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/prelaunch/share", response_model=PreparedResultShareView)
async def prepare_invite_share(
    user: CurrentUser,
    db: Db,
    settings: Config,
    request: Request,
) -> PreparedResultShareView:
    """A ready-to-send invitation: the card, the pitch, the ЗАНЯТЬ МЕСТО button."""
    if settings.launch_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "there is nothing to announce")
    bot = request.app.state.bot
    if bot is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram sharing is unavailable"
        )
    try:
        referral = await get_or_create_referral_code(db, user.id)
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Telegram sharing is temporarily unavailable",
        ) from exc
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user.telegram_id,
            result=build_invite_inline(
                settings=settings,
                referral_code=referral.code,
                first_name=user.first_name,
                username=user.username,
                launch_at=settings.launch_at,
                # A fresh draw each share: the same friends see the same
                # invitation several times over a launch week.
                variant_index=secrets.randbelow(len(INVITE_VARIANTS)),
            ),
            allow_user_chats=True,
            allow_bot_chats=False,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except TelegramAPIError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram sharing is temporarily unavailable"
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
        fallback_query=f"invite {referral.code}",
    )


@router.get("/rating", response_model=RatingView)
async def rating(user: CurrentUser, db: Db, settings: Config) -> RatingView:
    return await build_rating(db, user, settings=settings)


async def invitation_view(invitation: DuelInvitation, db: Db) -> InviteView:
    creator = await db.get(User, invitation.creator_user_id)
    offer = await db.get(MatchmakingOffer, invitation.creator_offer_id)
    if (
        creator is None
        or offer is None
        or offer.state
        not in {
            OfferState.OPEN.value,
            OfferState.RESERVED.value,
        }
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "challenge is no longer available")
    receiver_chance = 10_000 - offer.chance_bps
    receiver_stake = offer.opponent_stake_nano
    return InviteView(
        code=invitation.code,
        creator_name=creator.first_name,
        creator_username=creator.username,
        stake_nano=receiver_stake,
        total_pool_nano=offer.total_pool_nano,
        chance_bps=receiver_chance,
        payout_nano=offer.payout_nano,
        net_profit_nano=offer.payout_nano - receiver_stake,
        counter_offer_id=offer.onchain_offer_id,
        expires_at=invitation.expires_at,
    )


@router.get("/invites/{code}", response_model=InviteView)
async def preview_invite(code: str, user: CurrentUser, db: Db) -> InviteView:
    invitation = await db.get(DuelInvitation, code)
    if invitation is None or as_utc(invitation.expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
    if invitation.creator_user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "self invite is not allowed")
    return await invitation_view(invitation, db)


@router.post("/invites/{code}/accept", response_model=InviteView)
async def accept_invite(code: str, user: CurrentUser, db: Db, settings: Config) -> InviteView:
    await ensure_mode_enabled(db, "duel")
    invitation = await db.scalar(
        select(DuelInvitation).where(DuelInvitation.code == code).with_for_update()
    )
    if invitation is None or as_utc(invitation.expires_at) <= datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
    if invitation.creator_user_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "self invite is not allowed")
    if invitation.accepted_by_user_id not in {None, user.id}:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite already accepted")
    active_reservations = await db.scalar(
        select(func.count())
        .select_from(DuelInvitation)
        .where(
            DuelInvitation.accepted_by_user_id == user.id,
            DuelInvitation.state.in_([ChallengeState.ACCEPTED.value, ChallengeState.FUNDING.value]),
            DuelInvitation.expires_at > datetime.now(UTC),
        )
    )
    if not invitation.accepted_by_user_id and (active_reservations or 0) >= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "finish the current invitation first")
    offer = await db.get(MatchmakingOffer, invitation.creator_offer_id)
    wallet = await db.scalar(
        select(Wallet).where(
            Wallet.user_id == user.id,
            Wallet.network == settings.ton_network_id,
            Wallet.active.is_(True),
        )
    )
    if wallet is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Подтверди поддерживаемый кошелёк TON")
    if invitation.accepted_wallet_address not in {None, wallet.address}:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite is bound to another wallet")
    if offer is None or offer.owner_wallet == wallet.address:
        raise HTTPException(status.HTTP_409_CONFLICT, "same-wallet invite is not allowed")
    invitation.accepted_by_user_id = user.id
    invitation.accepted_wallet_address = wallet.address
    invitation.accepted_at = invitation.accepted_at or datetime.now(UTC)
    invitation.state = ChallengeState.ACCEPTED.value
    await db.commit()
    return await invitation_view(invitation, db)
