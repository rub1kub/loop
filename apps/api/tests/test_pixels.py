from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.config import get_settings
from app.dependencies import current_control_wallet
from app.models import User
from app.modules.pixels import router as pixel_router
from app.modules.pixels import service
from app.modules.pixels.models import PixelMove, PixelRound, PixelShare
from app.modules.teams.models import TeamMembership
from app.security import issue_session


@pytest.fixture(autouse=True)
def pixel_settings(monkeypatch):
    monkeypatch.setenv("LOOP_PIXEL_BATTLE_ENABLED", "true")


@pytest.fixture
def clock(monkeypatch):
    instant = [datetime(2026, 9, 28, 12, tzinfo=UTC)]
    monkeypatch.setattr(service, "utc_now", lambda: instant[0])
    monkeypatch.setattr(pixel_router, "utc_now", lambda: instant[0])
    return instant


async def player(app, number=1):
    async with app.state.session_factory() as db:
        user = User(telegram_id=9_700_000_000 + number, first_name=f"Painter {number}")
        db.add(user)
        await db.commit()
        token, _ = issue_session(user.id, user.telegram_id, str(uuid4()), get_settings())
        return user.id, {"Authorization": f"Bearer {token}"}


def move(round_id, *, x=10, y=20, color=4, operation_id=None):
    return dict(round_id=round_id, x=x, y=y, color=color, operation_id=operation_id or str(uuid4()))


async def snapshot(client, headers):
    response = await client.get("/api/v1/pixels", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_canvas_needs_auth_and_can_stay_disabled(client, app):
    assert (await client.get("/api/v1/pixels")).status_code == 401
    _, headers = await player(app)
    get_settings().pixel_battle_enabled = False
    assert (await snapshot(client, headers))["enabled"] is False
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PixelRound)) == 0
    denied = await client.post("/api/v1/pixels/moves", headers=headers, json=move("2026-09-28"))
    assert denied.status_code == 409


async def test_snapshot_and_move_are_free_and_idempotent(client, app, clock):
    _, headers = await player(app)
    before = await snapshot(client, headers)
    assert before["size"] == 128
    assert before["pixels"] == "0" * 16384
    assert before["ready_at"] is None
    body = move(before["round"]["id"])
    first = await client.post("/api/v1/pixels/moves", headers=headers, json=body)
    assert first.status_code == 200
    assert first.json()["revision"] == 1
    assert first.json()["replayed"] is False
    second = await client.post("/api/v1/pixels/moves", headers=headers, json=body)
    assert second.status_code == 200
    assert second.json()["revision"] == 1 and second.json()["replayed"] is True
    changed = await client.post("/api/v1/pixels/moves", headers=headers, json={**body, "x": 12})
    assert changed.status_code == 409
    after = await snapshot(client, headers)
    assert after["pixels"][20 * 128 + 10] == "4"
    assert after["round"]["revision"] == 1
    assert after["cooldown_seconds"] == 2


async def test_next_pixel_is_allowed_at_exactly_two_seconds(client, app, clock):
    _, headers = await player(app)
    board = (await snapshot(client, headers))["round"]["id"]
    started = clock[0]
    first = await client.post("/api/v1/pixels/moves", headers=headers, json=move(board))
    assert first.status_code == 200
    assert datetime.fromisoformat(first.json()["ready_at"]) == started + timedelta(seconds=2)

    for milliseconds, retry_after in [(0, "2"), (1000, "1"), (1999, "1")]:
        clock[0] = started + timedelta(milliseconds=milliseconds)
        blocked = await client.post("/api/v1/pixels/moves", headers=headers, json=move(board, x=11))
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"] == retry_after

    clock[0] = started + timedelta(seconds=2)
    second = await client.post("/api/v1/pixels/moves", headers=headers, json=move(board, x=11))
    assert second.status_code == 200
    assert second.json()["revision"] == 2
    assert datetime.fromisoformat(second.json()["ready_at"]) == started + timedelta(seconds=4)


