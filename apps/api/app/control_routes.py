import asyncio
import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, func, select, update
from sqlalchemy.sql import Select
from tonsdk.boc import Cell  # type: ignore[import-untyped]
from tonsdk.utils import Address  # type: ignore[import-untyped]

from .config import Settings
from .control_state import application_control, contract_control_key
from .dependencies import Config, ControlWallet, Db
from .models import (
    AdminAuditEvent,
    ApplicationControl,
    AuthExchange,
    ChainCheckpoint,
    ContractControl,
    ReferralAttribution,
    ReferralPayoutRequest,
    ReferralReward,
    User,
    Wallet,
)
from .modules.bank.models import BankPayout, BankPosition, BankPositionStatus
from .modules.duel.models import Duel, DuelOffer, DuelState, OfferState
from .modules.teams.models import Team, TeamMembership
from .schemas import WalletChallengeResponse, WalletVerifyRequest
from .security import (
    AuthenticationError,
    canonical_raw_address,
    issue_control_session,
    verify_ton_proof,
)
from .ton import (
    ContractAdminState,
    ContractState,
    TonProviderError,
    normalize_address,
    normalize_hash,
)

router = APIRouter(prefix="/api/v1/control", tags=["Control"])

CONTROL_COOKIE = "loop_control"
# Both contracts demand more gas for a withdrawal than for any other admin
# call, and a call that arrives short is rejected outright — the panel sent
# the same 0.03 for everything, so withdrawing simply bounced.
ADMIN_GAS_NANO = 30_000_000
WITHDRAW_GAS_NANO = 60_000_000
MIN_RETAINED_RESERVE_NANO = 200_000_000

BANK_OPCODES = {
    "pause": 0x4C424E02,
    "fund_reserve": 0x4C424E03,
    "withdraw_surplus": 0x4C424E04,
    "set_fee": 0x4C424E05,
    "set_treasury": 0x4C424E06,
    "set_owner": 0x4C424E07,
}
DUEL_OPCODES = {
    "pause": 0x4C4F4F07,
    "fund_reserve": 0x4C4F4F0A,
    "withdraw_surplus": 0x4C4F4F0B,
    "set_fee": 0x4C4F4F0C,
    "set_treasury": 0x4C4F4F0D,
    "set_owner": 0x4C4F4F0E,
}


class ControlSessionView(BaseModel):
    wallet: str
    expires_at: datetime | None = None


class ApplicationControlView(BaseModel):
    maintenance_enabled: bool
    bank_enabled: bool
    duel_enabled: bool
    updated_at: datetime


class ApplicationControlUpdate(BaseModel):
    maintenance_enabled: bool | None = None
    bank_enabled: bool | None = None
    duel_enabled: bool | None = None

    @model_validator(mode="after")
    def has_change(self) -> "ApplicationControlUpdate":
        if all(
            value is None
            for value in (self.maintenance_enabled, self.bank_enabled, self.duel_enabled)
        ):
            raise ValueError("at least one application control is required")
        return self


class ControlContractView(BaseModel):
    mode: Literal["bank", "duel"]
    address: str
    network: int
    status: str
    code_hash: str
    code_hash_matches: bool
    balance_nano: int
    locked_nano: int
    withdrawable_nano: int
    owner: str
    treasury: str
    fee_bps: int
    paused: bool
    owner_matches_session: bool
    extended_controls: bool
    last_transaction_hash: str | None
    error: str | None = None


class ControlMetricsView(BaseModel):
    users: int
    bank_positions: int
    active_bank_positions: int
    duel_offers: int
    active_duels: int
    worker_healthy: bool


class ControlAuditView(BaseModel):
    id: str
    action: str
    target: str
    status: str
    created_at: datetime


class ControlOverviewView(BaseModel):
    wallet: str
    application: ApplicationControlView
    metrics: ControlMetricsView
    contracts: list[ControlContractView]
    audit: list[ControlAuditView]
    generated_at: datetime


class ControlParticipantView(BaseModel):
    telegram_id: int
    username: str | None
    first_name: str
    wallet: str | None
    joined_at: datetime
    bank_positions: int
    bank_active: int
    bank_deposited_nano: int
    bank_received_nano: int
    duel_offers: int
    duel_settled: int
    referrals_qualified: int


class ControlParticipantsView(BaseModel):
    participants: list[ControlParticipantView]
    total: int
    generated_at: datetime


ControlAction = Literal[
    "pause",
    "fund_reserve",
    "withdraw_surplus",
    "set_fee",
    "set_treasury",
    "set_owner",
]


class ControlActionRequest(BaseModel):
    mode: Literal["bank", "duel"]
    action: ControlAction
    amount_nano: int | None = Field(default=None, ge=1, le=2**63 - 1)
    fee_bps: int | None = Field(default=None, ge=0, le=1_000)
    address: str | None = Field(default=None, min_length=48, max_length=68)
    paused: bool | None = None
    confirmation: str | None = Field(default=None, max_length=64)


