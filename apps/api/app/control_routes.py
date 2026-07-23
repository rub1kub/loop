import asyncio
import base64
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from tonsdk.boc import Cell  # type: ignore[import-untyped]
from tonsdk.utils import Address  # type: ignore[import-untyped]

from .config import Settings
from .control_state import application_control, contract_control_key
from .dependencies import Config, ControlWallet, Db
from .models import (
    AdminAuditEvent,
    ApplicationControl,
    ChainCheckpoint,
    ContractControl,
    User,
)
from .modules.bank.models import BankPosition, BankPositionStatus
from .modules.duel.models import Duel, DuelOffer, DuelState
from .schemas import WalletChallengeResponse, WalletVerifyRequest
from .security import (
    AuthenticationError,
    canonical_raw_address,
    issue_control_session,
    verify_ton_proof,
)
from .ton import ContractAdminState, ContractState, TonProviderError, normalize_address

router = APIRouter(prefix="/api/v1/control", tags=["Control"])

CONTROL_COOKIE = "loop_control"
ADMIN_GAS_NANO = 30_000_000
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
    return chain, admin, secrets.compare_digest(
        chain.code_hash, expected_hash.removeprefix("0x").upper()
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
                owner_matches_session=normalize_address(admin.owner)
                == normalize_address(wallet),
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
            .where(Duel.state.in_([DuelState.REVEALING.value]))
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


@router.patch("/application", response_model=ApplicationControlView)
async def update_application_control(
    body: ApplicationControlUpdate,
    wallet: ControlWallet,
    db: Db,
) -> ApplicationControlView:
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
        chain, admin, code_hash_matches = await _live_contract(
            request, settings, wallet, body.mode
        )
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
    amount = ADMIN_GAS_NANO + (
        body.amount_nano if body.action == "fund_reserve" and body.amount_nano else 0
    )
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
