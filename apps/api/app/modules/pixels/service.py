from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import utc_now
from ...models import User
from ..teams.models import Team, TeamMembership
from ..teams.service import as_utc, team_week_window
from .models import PixelCell, PixelMove, PixelPlayer, PixelRound, PixelTeamScore
from .schemas import (
    PixelChange,
    PixelPlaceRequest,
    PixelReceipt,
    PixelRoundView,
    PixelScores,
    PixelState,
    PixelTeamView,
)

SIZE = 128
COOLDOWN = timedelta(seconds=30)
PALETTE = (
    "#101012",
    "#ffffff",
    "#919198",
    "#45454d",
    "#ef4444",
    "#ff8c42",
    "#f5cb5c",
    "#a3d977",
    "#35b779",
    "#50c8c6",
    "#63b5ed",
    "#4775d1",
    "#8062c5",
    "#c77acb",
    "#ee9ca7",
    "#a07855",
)
MAX_CHANGES = 512


async def ensure_round(db: AsyncSession, at: datetime) -> PixelRound:
    start, end = team_week_window(at)
    key = (start + timedelta(hours=3)).date().isoformat()
    board = await db.get(PixelRound, key)
    if board is not None:
        return board
    try:
        async with db.begin_nested():
            board = PixelRound(
                id=key, starts_at=start, ends_at=end, revision=0, pixels=bytes(SIZE * SIZE)
            )
            db.add(board)
            await db.flush()
    except IntegrityError:
        board = await db.get(PixelRound, key, populate_existing=True)
        if board is None:
            raise
    return board


def round_view(board: PixelRound, at: datetime) -> PixelRoundView:
    return PixelRoundView(
        id=board.id,
        starts_at=as_utc(board.starts_at),
        ends_at=as_utc(board.ends_at),
        revision=board.revision,
        archived=at >= as_utc(board.ends_at),
    )


async def state_view(
    db: AsyncSession,
    board: PixelRound,
    user_id: str,
    at: datetime,
    *,
    after: int | None = None,
) -> PixelState:
    player = await db.get(PixelPlayer, user_id, populate_existing=True)
    full = after is None or after > board.revision or board.revision - after > MAX_CHANGES
    changes: list[PixelChange] = []
    if not full:
        rows = await db.scalars(
            select(PixelMove)
            .where(
                PixelMove.round_id == board.id,
                PixelMove.revision > after,
                PixelMove.revision <= board.revision,
            )
            .order_by(PixelMove.revision)
        )
        changes = [
            PixelChange(revision=move.revision, index=move.cell_index, color=move.color)
            for move in rows
        ]
    return PixelState(
        enabled=True,
        round=round_view(board, at),
        server_time=at,
        ready_at=as_utc(player.ready_at) if player else None,
        palette=list(PALETTE),
        pixels="".join(format(color, "x") for color in board.pixels) if full else None,
        changes=changes,
    )


async def account_score(
    db: AsyncSession,
    board: PixelRound,
    team_id: str | None,
    change: int,
    at: datetime,
) -> None:
    if team_id is None:
        return
    score = await db.get(PixelTeamScore, (board.id, team_id))
    if score is None:
        score = PixelTeamScore(
            round_id=board.id, team_id=team_id, held_pixels=0, pixel_ms=0, accrued_at=at
        )
        db.add(score)
    elapsed = max(0, int((at - as_utc(score.accrued_at)).total_seconds() * 1000))
    score.pixel_ms += score.held_pixels * elapsed
    score.held_pixels += change
    score.accrued_at = at


async def recolor(
    db: AsyncSession,
    board: PixelRound,
    index: int,
    color: int,
    at: datetime,
    *,
    user_id: str | None,
    team_id: str | None,
    operation_id: str,
) -> PixelMove:
    """Caller owns the round row lock; ownership and area-time change together."""
    cell = await db.get(PixelCell, (board.id, index))
    previous_team = cell.team_id if cell else None
    if previous_team != team_id:
        await account_score(db, board, previous_team, -1, at)
        await account_score(db, board, team_id, 1, at)
    if cell is None:
        cell = PixelCell(round_id=board.id, cell_index=index)
        db.add(cell)
    cell.user_id = user_id
    cell.team_id = team_id
    pixels = bytearray(board.pixels)
    pixels[index] = color
    board.pixels = bytes(pixels)
    board.revision += 1
    move = PixelMove(
        round_id=board.id,
        revision=board.revision,
        operation_id=operation_id,
        user_id=user_id,
        team_id=team_id,
        cell_index=index,
        color=color,
        created_at=at,
    )
    db.add(move)
    return move