class ControlTransactionView(BaseModel):
    audit_id: str
    operation: str
    address: str
    amount_nano: str
    payload: str
    valid_until: int
    query_id: int
    network: int
    sender_address: str | None = None


class ControlReferralPayoutView(BaseModel):
    id: str
    telegram_id: int
    username: str | None
    first_name: str
    address: str
    amount_nano: int
    state: str
    payout_tx_hash: str | None
    created_at: datetime
    prepared_at: datetime | None
    settled_at: datetime | None


class ControlReferralPayoutsView(BaseModel):
    treasury_address: str
    payouts: list[ControlReferralPayoutView]
    generated_at: datetime


class ControlReferralPayoutConfirm(BaseModel):
    signed_boc: str | None = Field(default=None, min_length=16, max_length=16_384)


class ControlReferralPayoutReject(BaseModel):
    reason: str = Field(min_length=3, max_length=160)


class ControlAnalyticsFunnelView(BaseModel):
    registered: int
    wallet_connected: int
    bank_started: int
    duel_started: int


class ControlAnalyticsDayView(BaseModel):
    date: str
    active_users: int = 0
    bank_positions: int = 0
    bank_volume_nano: int = 0
    duel_settled: int = 0
    referrals_qualified: int = 0
    team_joins: int = 0


class ControlAnalyticsView(BaseModel):
    days: int
    started_at: datetime
    active_users: int
    funnel: ControlAnalyticsFunnelView
    bank_positions: int
    bank_volume_nano: int
    bank_payout_nano: int
    duel_settled: int
    referral_qualified: int
    teams_created: int
    team_joins: int
    daily: list[ControlAnalyticsDayView]
    generated_at: datetime


def _application_view(control: ApplicationControl) -> ApplicationControlView:
    return ApplicationControlView(
        maintenance_enabled=control.maintenance_enabled,
        bank_enabled=control.bank_enabled,
        duel_enabled=control.duel_enabled,
        updated_at=control.updated_at,
    )


def _contract_settings(mode: str, settings: Settings) -> tuple[str, str]:
    if mode == "bank":
        return settings.bank_contract_address, settings.bank_contract_code_hash
    return settings.effective_duel_contract_address, settings.effective_duel_contract_code_hash


def _write_admin_payload(body: ControlActionRequest, query_id: int) -> str:
    opcodes = BANK_OPCODES if body.mode == "bank" else DUEL_OPCODES
    cell = Cell()
    cell.bits.write_uint(opcodes[body.action], 32)
    cell.bits.write_uint(query_id, 64)
    if body.action == "pause":
        cell.bits.write_bit(bool(body.paused))
    elif body.action in {"fund_reserve", "withdraw_surplus"}:
        cell.bits.write_coins(body.amount_nano)
    elif body.action == "set_fee":
        cell.bits.write_uint(body.fee_bps, 16)
    elif body.action in {"set_treasury", "set_owner"}:
        cell.bits.write_address(Address(body.address))
    return base64.b64encode(cell.to_boc(False)).decode()


def _referral_payout_payload(payout_id: str) -> str:
    """A stable human-readable label bound to exactly one payout request."""
    cell = Cell()
    cell.bits.write_uint(0, 32)
    cell.bits.write_bytes(f"LOOP referral {payout_id}".encode())
    return base64.b64encode(cell.to_boc(False)).decode()


def _referral_payout_view(payout: ReferralPayoutRequest, user: User) -> ControlReferralPayoutView:
    return ControlReferralPayoutView(
        id=payout.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        address=payout.address,
        amount_nano=payout.amount_nano,
        state=payout.state,
        payout_tx_hash=payout.payout_tx_hash,
        created_at=payout.created_at,
        prepared_at=payout.prepared_at,
        settled_at=payout.settled_at,
    )


async def _live_contract(
    request: Request,
    settings: Settings,
    wallet: str,
    mode: Literal["bank", "duel"],
) -> tuple[ContractState, ContractAdminState, bool]:
    address, expected_hash = _contract_settings(mode, settings)
    if not address:
        raise TonProviderError(f"{mode.upper()} contract is not configured")
    chain, admin = await asyncio.gather(
        request.app.state.ton_client.get_contract_state(address),
        request.app.state.ton_client.get_contract_admin_state(mode, address),
    )
    return (
        chain,
        admin,
        secrets.compare_digest(chain.code_hash, expected_hash.removeprefix("0x").upper()),
    )


