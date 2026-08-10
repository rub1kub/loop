from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TeamSeasonView(BaseModel):
    id: str
    key: str
    name: str
    starts_at: datetime
    ends_at: datetime
    competition: str


class TeamEntryView(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    tag: str
    mark: int
    avatar_url: str | None
    join_policy: str
    member_count: int
    active_members: int
    flow_nano: int
    bank_entries: int
    bank_payouts: int
    duel_settlements: int
    rank: int
    is_mine: bool


class TeamMemberView(BaseModel):
    user_id: str
    first_name: str
    username: str | None
    photo_url: str | None
    role: str
    joined_at: datetime
    flow_nano: int
    bank_entries: int
    bank_payouts: int
    duel_settlements: int
    is_me: bool


class TeamActivityView(BaseModel):
    id: str
    kind: str
    user_id: str
    first_name: str
    username: str | None
    amount_nano: int
    tx_hash: str
    event_at: datetime


class TeamRequestView(BaseModel):
    id: str
    user_id: str
    first_name: str
    username: str | None
    photo_url: str | None
    created_at: datetime


class TeamDetailView(TeamEntryView):
    my_role: str | None
    my_join_state: Literal["none", "pending", "joined"]
    my_flow_nano: int
    top_members: list[TeamMemberView]
    recent_activity: list[TeamActivityView]
    pending_requests: list[TeamRequestView]


class TeamOverviewView(BaseModel):
    season: TeamSeasonView
    my_team: TeamDetailView | None
    leaderboard: list[TeamEntryView]


class TeamSearchView(BaseModel):
    items: list[TeamEntryView]
    total: int
    offset: int
    limit: int


class TeamMembersPageView(BaseModel):
    items: list[TeamMemberView]
    total: int
    offset: int
    limit: int


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=32)
    # Kept optional for older clients. New clients do not expose an internal
    # identifier as a second piece of team branding.
    tag: str | None = Field(default=None, min_length=2, max_length=8)
    join_policy: Literal["open", "request", "invite"] = "open"

    @field_validator("name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("tag")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return " ".join(value.strip().split()) if value is not None else None


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=32)
    description: str | None = Field(default=None, max_length=160)
    mark: int | None = Field(default=None, ge=0, le=11)
    join_policy: Literal["open", "request", "invite"] | None = None

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return " ".join(value.strip().split()) if value is not None else None


class TeamJoinRequestBody(BaseModel):
    invite_token: str | None = Field(default=None, min_length=12, max_length=48)


class TeamJoinResultView(BaseModel):
    state: Literal["joined", "requested"]
    team: TeamDetailView


class TeamRoleUpdateRequest(BaseModel):
    role: Literal["admin", "member"]


class TeamTransferRequest(BaseModel):
    user_id: str = Field(min_length=36, max_length=36)


class TeamInviteView(BaseModel):
    token: str
    expires_at: datetime
    team: TeamEntryView
    inviter_name: str
    referral_url: str


class TeamInvitePreviewView(BaseModel):
    token: str
    expires_at: datetime
    team: TeamEntryView
    inviter_name: str


class TeamRequestDecision(BaseModel):
    approve: bool
