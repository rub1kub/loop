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
    onboarding_enabled: bool


class AuthResponse(BaseModel):
    access_token: str
    expires_at: datetime
    user: UserView


class SettingsUpdate(BaseModel):
    onboarding_seen: bool | None = None
    onboarding_enabled: bool | None = None


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


class ModeStatsView(BaseModel):
    active: int
    completed: int
    total: int


class PlushBrickView(BaseModel):
    verified: bool
    balance_nano: int
    holder: bool
    duel_fee_bps: int
    fee_discount_active: bool


class ProfileView(BaseModel):
    user: UserView
    wallet: WalletView | None
    bank: ModeStatsView
    duel: ModeStatsView
    plush_brick: PlushBrickView


class BankPositionQuoteRequest(BaseModel):
    position_id: int = Field(ge=1, le=9_007_199_254_740_991)
    principal_nano: int = Field(ge=1)
    multiplier_bps: int

    @field_validator("multiplier_bps")
    @classmethod
    def valid_multiplier(cls, value: int) -> int:
        if value not in {12_500, 15_000, 20_000}:
            raise ValueError("multiplier must be 12500, 15000 or 20000")
        return value


class BankPositionPreviewRequest(BaseModel):
    principal_nano: int = Field(ge=1)
    multiplier_bps: int

    @field_validator("multiplier_bps")
    @classmethod
    def valid_multiplier(cls, value: int) -> int:
        if value not in {12_500, 15_000, 20_000}:
            raise ValueError("multiplier must be 12500, 15000 or 20000")
        return value


class BankPositionPreviewResponse(BaseModel):
    principal_nano: int
    multiplier_bps: int
    target_payout_nano: int
    fee_nano: int
    gas_nano: int
    transaction_amount_nano: int
    contract_address: str
    network: int


class BankContractCall(BaseModel):
    operation: str
    query_id: int
    position_id: int
    contract_address: str
    amount_nano: str
    principal_nano: str
    multiplier_bps: int
    valid_until: int
    network: int
    fee_nano: str


class BankPositionView(BaseModel):
    id: str
    position_id: int
    owner_wallet: str
    principal_nano: int
    multiplier_bps: int
    target_payout_nano: int
    funded_amount_nano: int
    remaining_amount_nano: int
    progress_bps: int
    queue_index: int | None
    current_status: str
    funding_transaction: str | None
    payout_transaction: str | None
    proof_url: str | None
    created_at: datetime
    completed_at: datetime | None


class BankPositionQuoteResponse(BaseModel):
    position: BankPositionView
    transaction: BankContractCall


class OfferQuoteRequest(BaseModel):
    offer_id: int = Field(ge=1, le=9_007_199_254_740_991)
    chance_bps: int
    stake_nano: int = Field(ge=1)
    commitment_hex: str = Field(min_length=64, max_length=64)
    mode: str = Field(default="afk", pattern="^(afk|direct)$")
    challenge_code: str | None = Field(default=None, min_length=8, max_length=24)

    @field_validator("chance_bps")
    @classmethod
    def valid_chance(cls, value: int) -> int:
        if value not in {2_500, 5_000, 7_500}:
            raise ValueError("chance must be 2500, 5000 or 7500")
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
    network: int
    chance_bps: int
    stake_nano: str
    opponent_stake_nano: str
    total_pool_nano: str
    commitment_hex: str
    expires_at: int
    commitment_domain: int
    fee_bps: int
    invite_id_hex: str | None = None
    direct_counter_offer_id: int = 0
    direct_valid_until: int = 0
    direct_signature_hex: str | None = None


class OfferView(BaseModel):
    id: str
    onchain_offer_id: int
    chance_bps: int
    total_pool_nano: int
    stake_nano: int
    opponent_stake_nano: int
    fee_bps: int
    payout_nano: int
    net_profit_nano: int
    mode: str
    direct_opponent_wallet: str | None
    state: str
    expires_at: datetime
    funding_tx_hash: str | None
    funding_proof_url: str | None


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
    stake_nano: int
    opponent_stake_nano: int
    total_pool_nano: int
    payout_nano: int
    reveal_deadline: datetime
    winner_wallet: str | None
    settled_tx_hash: str | None
    settlement_proof_url: str | None


class ContractStateView(BaseModel):
    mode: str
    network: int
    address: str
    status: str
    balance_nano: int
    code_hash: str
    code_hash_matches: bool
    last_transaction_hash: str | None
    last_transaction_url: str | None
    wallet_balance_nano: int | None


class JettonBalanceView(BaseModel):
    network: int
    owner_address: str
    jetton_master: str
    jetton_wallet: str | None
    balance_nano: int
    verified: bool


class ActionIntent(BaseModel):
    operation: str
    query_id: int
    offer_id: int
    duel_id: int
    contract_address: str
    amount_nano: str
    valid_until: int
    network: int


class ReferralRewardView(BaseModel):
    cause: str
    reward_points: int
    payout_tx_hash: str | None
    created_at: datetime


class ReferralView(BaseModel):
    code: str
    url: str
    invited: int
    qualified: int
    reward_points: int
    history: list[ReferralRewardView]


class InviteView(BaseModel):
    code: str
    creator_name: str
    creator_username: str | None
    stake_nano: int
    total_pool_nano: int
    chance_bps: int
    payout_nano: int
    net_profit_nano: int
    counter_offer_id: int
    expires_at: datetime


class DuelCanaryReport(BaseModel):
    network: int
    contract_address: str = Field(min_length=48, max_length=68)
    duel_id: int = Field(ge=1, le=2**64 - 1)
    settlement_tx_hash: str = Field(min_length=43, max_length=96)
    first_wallet_balance_nano: int = Field(ge=0, le=2**63 - 1)
    second_wallet_balance_nano: int = Field(ge=0, le=2**63 - 1)