async def _contract_view(
    request: Request,
    settings: Settings,
    wallet: str,
    mode: Literal["bank", "duel"],
) -> tuple[ControlContractView, ContractAdminState | None, ContractState | None]:
    address, _ = _contract_settings(mode, settings)
    try:
        chain, admin, hash_matches = await _live_contract(request, settings, wallet, mode)
        withdrawable = max(
            chain.balance_nano - admin.locked_nano - MIN_RETAINED_RESERVE_NANO,
            0,
        )
        return (
            ControlContractView(
                mode=mode,
                address=chain.address,
                network=settings.ton_network_id,
                status=chain.status,
                code_hash=chain.code_hash,
                code_hash_matches=hash_matches,
                balance_nano=chain.balance_nano,
                locked_nano=admin.locked_nano,
                withdrawable_nano=withdrawable,
                owner=admin.owner,
                treasury=admin.treasury,
                fee_bps=admin.fee_bps,
                paused=admin.paused,
                owner_matches_session=normalize_address(admin.owner) == normalize_address(wallet),
                extended_controls=admin.extended_controls,
                last_transaction_hash=chain.last_transaction_hash,
            ),
            admin,
            chain,
        )
    except TonProviderError as exc:
        return (
            ControlContractView(
                mode=mode,
                address=address,
                network=settings.ton_network_id,
                status="unavailable",
                code_hash="",
                code_hash_matches=False,
                balance_nano=0,
                locked_nano=0,
                withdrawable_nano=0,
                owner="",
                treasury="",
                fee_bps=0,
                paused=False,
                owner_matches_session=False,
                extended_controls=False,
                last_transaction_hash=None,
                error=str(exc),
            ),
            None,
            None,
        )


async def _sync_contract_control(
    db: Db,
    settings: Settings,
    view: ControlContractView,
) -> None:
    if view.error:
        return
    key = contract_control_key(view.mode, settings.ton_network_id, view.address)
    state = await db.get(ContractControl, key)
    if state is None:
        state = ContractControl(
            key=key,
            mode=view.mode,
            network=settings.ton_network_id,
            address=view.address,
            owner=view.owner,
            treasury=view.treasury,
            fee_bps=view.fee_bps,
        )
        db.add(state)
    state.owner = view.owner
    state.treasury = view.treasury
    state.fee_bps = view.fee_bps
    state.paused = view.paused
    state.locked_nano = view.locked_nano
    state.last_tx_hash = view.last_transaction_hash


async def _assert_contract_owner(request: Request, settings: Settings, wallet: str) -> None:
    """Confirms with the chain that this wallet still owns a LOOP contract."""
    for mode in ("bank", "duel"):
        try:
            _, admin, _ = await _live_contract(request, settings, wallet, mode)
        except TonProviderError:
            continue
        if normalize_address(admin.owner) == normalize_address(wallet):
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "connected wallet is not contract owner")


@router.post("/challenge", response_model=WalletChallengeResponse)
async def control_challenge(request: Request, settings: Config) -> WalletChallengeResponse:
    if not settings.control_admin_wallet:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "browser control is not configured",
        )
    payload = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(seconds=settings.ton_proof_ttl_seconds)
    await request.app.state.challenge_store.put(
        payload,
        {
            "role": "control",
            "network": settings.ton_network_id,
            "domain": settings.public_origin.removeprefix("https://").removeprefix("http://"),
        },
        settings.ton_proof_ttl_seconds,
    )
    return WalletChallengeResponse(payload=payload, expires_at=expires)