async def test_server_cooldown_survives_a_new_session_and_week(client, app, clock):
    user_id, first_headers = await player(app)
    clock[0] = datetime(2026, 10, 4, 20, 59, 59, tzinfo=UTC)
    board = await snapshot(client, first_headers)
    assert (
        await client.post(
            "/api/v1/pixels/moves", headers=first_headers, json=move(board["round"]["id"])
        )
    ).status_code == 200
    token, _ = issue_session(user_id, 9_700_000_001, str(uuid4()), get_settings())
    second_headers = {"Authorization": f"Bearer {token}"}
    clock[0] += timedelta(seconds=1)
    next_board = await snapshot(client, second_headers)
    assert next_board["round"]["id"] != board["round"]["id"]
    blocked = await client.post(
        "/api/v1/pixels/moves", headers=second_headers, json=move(next_board["round"]["id"])
    )
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "1"
    clock[0] += timedelta(seconds=1)
    allowed = await client.post(
        "/api/v1/pixels/moves", headers=second_headers, json=move(next_board["round"]["id"])
    )
    assert allowed.status_code == 200


async def test_old_retry_keeps_the_newer_cooldown(client, app, clock):
    _, headers = await player(app)
    board = (await snapshot(client, headers))["round"]["id"]
    first_body = move(board)
    await client.post("/api/v1/pixels/moves", headers=headers, json=first_body)
    clock[0] += timedelta(seconds=2)
    second = await client.post("/api/v1/pixels/moves", headers=headers, json=move(board, x=11))
    retry = await client.post("/api/v1/pixels/moves", headers=headers, json=first_body)
    assert retry.json()["revision"] == 1
    assert retry.json()["ready_at"] == second.json()["ready_at"]


async def test_noop_does_not_spend_a_move_and_changes_have_no_identity(client, app, clock):
    _, headers = await player(app)
    board = await snapshot(client, headers)
    noop = await client.post(
        "/api/v1/pixels/moves", headers=headers, json=move(board["round"]["id"], color=0)
    )
    assert noop.status_code == 409
    assert (await snapshot(client, headers))["ready_at"] is None
    good = await client.post(
        "/api/v1/pixels/moves", headers=headers, json=move(board["round"]["id"])
    )
    assert good.status_code == 200
    changes = await client.get(
        "/api/v1/pixels", headers=headers, params={"round_id": board["round"]["id"], "after": 0}
    )
    assert changes.json()["pixels"] is None
    assert changes.json()["changes"] == [{"revision": 1, "index": 2570, "color": 4}]
    stale = await client.get(
        "/api/v1/pixels", headers=headers, params={"round_id": board["round"]["id"], "after": 99}
    )
    assert stale.json()["pixels"] is not None


@pytest.mark.parametrize(
    "override",
    [
        {"x": -1},
        {"x": 128},
        {"y": 128},
        {"x": True},
        {"y": 1.5},
        {"color": 16},
        {"color": -1},
        {"color": "3"},
        {"user_id": "other-player"},
        {"team_id": "other-team"},
        {"ready_at": "2000-01-01"},
    ],
)
async def test_client_cannot_forge_rules(client, app, clock, override):
    _, headers = await player(app)
    board = await snapshot(client, headers)
    bad = await client.post(
        "/api/v1/pixels/moves", headers=headers, json={**move(board["round"]["id"]), **override}
    )
    assert bad.status_code == 422
    assert (await snapshot(client, headers))["round"]["revision"] == 0


