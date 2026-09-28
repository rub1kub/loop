from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PixelRoundView(BaseModel):
    id: str
    starts_at: datetime
    ends_at: datetime
    revision: int
    archived: bool


class PixelChange(BaseModel):
    revision: int
    index: int
    color: int


class PixelState(BaseModel):
    enabled: bool
    round: PixelRoundView | None = None
    server_time: datetime
    ready_at: datetime | None = None
    size: int = 128
    cooldown_seconds: int = 30
    palette: list[str] = Field(default_factory=list)
    # One hex digit per cell, row-major. None means apply the changes instead.
    pixels: str | None = None
    changes: list[PixelChange] = Field(default_factory=list)


class PixelPlaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_id: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    operation_id: UUID
    x: int = Field(ge=0, lt=128, strict=True)
    y: int = Field(ge=0, lt=128, strict=True)
    color: int = Field(ge=0, lt=16, strict=True)


class PixelReceipt(PixelChange):
    round_id: str
    server_time: datetime
    ready_at: datetime
    replayed: bool = False


class PixelTeamView(BaseModel):
    team_id: str
    name: str
    held_pixels: int
    points: int
    is_mine: bool


class PixelScores(BaseModel):
    teams: list[PixelTeamView]
    my_team: PixelTeamView | None = None


class PixelShareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_id: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    x: int = Field(ge=0, lt=128, strict=True)
    y: int = Field(ge=0, lt=128, strict=True)


class PixelShareView(BaseModel):
    url: str
    image_url: str
    prepared_message_id: str | None = None


class PixelModerationRequest(PixelShareRequest):
    operation_id: UUID
    width: int = Field(ge=1, le=32, strict=True)
    height: int = Field(ge=1, le=32, strict=True)
    reason: str = Field(min_length=5, max_length=160)


class PixelModerationView(BaseModel):
    id: str
    reason: str
    x: int
    y: int
    width: int
    height: int
    created_at: datetime