@router.post("/session", response_model=ControlSessionView)
async def create_control_session(
    body: WalletVerifyRequest,
    response: Response,
    request: Request,
    settings: Config,
) -> ControlSessionView:
    challenge = await request.app.state.challenge_store.consume(body.proof.payload)
    if (
        not challenge
        or challenge.get("role") != "control"
        or challenge.get("network") != settings.ton_network_id
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "control challenge is invalid or used")
    try:
        onchain_key = await request.app.state.ton_client.get_wallet_public_key(body.address)
        if not secrets.compare_digest(onchain_key.lower(), body.public_key.lower()):
            raise AuthenticationError("wallet public key mismatch")
        wallet = verify_ton_proof(
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
        configured = canonical_raw_address(normalize_address(settings.control_admin_wallet))
        if not secrets.compare_digest(wallet.lower(), configured.lower()):
            raise AuthenticationError("wallet is not authorized for LOOP control")
    except (AuthenticationError, TonProviderError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    token, expires = issue_control_session(wallet, settings)
    response.set_cookie(
        CONTROL_COOKIE,
        token,
        max_age=settings.control_session_ttl_seconds,
        expires=expires,
        path="/api/v1/control",
        secure=settings.public_origin.startswith("https://"),
        httponly=True,
        samesite="strict",
    )
    return ControlSessionView(wallet=wallet, expires_at=expires)


@router.get("/session", response_model=ControlSessionView)
async def get_control_session(wallet: ControlWallet) -> ControlSessionView:
    return ControlSessionView(wallet=wallet)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_control_session(response: Response, wallet: ControlWallet) -> Response:
    del wallet
    response.delete_cookie(CONTROL_COOKIE, path="/api/v1/control", samesite="strict")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/overview", response_model=ControlOverviewView)
async def control_overview(
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
) -> ControlOverviewView:
    control = await application_control(db)
    bank_result, duel_result = await asyncio.gather(
        _contract_view(request, settings, wallet, "bank"),
        _contract_view(request, settings, wallet, "duel"),
    )
    contract_results = [bank_result, duel_result]
    for view, _, _ in contract_results:
        await _sync_contract_control(db, settings, view)

    users = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    bank_positions = int(await db.scalar(select(func.count()).select_from(BankPosition)) or 0)
    active_bank = int(
        await db.scalar(
            select(func.count())
            .select_from(BankPosition)
            .where(
                BankPosition.current_status.in_(
                    [
                        BankPositionStatus.PENDING_CONFIRMATION.value,
                        BankPositionStatus.QUEUED.value,
                        BankPositionStatus.PARTIALLY_FUNDED.value,
                        BankPositionStatus.COMPLETED.value,
                    ]
                )
            )
        )
        or 0
    )
    duel_offers = int(await db.scalar(select(func.count()).select_from(DuelOffer)) or 0)
    active_duels = int(
        await db.scalar(
            select(func.count())
            .select_from(Duel)
            .where(Duel.state.in_([DuelState.BOOSTING.value, DuelState.REVEALING.value]))
        )
        or 0
    )
    heartbeat = await db.scalar(select(func.max(ChainCheckpoint.heartbeat_at)))
    heartbeat_utc = (
        heartbeat if heartbeat is None or heartbeat.tzinfo else heartbeat.replace(tzinfo=UTC)
    )
    worker_healthy = bool(
        heartbeat_utc and heartbeat_utc >= datetime.now(UTC) - timedelta(minutes=2)
    )
    events = (
        await db.scalars(
            select(AdminAuditEvent).order_by(AdminAuditEvent.created_at.desc()).limit(12)
        )
    ).all()
    await db.commit()
    return ControlOverviewView(
        wallet=wallet,
        application=_application_view(control),
        metrics=ControlMetricsView(
            users=users,
            bank_positions=bank_positions,
            active_bank_positions=active_bank,
            duel_offers=duel_offers,
            active_duels=active_duels,
            worker_healthy=worker_healthy,
        ),
        contracts=[item[0] for item in contract_results],
        audit=[
            ControlAuditView(
                id=event.id,
                action=event.action,
                target=event.target,
                status=event.status,
                created_at=event.created_at,
            )
            for event in events
        ],
        generated_at=datetime.now(UTC),
    )


@router.get("/participants", response_model=ControlParticipantsView)
async def control_participants(
    wallet: ControlWallet,
    db: Db,
    settings: Config,
    limit: int = 100,
) -> ControlParticipantsView:
    """Who is taking part, and what each of them has actually done.

    Counted per user rather than per wallet: a participant who relinked keeps
    one row. Only the current network is counted, so figures left behind on a
    network the application has moved away from do not inflate anyone's totals.
    """
    del wallet
    network = settings.ton_network_id
    limit = max(1, min(limit, 500))

    active_bank_states = [
        BankPositionStatus.PENDING_CONFIRMATION.value,
        BankPositionStatus.QUEUED.value,
        BankPositionStatus.PARTIALLY_FUNDED.value,
        BankPositionStatus.COMPLETED.value,
    ]
    bank = (
        select(
            BankPosition.user_id.label("user_id"),
            func.count().label("positions"),
            func.sum(case((BankPosition.current_status.in_(active_bank_states), 1), else_=0)).label(
                "active"
            ),
            func.sum(BankPosition.principal_nano).label("deposited"),
            func.sum(
                case(
                    (
                        BankPosition.current_status == BankPositionStatus.PAYOUT_SENT.value,
                        BankPosition.target_payout_nano,
                    ),
                    else_=0,
                )
            ).label("received"),
        )
        .where(BankPosition.network == network, BankPosition.user_id.is_not(None))
        .group_by(BankPosition.user_id)
        .subquery()
    )
    duel = (
        select(
            DuelOffer.user_id.label("user_id"),
            func.count().label("offers"),
            func.sum(case((DuelOffer.state == OfferState.SETTLED.value, 1), else_=0)).label(
                "settled"
            ),
        )
        .where(DuelOffer.network == network, DuelOffer.user_id.is_not(None))
        .group_by(DuelOffer.user_id)
        .subquery()
    )
    referrals = (
        select(
            ReferralAttribution.inviter_user_id.label("user_id"),
            func.count().label("qualified"),
        )
        .where(ReferralAttribution.status == "qualified")
        .group_by(ReferralAttribution.inviter_user_id)
        .subquery()
    )
    wallets = (
        select(Wallet.user_id.label("user_id"), Wallet.address.label("address"))
        .where(Wallet.active.is_(True), Wallet.network == network)
        .subquery()
    )

    total = int(await db.scalar(select(func.count()).select_from(User)) or 0)
    rows = (
        await db.execute(
            select(User, wallets.c.address, bank, duel, referrals.c.qualified)
            .outerjoin(wallets, wallets.c.user_id == User.id)
            .outerjoin(bank, bank.c.user_id == User.id)
            .outerjoin(duel, duel.c.user_id == User.id)
            .outerjoin(referrals, referrals.c.user_id == User.id)
            .order_by(User.created_at.desc())
            .limit(limit)
        )
    ).all()

    participants = [
        ControlParticipantView(
            telegram_id=row[0].telegram_id,
            username=row[0].username,
            first_name=row[0].first_name,
            wallet=row[1],
            joined_at=row[0].created_at,
            bank_positions=int(row[3] or 0),
            bank_active=int(row[4] or 0),
            bank_deposited_nano=int(row[5] or 0),
            bank_received_nano=int(row[6] or 0),
            duel_offers=int(row[8] or 0),
            duel_settled=int(row[9] or 0),
            referrals_qualified=int(row[10] or 0),
        )
        for row in rows
    ]
    return ControlParticipantsView(
        participants=participants,
        total=total,
        generated_at=datetime.now(UTC),
    )


async def _verified_referral_treasury(request: Request, settings: Settings, wallet: str) -> str:
    _, admin, code_hash_matches = await _live_contract(request, settings, wallet, "bank")
    if not code_hash_matches:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "configured BANK contract code does not match"
        )
    if normalize_address(admin.owner) != normalize_address(wallet):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "connected wallet is not contract owner")
    return normalize_address(admin.treasury)