async def test_deadline_freezes_archive_and_retries_still_confirm_old_move(client, app, clock):
    _, headers = await player(app)
    board = await snapshot(client, headers)
    body = move(board["round"]["id"])
    await client.post("/api/v1/pixels/moves", headers=headers, json=body)
    clock[0] = datetime.fromisoformat(board["round"]["ends_at"].replace("Z", "+00:00"))
    assert (
        await client.post("/api/v1/pixels/moves", headers=headers, json=move(board["round"]["id"]))
    ).status_code == 409
    replay = await client.post("/api/v1/pixels/moves", headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    archived = await client.get(f"/api/v1/pixels/rounds/{board['round']['id']}", headers=headers)
    assert archived.json()["round"]["archived"] is True
    assert archived.json()["pixels"][2570] == "4"
    rounds = await client.get("/api/v1/pixels/archive", headers=headers)
    assert len(rounds.json()) == 1
    assert (await snapshot(client, headers))["pixels"] == "0" * 16384


async def test_team_scores_area_time_not_clicks_and_stop_at_deadline(client, app, clock):
    _, a = await player(app, 1)
    _, b = await player(app, 2)
    team_a = (await client.post("/api/v1/teams", headers=a, json={"name": "Painters A"})).json()
    team_b = (await client.post("/api/v1/teams", headers=b, json={"name": "Painters B"})).json()
    board_id = (await snapshot(client, a))["round"]["id"]
    await client.post("/api/v1/pixels/moves", headers=a, json=move(board_id, color=4))
    clock[0] += timedelta(seconds=30)
    await client.post("/api/v1/pixels/moves", headers=a, json=move(board_id, color=5))
    clock[0] += timedelta(seconds=30)
    await client.post("/api/v1/pixels/moves", headers=b, json=move(board_id, color=6))
    clock[0] += timedelta(seconds=60)
    response = await client.get(f"/api/v1/pixels/rounds/{board_id}/scores", headers=a)
    teams = {row["team_id"]: row for row in response.json()["teams"]}
    assert teams[team_a["id"]]["points"] == 1
    assert teams[team_a["id"]]["held_pixels"] == 0
    assert teams[team_b["id"]]["points"] == 1
    assert teams[team_b["id"]]["held_pixels"] == 1
    clock[0] = datetime(2026, 10, 5, 0, tzinfo=UTC)
    frozen = (await client.get(f"/api/v1/pixels/rounds/{board_id}/scores", headers=a)).json()
    clock[0] += timedelta(days=7)
    assert (
        await client.get(f"/api/v1/pixels/rounds/{board_id}/scores", headers=a)
    ).json() == frozen


async def test_leaving_team_keeps_existing_pixel_attribution(client, app, clock):
    user_id, headers = await player(app)
    team = (await client.post("/api/v1/teams", headers=headers, json={"name": "Old team"})).json()
    board_id = (await snapshot(client, headers))["round"]["id"]
    await client.post("/api/v1/pixels/moves", headers=headers, json=move(board_id))
    async with app.state.session_factory() as db:
        membership = await db.scalar(
            select(TeamMembership).where(TeamMembership.user_id == user_id)
        )
        membership.state = "left"
        await db.commit()
    clock[0] += timedelta(seconds=60)
    response = await client.get(f"/api/v1/pixels/rounds/{board_id}/scores", headers=headers)
    assert response.json()["my_team"] is None
    assert response.json()["teams"][0]["team_id"] == team["id"]
    assert response.json()["teams"][0]["points"] == 1


async def test_moderation_requires_control_and_leaves_a_public_audit(client, app, clock):
    _, headers = await player(app)
    board_id = (await snapshot(client, headers))["round"]["id"]
    await client.post("/api/v1/pixels/moves", headers=headers, json=move(board_id))
    body = {
        "round_id": board_id,
        "operation_id": str(uuid4()),
        "x": 10,
        "y": 20,
        "width": 1,
        "height": 1,
        "reason": "Тестовая модерация",
    }
    assert (
        await client.post("/api/v1/control/pixels/clear", headers=headers, json=body)
    ).status_code == 401
    app.dependency_overrides[current_control_wallet] = lambda: "test-operator"
    try:
        for _ in range(2):
            result = await client.post("/api/v1/control/pixels/clear", json=body)
            assert result.status_code == 204
    finally:
        app.dependency_overrides.pop(current_control_wallet)
    after = await snapshot(client, headers)
    assert after["pixels"][2570] == "0"
    assert after["round"]["revision"] == 2
    log = (await client.get(f"/api/v1/pixels/rounds/{board_id}/moderation", headers=headers)).json()
    assert len(log) == 1 and log[0]["reason"] == "Тестовая модерация"
    assert "actor_hash" not in log[0]


async def test_share_freezes_real_pixels_and_rate_limits_storage(client, app, clock):
    _, headers = await player(app)
    app.state.bot = None
    get_settings().bot_username = "getloopbot"
    board_id = (await snapshot(client, headers))["round"]["id"]
    body = {"round_id": board_id, "x": 10, "y": 20}
    first = (await client.post("/api/v1/pixels/share", headers=headers, json=body)).json()
    second = (await client.post("/api/v1/pixels/share", headers=headers, json=body)).json()
    assert first["image_url"] == second["image_url"]
    other_crop = await client.post("/api/v1/pixels/share", headers=headers, json={**body, "x": 60})
    assert other_crop.status_code == 429
    assert first["prepared_message_id"] is None
    card = await client.get(first["image_url"])
    assert card.status_code == 200
    assert Image.open(BytesIO(card.content)).size == (1080, 1080)
    share_id = first["url"].split("pixel_")[1]
    region = await client.get(f"/api/v1/pixels/shares/{share_id}", headers=headers)
    assert region.json() == body
    async with app.state.session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PixelShare)) == 1
        assert await db.scalar(select(func.count()).select_from(PixelMove)) == 0
