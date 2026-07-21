from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=8192)


class UserView(BaseModel):
    id: str
    telegram_id: int
    username: str | None
    first_name: str
    photo_url: str | None
    onboarding_seen: bool


class AuthResponse(BaseModel):
    access_token: str
    expires_at: datetime
    user: UserView


class SettingsUpdate(BaseModel):
    onboarding_seen: bool


class WalletChallengeResponse(BaseModel):
    payload: str
    expires_at: datetime


class TonProofDomain(BaseModel):
    length_bytes: int = Field(alias="lengthBytes", ge=1, le=253)
    value: str = Field(min_length=1, max_length=253)


class TonProof(BaseModel):
    timestamp: int
    domain: TonProofDomain
    signature: str = Field(min_length=80, max_length=128)
    payload: str = Field(min_length=20, max_length=256)


class WalletVerifyRequest(BaseModel):
    address: str = Field(min_length=66, max_length=68)
    network: int
    public_key: str = Field(alias="publicKey", min_length=64, max_length=64)
    proof: TonProof

    @field_validator("public_key")
    @classmethod
    def valid_public_key(cls, value: str) -> str:
        int(value, 16)
        return value.lower()


class WalletView(BaseModel):
    address: str
    network: int
    verified_at: datetime


class BankCycleStart(BaseModel):
    goal_events: int = Field(default=6, ge=3, le=12)


class CycleEventView(BaseModel):
    id: str
    kind: str
    title: str
    proof_type: str
    proof_ref: str | None
    created_at: datetime


class BankCycleView(BaseModel):
    id: str
    sequence_number: int
    status: str
    goal_events: int
    event_count: int
    progress_bps: int
    started_at: datetime
    ends_at: datetime
    completed_at: datetime | None
    events: list[CycleEventView]


class ProfileView(BaseModel):
    user: UserView
    wallet: WalletView | None
    bank: BankCycleView | None


class OfferQuoteRequest(BaseModel):
    offer_id: int = Field(ge=1, le=9_007_199_254_740_991)
    chance_bps: int
    total_pool_nano: int
    commitment_hex: str = Field(min_length=64, max_length=64)

    @field_validator("chance_bps")
    @classmethod
    def valid_chance(cls, value: int) -> int:
        if value not in {2500, 5000, 7500}:
            raise ValueError("chance_bps must be 2500, 5000 or 7500")
        return value

    @field_validator("commitment_hex")
    @classmethod
    def valid_commitment(cls, value: str) -> str:
        int(value, 16)
        return value.lower()


class ContractCall(BaseModel):
    operation: str
    query_id: int
    offer_id: int
    counter_offer_id: int
    contract_address: str
    amount_nano: str
    valid_until: int
    chance_bps: int
    total_pool_nano: str
    commitment_hex: str
    expires_at: int
    commitment_domain: int


class OfferView(BaseModel):
    id: str
    onchain_offer_id: int
    chance_bps: int
    total_pool_nano: int
    stake_nano: int
    state: str
    expires_at: datetime


class OfferQuoteResponse(BaseModel):
    offer: OfferView
    transaction: ContractCall


class DuelView(BaseModel):
    id: str
    onchain_duel_id: int
    state: str
    offer_id: int
    own_revealed: bool
    chance_bps: int
    total_pool_nano: int
    reveal_deadline: datetime
    winner_wallet: str | None


class ActionIntent(BaseModel):
    operation: str
    query_id: int
    offer_id: int
    duel_id: int
    contract_address: str
    amount_nano: str
    valid_until: int


class ReferralView(BaseModel):
    code: str
    url: str
    invited: int
    qualified: int
    reward_points: int


class InviteView(BaseModel):
    code: str
    creator_telegram_id: int
    stake_nano: int
    chance_bps: int
    expires_at: datetime