async def _reserve_legacy_payout_rewards(
    db: Db, payout: ReferralPayoutRequest
) -> list[ReferralReward]:
    """Attach rewards to a request created before reservation was introduced."""
    reserved = (
        await db.scalars(
            select(ReferralReward)
            .where(ReferralReward.payout_request_id == payout.id)
            .order_by(ReferralReward.created_at, ReferralReward.id)
            .with_for_update()
        )
    ).all()
    if reserved:
        if sum(item.reward_nano for item in reserved) != payout.amount_nano:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "reserved referral rewards do not match request"
            )
        return list(reserved)

    candidates = (
        await db.scalars(
            select(ReferralReward)
            .join(
                ReferralAttribution,
                ReferralReward.attribution_id == ReferralAttribution.id,
            )
            .where(
                ReferralAttribution.inviter_user_id == payout.user_id,
                ReferralReward.payout_tx_hash.is_(None),
                ReferralReward.payout_request_id.is_(None),
            )
            .order_by(ReferralReward.created_at, ReferralReward.id)
            .with_for_update()
        )
    ).all()
    selected: list[ReferralReward] = []
    amount = 0
    for reward in candidates:
        if amount >= payout.amount_nano:
            break
        selected.append(reward)
        amount += reward.reward_nano
    if amount != payout.amount_nano:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "referral request no longer matches unpaid rewards"
        )
    for reward in selected:
        reward.payout_request_id = payout.id
    return selected


@router.get("/referral-payouts", response_model=ControlReferralPayoutsView)
async def control_referral_payouts(
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
    limit: int = 100,
) -> ControlReferralPayoutsView:
    try:
        treasury = await _verified_referral_treasury(request, settings, wallet)
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    rows = (
        await db.execute(
            select(ReferralPayoutRequest, User)
            .join(User, User.id == ReferralPayoutRequest.user_id)
            .order_by(
                case(
                    (ReferralPayoutRequest.state == "requested", 0),
                    (ReferralPayoutRequest.state == "prepared", 1),
                    else_=2,
                ),
                ReferralPayoutRequest.created_at.desc(),
            )
            .limit(max(1, min(limit, 500)))
        )
    ).all()
    return ControlReferralPayoutsView(
        treasury_address=treasury,
        payouts=[_referral_payout_view(payout, user) for payout, user in rows],
        generated_at=datetime.now(UTC),
    )


