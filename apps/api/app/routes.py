import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .dependencies import Config, CurrentUser, Db
from .models import (
    AuthExchange,
    BankPosition,
    InlineInvite,
    MatchmakingOffer,
    OfferState,
    ReferralCode,
    User,
    Wallet,
)
from .schemas import (
    AuthResponse,
    BankPositionRequest,
    BankPositionView,
    ContractCall,
    InviteView,
    OfferQuoteRequest,
    OfferQuoteResponse,
    OfferView,
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
from .ton import TonProviderError

router = APIRouter(prefix="/api/v1")


def user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        onboarding_seen=user.onboarding_seen,
    )


@router.post("/auth/telegram", response_model=AuthResponse)
async def authenticate(body: TelegramAuthRequest, db: Db, settings: Config) -> AuthResponse:
    try:
        identity = validate_telegram_init_data(
            body.init_data, settings.bot_token.get_secret_value(), settings
        )
    except AuthenticationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

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
        if identity.start_param and identity.start_param.startswith("ref_"):
            referral = await db.get(ReferralCode, identity.start_param[4:])
            if referral:
                owner = await db.get(User, referral.owner_user_id)
                if owner and owner.telegram_id != identity.telegram_id:
                    user.referred_by_id = owner.id
        db.add(user)
        await db.flush()
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
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = await db.get(AuthExchange, identity.digest)
        if existing is None or existing.user_id != user.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "initData replay rejected") from exc
    return AuthResponse(access_token=token, expires_at=expires, user=user_view(user))


@router.get("/me")
async def get_me(
    user: CurrentUser, db: Db, request: Request, settings: Config
) -> dict[str, object]:
    wallet = await db.scalar(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.active.is_(True))
    )
    position = await db.get(BankPosition, user.id)
    balance = None
    holder = False
    if wallet:
        try:
            balance = await request.app.state.ton_client.get_native_balance(wallet.address)
            if settings.ton_network_id == -239:
                holder_balance = await request.app.state.ton_client.get_holder_balance(
                    wallet.address, settings.plush_brick_master
                )
                holder = holder_balance >= settings.holder_min_balance_nano
        except TonProviderError:
            balance = None
    return {
        "user": user_view(user).model_dump(mode="json"),
        "wallet": (
            WalletView(
                address=wallet.address, network=wallet.network, verified_at=wallet.verified_at
            ).model_dump(mode="json")
            if wallet
            else None
        ),
        "bank": (
            BankPositionView(
                target_nano=position.target_nano, updated_at=position.updated_at
            ).model_dump(mode="json")
            if position
            else None
        ),
        "balance_nano": balance,
        "plush_brick_holder": holder,
    }


@router.patch("/me/settings", response_model=UserView)
async def update_settings(body: SettingsUpdate, user: CurrentUser, db: Db) -> UserView:
    user.onboarding_seen = body.onboarding_seen
    await db.commit()
    return user_view(user)


@router.put("/bank", response_model=BankPositionView)
async def set_bank_position(
    body: BankPositionRequest, user: CurrentUser, db: Db
) -> BankPositionView:
    position = await db.get(BankPosition, user.id)
    if position is None:
        position = BankPosition(user_id=user.id, target_nano=body.target_nano)
        db.add(position)
    else:
        position.target_nano = body.target_nano
        position.updated_at = datetime.now(UTC)
    await db.commit()
    return BankPositionView(target_nano=position.target_nano, updated_at=position.updated_at)


@router.post("/wallet/challenge", response_model=WalletChallengeResponse)
async def wallet_challenge(
    user: CurrentUser, request: Request, settings: Config
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
        raise HTTPException(status.HTTP_409_CONFLICT, "wallet is bound to another account")
    current = await db.scalar(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.active.is_(True))
    )
    if current and current.address != address:
        current.active = False
    wallet = existing or Wallet(
        user_id=user.id,
        network=body.network,
        address=address,
        public_key=onchain_key.lower(),
    )
    wallet.active = True
    wallet.verified_at = datetime.now(UTC)
    db.add(wallet)
    await db.commit()
    return WalletView(
        address=wallet.address, network=wallet.network, verified_at=wallet.verified_at
    )