async def place(db: AsyncSession, user: User, body: PixelPlaceRequest) -> PixelReceipt:
    # Match the team-membership lock order. A token/session/device is never the player key.
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    previous = await db.scalar(
        select(PixelMove).where(
            PixelMove.user_id == user.id,
            PixelMove.operation_id == str(body.operation_id),
        )
    )
    if previous:
        if (previous.round_id, previous.cell_index, previous.color) != (
            body.round_id,
            body.y * SIZE + body.x,
            body.color,
        ):
            raise HTTPException(409, "Этот ход уже использован для другого пикселя")
        result = receipt(previous, utc_now(), replayed=True)
        player = await db.get(PixelPlayer, user.id, populate_existing=True)
        if player:
            result.ready_at = max(result.ready_at, as_utc(player.ready_at))
        return result
    board = await db.scalar(
        select(PixelRound)
        .where(PixelRound.id == body.round_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # Take time AFTER waiting for locks, including at a weekly boundary.
    at = utc_now()
    if board is None or not as_utc(board.starts_at) <= at < as_utc(board.ends_at):
        raise HTTPException(409, "Этот раунд завершён. Открой новое полотно")
    player = await db.get(PixelPlayer, user.id, populate_existing=True)
    if player and as_utc(player.ready_at) > at:
        seconds = max(1, int((as_utc(player.ready_at) - at).total_seconds()) + 1)
        raise HTTPException(
            429, "Следующий пиксель ещё не готов", headers={"Retry-After": str(seconds)}
        )
    index = body.y * SIZE + body.x
    if board.pixels[index] == body.color:
        raise HTTPException(409, "Здесь уже этот цвет. Выбери другой пиксель или цвет")
    membership = await db.scalar(
        select(TeamMembership)
        .join(Team)
        .where(
            TeamMembership.user_id == user.id,
            TeamMembership.state == "active",
            Team.state == "active",
        )
    )
    move = await recolor(
        db,
        board,
        index,
        body.color,
        at,
        user_id=user.id,
        team_id=membership.team_id if membership else None,
        operation_id=str(body.operation_id),
    )
    if player is None:
        player = PixelPlayer(user_id=user.id, ready_at=at + COOLDOWN)
        db.add(player)
    else:
        player.ready_at = at + COOLDOWN
    await db.flush()
    return receipt(move, at)


def receipt(move: PixelMove, at: datetime, *, replayed: bool = False) -> PixelReceipt:
    return PixelReceipt(
        round_id=move.round_id,
        revision=move.revision,
        index=move.cell_index,
        color=move.color,
        server_time=at,
        ready_at=as_utc(move.created_at) + COOLDOWN,
        replayed=replayed,
    )


async def scores(db: AsyncSession, board: PixelRound, user_id: str) -> PixelScores:
    at = min(utc_now(), as_utc(board.ends_at))
    membership = await db.scalar(
        select(TeamMembership).where(
            TeamMembership.user_id == user_id,
            TeamMembership.state == "active",
        )
    )
    rows = await db.execute(
        select(PixelTeamScore, Team.name)
        .join(Team)
        .where(
            PixelTeamScore.round_id == board.id,
        )
    )
    entries: list[tuple[int, PixelTeamView]] = []
    for score, name in rows:
        elapsed = max(0, int((at - as_utc(score.accrued_at)).total_seconds() * 1000))
        total = score.pixel_ms + score.held_pixels * elapsed
        entries.append(
            (
                total,
                PixelTeamView(
                    team_id=score.team_id,
                    name=name,
                    held_pixels=score.held_pixels,
                    points=total // 60_000,
                    is_mine=bool(membership and membership.team_id == score.team_id),
                ),
            )
        )
    entries.sort(key=lambda item: (-item[0], -item[1].held_pixels, item[1].team_id))
    all_teams = [entry for _, entry in entries]
    return PixelScores(
        teams=all_teams[:20], my_team=next((e for e in all_teams if e.is_mine), None)
    )