@router.post(
    "/referral-payouts/{payout_id}/transaction",
    response_model=ControlTransactionView,
)
async def prepare_referral_payout(
    payout_id: str,
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
) -> ControlTransactionView:
    try:
        treasury = await _verified_referral_treasury(request, settings, wallet)
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    payout = await db.scalar(
        select(ReferralPayoutRequest).where(ReferralPayoutRequest.id == payout_id).with_for_update()
    )
    if payout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral payout not found")
    if payout.state not in {"requested", "prepared"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "referral payout is already closed")
    await _reserve_legacy_payout_rewards(db, payout)
    payout.prepared_by_wallet = wallet
    payout.prepared_at = datetime.now(UTC)
    event = AdminAuditEvent(
        wallet=wallet,
        action="referral.payout",
        target=payout.id,
        payload_json=json.dumps(
            {
                "sender": treasury,
                "destination": payout.address,
                "amount_nano": payout.amount_nano,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    db.add(event)
    await db.commit()
    return ControlTransactionView(
        audit_id=event.id,
        operation="referral_payout",
        address=payout.address,
        amount_nano=str(payout.amount_nano),
        payload=_referral_payout_payload(payout.id),
        valid_until=int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        query_id=0,
        network=settings.ton_network_id,
        sender_address=treasury,
    )


@router.post(
    "/referral-payouts/{payout_id}/confirm",
    response_model=ControlReferralPayoutView,
)
async def confirm_referral_payout(
    payout_id: str,
    body: ControlReferralPayoutConfirm,
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
) -> ControlReferralPayoutView:
    try:
        treasury = await _verified_referral_treasury(request, settings, wallet)
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    payout = await db.get(ReferralPayoutRequest, payout_id)
    if payout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral payout not found")
    user = await db.get(User, payout.user_id)
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "referral payout user is missing")
    if payout.state == "paid":
        return _referral_payout_view(payout, user)
    if payout.state not in {"requested", "prepared"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "prepare referral payout first")
    if body.signed_boc:
        payout.state = "prepared"
        payout.signed_boc = body.signed_boc
        payout.prepared_at = payout.prepared_at or datetime.now(UTC)
        await db.commit()
    elif payout.state != "prepared" or not payout.signed_boc:
        raise HTTPException(status.HTTP_409_CONFLICT, "signed referral payout is missing")
    try:
        if payout.signed_boc:
            proof = await request.app.state.ton_client.verify_wallet_transfer(
                payout.signed_boc,
                treasury,
                payout.address,
                payout.amount_nano,
                _referral_payout_payload(payout.id),
            )
        else:
            proof = await request.app.state.ton_client.find_wallet_transfer(
                treasury,
                payout.address,
                payout.amount_nano,
                _referral_payout_payload(payout.id),
                payout.prepared_at or payout.created_at,
            )
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    payout = await db.scalar(
        select(ReferralPayoutRequest).where(ReferralPayoutRequest.id == payout_id).with_for_update()
    )
    if payout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral payout not found")
    if payout.state == "paid":
        return _referral_payout_view(payout, user)
    rewards = await _reserve_legacy_payout_rewards(db, payout)
    if any(reward.payout_tx_hash is not None for reward in rewards):
        raise HTTPException(status.HTTP_409_CONFLICT, "referral reward is already paid")
    transaction_hash = normalize_hash(proof.transaction_hash)
    for reward in rewards:
        reward.payout_tx_hash = transaction_hash
    payout.state = "paid"
    payout.payout_tx_hash = transaction_hash
    payout.settled_at = proof.confirmed_at
    db.add(
        AdminAuditEvent(
            wallet=wallet,
            action="chain.referral_payout",
            target=payout.id,
            payload_json=json.dumps(
                {
                    "transaction_hash": transaction_hash,
                    "logical_time": proof.logical_time,
                    "masterchain_seqno": proof.masterchain_seqno,
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            status="confirmed",
        )
    )
    await db.commit()
    return _referral_payout_view(payout, user)


@router.post(
    "/referral-payouts/{payout_id}/reject",
    response_model=ControlReferralPayoutView,
)
async def reject_referral_payout(
    payout_id: str,
    body: ControlReferralPayoutReject,
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
) -> ControlReferralPayoutView:
    await _assert_contract_owner(request, settings, wallet)
    payout = await db.scalar(
        select(ReferralPayoutRequest).where(ReferralPayoutRequest.id == payout_id).with_for_update()
    )
    if payout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral payout not found")
    if payout.state != "requested":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "only an unsigned referral payout can be rejected",
        )
    user = await db.get(User, payout.user_id)
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "referral payout user is missing")
    await db.execute(
        update(ReferralReward)
        .where(ReferralReward.payout_request_id == payout.id)
        .values(payout_request_id=None)
    )
    payout.state = "rejected"
    payout.settled_at = datetime.now(UTC)
    db.add(
        AdminAuditEvent(
            wallet=wallet,
            action="referral.reject",
            target=payout.id,
            payload_json=json.dumps({"reason": body.reason}, separators=(",", ":")),
            status="applied",
        )
    )
    await db.commit()
    return _referral_payout_view(payout, user)


@router.get("/analytics", response_model=ControlAnalyticsView)
async def control_analytics(
    wallet: ControlWallet,
    db: Db,
    days: int = 30,
) -> ControlAnalyticsView:
    del wallet
    days = max(7, min(days, 90))
    now = datetime.now(UTC)
    started_at = now - timedelta(days=days)
    cohort = select(User.id.label("user_id")).where(User.created_at >= started_at).subquery()

    async def count(statement: Select[tuple[Any]]) -> int:
        return int(await db.scalar(statement) or 0)

    registered = await count(select(func.count()).select_from(cohort))
    wallet_connected = await count(
        select(func.count(func.distinct(Wallet.user_id)))
        .select_from(Wallet)
        .join(cohort, cohort.c.user_id == Wallet.user_id)
    )
    bank_started = await count(
        select(func.count(func.distinct(BankPosition.user_id)))
        .select_from(BankPosition)
        .join(cohort, cohort.c.user_id == BankPosition.user_id)
        .where(BankPosition.confirmed_at.is_not(None))
    )
    duel_started = await count(
        select(func.count(func.distinct(DuelOffer.user_id)))
        .select_from(DuelOffer)
        .join(cohort, cohort.c.user_id == DuelOffer.user_id)
        .where(DuelOffer.funding_tx_hash.is_not(None))
    )
    active_users = await count(
        select(func.count(func.distinct(AuthExchange.user_id))).where(
            AuthExchange.created_at >= started_at
        )
    )
    bank_summary = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(BankPosition.principal_nano), 0)).where(
                BankPosition.confirmed_at >= started_at
            )
        )
    ).one()
    bank_payout_nano = await count(
        select(func.coalesce(func.sum(BankPayout.amount_nano), 0)).where(
            BankPayout.created_at >= started_at
        )
    )
    duel_settled = await count(
        select(func.count())
        .select_from(Duel)
        .where(Duel.settled_at >= started_at, Duel.state == DuelState.SETTLED.value)
    )
    referral_qualified = await count(
        select(func.count())
        .select_from(ReferralAttribution)
        .where(ReferralAttribution.qualified_at >= started_at)
    )
    teams_created = await count(
        select(func.count()).select_from(Team).where(Team.created_at >= started_at)
    )
    team_joins = await count(
        select(func.count())
        .select_from(TeamMembership)
        .where(TeamMembership.joined_at >= started_at)
    )

    daily = {
        (started_at.date() + timedelta(days=index)).isoformat(): ControlAnalyticsDayView(
            date=(started_at.date() + timedelta(days=index)).isoformat()
        )
        for index in range(days + 1)
        if started_at.date() + timedelta(days=index) <= now.date()
    }

    auth_day = func.date(AuthExchange.created_at)
    auth_rows = (
        await db.execute(
            select(auth_day, func.count(func.distinct(AuthExchange.user_id)))
            .where(AuthExchange.created_at >= started_at)
            .group_by(auth_day)
            .order_by(auth_day)
        )
    ).all()
    for day, value in auth_rows:
        if str(day) in daily:
            daily[str(day)].active_users = int(value or 0)

    bank_day = func.date(BankPosition.confirmed_at)
    bank_rows = (
        await db.execute(
            select(
                bank_day,
                func.count(),
                func.coalesce(func.sum(BankPosition.principal_nano), 0),
            )
            .where(BankPosition.confirmed_at >= started_at)
            .group_by(bank_day)
            .order_by(bank_day)
        )
    ).all()
    for day, positions, volume in bank_rows:
        if str(day) in daily:
            daily[str(day)].bank_positions = int(positions or 0)
            daily[str(day)].bank_volume_nano = int(volume or 0)

    duel_day = func.date(Duel.settled_at)
    duel_rows = (
        await db.execute(
            select(duel_day, func.count())
            .where(Duel.settled_at >= started_at, Duel.state == DuelState.SETTLED.value)
            .group_by(duel_day)
            .order_by(duel_day)
        )
    ).all()
    for day, value in duel_rows:
        if str(day) in daily:
            daily[str(day)].duel_settled = int(value or 0)

    referral_day = func.date(ReferralAttribution.qualified_at)
    referral_rows = (
        await db.execute(
            select(referral_day, func.count())
            .where(ReferralAttribution.qualified_at >= started_at)
            .group_by(referral_day)
            .order_by(referral_day)
        )
    ).all()
    for day, value in referral_rows:
        if str(day) in daily:
            daily[str(day)].referrals_qualified = int(value or 0)

    team_day = func.date(TeamMembership.joined_at)
    team_rows = (
        await db.execute(
            select(team_day, func.count())
            .where(TeamMembership.joined_at >= started_at)
            .group_by(team_day)
            .order_by(team_day)
        )
    ).all()
    for day, value in team_rows:
        if str(day) in daily:
            daily[str(day)].team_joins = int(value or 0)

    return ControlAnalyticsView(
        days=days,
        started_at=started_at,
        active_users=active_users,
        funnel=ControlAnalyticsFunnelView(
            registered=registered,
            wallet_connected=wallet_connected,
            bank_started=bank_started,
            duel_started=duel_started,
        ),
        bank_positions=int(bank_summary[0] or 0),
        bank_volume_nano=int(bank_summary[1] or 0),
        bank_payout_nano=bank_payout_nano,
        duel_settled=duel_settled,
        referral_qualified=referral_qualified,
        teams_created=teams_created,
        team_joins=team_joins,
        daily=list(daily.values()),
        generated_at=now,
    )


