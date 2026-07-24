import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from .control_state import effective_contract_fee, ensure_mode_enabled
from .dependencies import Config, CurrentUser, Db
from .models import (
    AuthExchange,
    ReferralAttribution,
    ReferralCode,
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
from .schemas import (
    AuthResponse,
    ContractStateView,
    InviteView,
    JettonBalanceView,
    ModeStatsView,
    PlushBrickView,
    ProfileView,
    RatingView,
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
from .ton import TonProviderError, explorer_transaction_url

router = APIRouter(prefix="/api/v1")


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        photo_url=user.photo_url,
        onboarding_seen=user.onboarding_seen,
        onboarding_enabled=user.onboarding_enabled,
    )


async def record_referral_attribution(
    db: Db,
    user: User,
    start_param: str | None,
) -> None:
    if not start_param or not start_param.startswith("ref_"):
        return
    code = start_param[4:]
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
        try:
            plush = await request.app.state.plush_ton_client.get_jetton_wallet(
                wallet.address, settings.plush_brick_master
            )
            plush_balance = plush.balance_nano
            plush_verified = True
        except TonProviderError:
            pass
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
        plush_brick=PlushBrickView(
            verified=plush_verified,
            balance_nano=plush_balance,
            holder=holder,
            # The current DuelEscrow exposes one global on-chain fee. Reporting a
            # holder discount here would make the quote disagree with settlement.
            duel_fee_bps=duel_fee_bps,
            fee_discount_active=False,
        ),
    )


@router.patch("/me/settings", response_model=UserView)
async def update_settings(body: SettingsUpdate, user: CurrentUser, db: Db) -> UserView:
    if body.onboarding_seen is not None:
        user.onboarding_seen = body.onboarding_seen
    if body.onboarding_enabled is not None:
        user.onboarding_enabled = body.onboarding_enabled
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
    if body.network != settings.ton_network_id or body.network != -3:
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
        raise HTTPException(status.HTTP_409_CONFLICT, "wallet is bound to another account")
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
        duel_active = await db.scalar(
            select(MatchmakingOffer.id).where(
                MatchmakingOffer.wallet_id == current.id,
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
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "finish active BANK and DUEL operations before changing wallet",
            )
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


async def get_or_create_referral_code(db: Db, user_id: str) -> ReferralCode:
    existing = await db.scalar(select(ReferralCode).where(ReferralCode.owner_user_id == user_id))
    if existing is not None:
        return existing
    for _ in range(3):
        referral = ReferralCode(code=secrets.token_urlsafe(9), owner_user_id=user_id)
        db.add(referral)
        try:
            await db.commit()
            return referral
        except IntegrityError:
            await db.rollback()
            existing_after_conflict: ReferralCode | None = await db.scalar(
                select(ReferralCode).where(ReferralCode.owner_user_id == user_id)
            )
            if existing_after_conflict is not None:
                return existing_after_conflict
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "could not create referral code")


@router.get("/referrals", response_model=ReferralView)
async def referrals(user: CurrentUser, db: Db, settings: Config) -> ReferralView:
    referral = await get_or_create_referral_code(db, user.id)
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
    rewards = (
        await db.scalars(
            select(ReferralReward)
            .join(
                ReferralAttribution,
                ReferralReward.attribution_id == ReferralAttribution.id,
            )
            .where(ReferralAttribution.inviter_user_id == user.id)
            .order_by(ReferralReward.created_at.desc())
            .limit(50)
        )
    ).all()
    return ReferralView(
        code=referral.code,
        url=f"https://t.me/{settings.bot_username}?startapp=ref_{referral.code}",
        invited=invited or 0,
        qualified=qualified or 0,
        reward_points=sum(reward.reward_points for reward in rewards),
        history=[
            ReferralRewardView(
                cause=reward.cause,
                reward_points=reward.reward_points,
                payout_tx_hash=reward.payout_tx_hash,
                created_at=reward.created_at,
            )
            for reward in rewards
        ],
    )


@router.get("/rating", response_model=RatingView)
async def rating(user: CurrentUser, db: Db) -> RatingView:
    return await build_rating(db, user)


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