@router.post("/duels/quote", response_model=OfferQuoteResponse)
async def create_offer_quote(
    body: OfferQuoteRequest, user: CurrentUser, db: Db, settings: Config
) -> OfferQuoteResponse:
    if not settings.ton_contract_address:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "duel contract is not configured")
    if not settings.min_pool_nano <= body.total_pool_nano <= settings.max_pool_nano:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "pool is outside limits")
    if body.total_pool_nano % 4:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "pool must be divisible by four")
    wallet = await db.scalar(
        select(Wallet).where(
            Wallet.user_id == user.id,
            Wallet.network == settings.ton_network_id,
            Wallet.active.is_(True),
        )
    )
    if wallet is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "verified wallet required")
    active = await db.scalar(
        select(MatchmakingOffer).where(
            MatchmakingOffer.wallet_id == wallet.id,
            MatchmakingOffer.state.in_(
                [OfferState.PENDING_FUNDING.value, OfferState.OPEN.value, OfferState.MATCHED.value]
            ),
        )
    )
    if active:
        raise HTTPException(status.HTTP_409_CONFLICT, "wallet already has an active offer")
    counter = await db.scalar(
        select(MatchmakingOffer)
        .where(
            MatchmakingOffer.network == settings.ton_network_id,
            MatchmakingOffer.contract_address == settings.ton_contract_address,
            MatchmakingOffer.total_pool_nano == body.total_pool_nano,
            MatchmakingOffer.chance_bps == 10_000 - body.chance_bps,
            MatchmakingOffer.state == OfferState.OPEN.value,
            MatchmakingOffer.wallet_id != wallet.id,
            MatchmakingOffer.user_id != user.id,
            MatchmakingOffer.expires_at > datetime.now(UTC),
        )
        .order_by(MatchmakingOffer.created_at)
        .with_for_update(skip_locked=True)
    )
    offer_id = secrets.randbelow(2**63 - 1) + 1
    expires = datetime.now(UTC) + timedelta(seconds=settings.offer_ttl_seconds)
    stake = body.total_pool_nano * body.chance_bps // 10_000
    offer = MatchmakingOffer(
        onchain_offer_id=offer_id,
        user_id=user.id,
        wallet_id=wallet.id,
        network=settings.ton_network_id,
        contract_address=settings.ton_contract_address,
        chance_bps=body.chance_bps,
        total_pool_nano=body.total_pool_nano,
        stake_nano=stake,
        commitment_hex=body.commitment_hex,
        counter_offer_id=counter.onchain_offer_id if counter else 0,
        expires_at=expires,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    view = OfferView(
        id=offer.id,
        onchain_offer_id=offer.onchain_offer_id,
        chance_bps=offer.chance_bps,
        total_pool_nano=offer.total_pool_nano,
        stake_nano=offer.stake_nano,
        state=offer.state,
        expires_at=offer.expires_at,
    )
    return OfferQuoteResponse(
        offer=view,
        transaction=ContractCall(
            operation="open_offer",
            query_id=offer_id,
            offer_id=offer_id,
            counter_offer_id=offer.counter_offer_id,
            contract_address=offer.contract_address,
            amount_nano=str(stake + settings.offer_gas_nano),
            valid_until=int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
            chance_bps=offer.chance_bps,
            total_pool_nano=str(offer.total_pool_nano),
            commitment_hex=offer.commitment_hex,
            expires_at=int(offer.expires_at.timestamp()),
        ),
    )


@router.get("/duels/offers", response_model=list[OfferView])
async def list_offers(user: CurrentUser, db: Db) -> list[OfferView]:
    offers = (
        await db.scalars(
            select(MatchmakingOffer)
            .where(MatchmakingOffer.user_id == user.id)
            .order_by(MatchmakingOffer.created_at.desc())
            .limit(50)
        )
    ).all()
    return [
        OfferView(
            id=offer.id,
            onchain_offer_id=offer.onchain_offer_id,
            chance_bps=offer.chance_bps,
            total_pool_nano=offer.total_pool_nano,
            stake_nano=offer.stake_nano,
            state=offer.state,
            expires_at=offer.expires_at,
        )
        for offer in offers
    ]


@router.get("/referrals", response_model=ReferralView)
async def referrals(user: CurrentUser, db: Db, settings: Config) -> ReferralView:
    referral = await db.scalar(select(ReferralCode).where(ReferralCode.owner_user_id == user.id))
    if referral is None:
        referral = ReferralCode(code=secrets.token_urlsafe(9), owner_user_id=user.id)
        db.add(referral)
        await db.commit()
    invited = await db.scalar(
        select(func.count()).select_from(User).where(User.referred_by_id == user.id)
    )
    url = f"https://t.me/{settings.bot_username}?startapp=ref_{referral.code}"
    return ReferralView(code=referral.code, url=url, invited=invited or 0, qualified=0)


@router.get("/invites/{code}", response_model=InviteView)
async def resolve_invite(code: str, user: CurrentUser, db: Db) -> InviteView:
    invite = await db.get(InlineInvite, code)
    if invite is None or invite.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
    if invite.creator_telegram_id == user.telegram_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "self invite is not allowed")
    if invite.accepted_by_user_id and invite.accepted_by_user_id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite already accepted")
    invite.accepted_by_user_id = user.id
    await db.commit()
    return InviteView(
        code=invite.code,
        creator_telegram_id=invite.creator_telegram_id,
        stake_nano=invite.stake_nano,
        chance_bps=invite.chance_bps,
        expires_at=invite.expires_at,
    )