@router.patch("/application", response_model=ApplicationControlView)
async def update_application_control(
    body: ApplicationControlUpdate,
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
) -> ApplicationControlView:
    # The session gate proves only that the caller holds a session for the
    # configured admin wallet — not that the wallet still owns anything. Every
    # other control action asks the chain; without this one an ownership
    # transfer would leave the former admin able to switch the app off.
    #
    # It is not a defence against a forged session: a forged one claims the
    # owner's own address, and the chain agrees. What limits that is the
    # asymmetry below — a transaction still has to be signed by the owner's
    # wallet, so a stolen session can cause an outage but cannot move funds.
    await _assert_contract_owner(request, settings, wallet)
    control = await application_control(db)
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(control, key, value)
    control.updated_by_wallet = wallet
    event = AdminAuditEvent(
        wallet=wallet,
        action="application_control",
        target="application",
        payload_json=json.dumps(changes, separators=(",", ":"), sort_keys=True),
        status="applied",
    )
    db.add(event)
    await db.commit()
    await db.refresh(control)
    return _application_view(control)


@router.post("/transactions", response_model=ControlTransactionView)
async def prepare_control_transaction(
    body: ControlActionRequest,
    wallet: ControlWallet,
    db: Db,
    request: Request,
    settings: Config,
) -> ControlTransactionView:
    address, _ = _contract_settings(body.mode, settings)
    try:
        chain, admin, code_hash_matches = await _live_contract(request, settings, wallet, body.mode)
    except TonProviderError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    if not code_hash_matches:
        raise HTTPException(status.HTTP_409_CONFLICT, "configured contract code does not match")
    if normalize_address(admin.owner) != normalize_address(wallet):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "connected wallet is not contract owner")
    if body.action != "pause" and not admin.extended_controls:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "extended controls require the current LOOP contract version",
        )
    if body.action == "pause" and body.paused is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "paused value is required")
    if body.action in {"fund_reserve", "withdraw_surplus"} and body.amount_nano is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "amount is required")
    if body.action == "set_fee" and body.fee_bps is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "fee is required")
    if body.action in {"set_treasury", "set_owner"}:
        if not body.address:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "address is required")
        try:
            body.address = normalize_address(body.address)
        except TonProviderError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        if body.address == normalize_address(address):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "contract cannot own or receive its own treasury",
            )
    if body.action in {"withdraw_surplus", "set_fee", "set_treasury", "set_owner"}:
        if not admin.paused:
            raise HTTPException(status.HTTP_409_CONFLICT, "pause the contract first")
    if body.action == "withdraw_surplus":
        withdrawable = max(
            chain.balance_nano - admin.locked_nano - MIN_RETAINED_RESERVE_NANO,
            0,
        )
        if body.amount_nano is None or body.amount_nano > withdrawable:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "amount exceeds the verified free reserve",
            )
    if body.action == "set_fee" and body.mode == "duel" and admin.locked_nano:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "finish or refund active DUEL stakes before changing the fee",
        )
    if body.action == "set_owner" and body.confirmation != "TRANSFER OWNER":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "owner transfer confirmation is required",
        )

    query_id = secrets.randbelow(2**63 - 1) + 1
    payload = _write_admin_payload(body, query_id)
    gas = WITHDRAW_GAS_NANO if body.action == "withdraw_surplus" else ADMIN_GAS_NANO
    amount = gas + (body.amount_nano if body.action == "fund_reserve" and body.amount_nano else 0)
    event = AdminAuditEvent(
        wallet=wallet,
        action=f"{body.mode}.{body.action}",
        target=normalize_address(address),
        payload_json=json.dumps(
            {
                "amount_nano": body.amount_nano,
                "fee_bps": body.fee_bps,
                "address": body.address,
                "paused": body.paused,
                "query_id": query_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    db.add(event)
    await db.commit()
    return ControlTransactionView(
        audit_id=event.id,
        operation=body.action,
        address=address,
        amount_nano=str(amount),
        payload=payload,
        valid_until=int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        query_id=query_id,
        network=settings.ton_network_id,
    )
