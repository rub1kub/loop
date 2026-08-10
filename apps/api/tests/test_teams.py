import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from sqlalchemy import func, select

from app.models import User
from app.modules.teams.models import (
    Team,
    TeamInvite,
    TeamMemberSeasonStats,
    TeamMembership,
    TeamScoreEvent,
    TeamSeasonStats,
)
from app.modules.teams.scoring import record_team_score_event
from app.modules.teams.service import create_invite, ensure_season


def signed_init_data(telegram_id: int) -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": f"AAE-teams-{telegram_id}",
        "user": json.dumps(
            {"id": telegram_id, "first_name": f"Игрок {telegram_id}"},
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", b"123456:test-token", hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def authenticate(client, telegram_id: int) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_init_data(telegram_id)},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_team_has_no_member_cap_and_enforces_change_cooldown(client) -> None:
    owner = await authenticate(client, 8_100_000_001)
    created = await client.post(
        "/api/v1/teams",
        headers=owner,
        json={"name": "Бесконечный круг", "tag": "КРУГ", "join_policy": "open"},
    )
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]

    member_headers: list[dict[str, str]] = []
    for index in range(12):
        headers = await authenticate(client, 8_100_001_000 + index)
        member_headers.append(headers)
        joined = await client.post(f"/api/v1/teams/{slug}/join", headers=headers, json={})
        assert joined.status_code == 200, joined.text
        assert joined.json()["state"] == "joined"

    detail = await client.get(f"/api/v1/teams/{slug}", headers=owner)
    assert detail.status_code == 200
    assert detail.json()["member_count"] == 13

    leaving = member_headers[0]
    assert (await client.post(f"/api/v1/teams/{slug}/leave", headers=leaving)).status_code == 204
    blocked = await client.post(f"/api/v1/teams/{slug}/join", headers=leaving, json={})
    assert blocked.status_code == 409
    assert "после" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_join_requests_require_team_manager(client) -> None:
    owner = await authenticate(client, 8_200_000_001)
    applicant = await authenticate(client, 8_200_000_002)
    outsider = await authenticate(client, 8_200_000_003)
    created = await client.post(
        "/api/v1/teams",
        headers=owner,
        json={"name": "Тихая линия", "tag": "ЛИНИЯ", "join_policy": "request"},
    )
    slug = created.json()["slug"]

    requested = await client.post(f"/api/v1/teams/{slug}/join", headers=applicant, json={})
    assert requested.status_code == 200
    assert requested.json()["state"] == "requested"
    request_id = (await client.get(f"/api/v1/teams/{slug}", headers=owner)).json()[
        "pending_requests"
    ][0]["id"]

    denied = await client.post(
        f"/api/v1/teams/{slug}/requests/{request_id}",
        headers=outsider,
        json={"approve": True},
    )
    assert denied.status_code == 403
    approved = await client.post(
        f"/api/v1/teams/{slug}/requests/{request_id}",
        headers=owner,
        json={"approve": True},
    )
    assert approved.status_code == 204
    member_view = await client.get(f"/api/v1/teams/{slug}", headers=applicant)
    assert member_view.json()["my_role"] == "member"


@pytest.mark.asyncio
async def test_score_is_temporal_idempotent_and_bank_flow_drives_rank(client, app) -> None:
    headers = await authenticate(client, 8_300_000_001)
    created = await client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": "Первый импульс", "tag": "ПУЛЬС", "join_policy": "open"},
    )
    assert created.status_code == 201
    team_id = created.json()["id"]

    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 8_300_000_001))
        membership = await db.scalar(
            select(TeamMembership).where(
                TeamMembership.user_id == user.id,
                TeamMembership.state == "active",
            )
        )
        assert user is not None and membership is not None
        event_at = datetime.now(UTC)
        membership.joined_at = event_at
        await db.flush()

        first = await record_team_score_event(
            db,
            user_id=user.id,
            source_kind="bank_entry",
            source_entity_id="bank-position-1",
            source_key="bank_entry:-3:bank-position-1",
            amount_nano=2_500_000_000,
            network=-3,
            tx_hash="a" * 64,
            event_at=event_at,
        )
        replay = await record_team_score_event(
            db,
            user_id=user.id,
            source_kind="bank_entry",
            source_entity_id="bank-position-1",
            source_key="bank_entry:-3:bank-position-1",
            amount_nano=2_500_000_000,
            network=-3,
            tx_hash="a" * 64,
            event_at=event_at,
        )
        duel = await record_team_score_event(
            db,
            user_id=user.id,
            source_kind="duel_settlement",
            source_entity_id="duel-settlement-1",
            source_key=f"duel_settlement:-3:duel-settlement-1:{user.id}",
            amount_nano=99_000_000_000,
            network=-3,
            tx_hash="b" * 64,
            event_at=event_at,
        )
        await db.commit()

        assert first is True
        assert replay is False
        assert duel is True
        assert int(await db.scalar(select(func.count()).select_from(TeamScoreEvent)) or 0) == 2
        team_stats = await db.scalar(
            select(TeamSeasonStats).where(TeamSeasonStats.team_id == team_id)
        )
        member_stats = await db.scalar(
            select(TeamMemberSeasonStats).where(TeamMemberSeasonStats.team_id == team_id)
        )
        assert team_stats is not None and member_stats is not None
        assert team_stats.flow_nano == 2_500_000_000
        assert team_stats.duel_settlements == 1
        assert team_stats.active_members == 1
        assert member_stats.flow_nano == 2_500_000_000

    overview = await client.get("/api/v1/teams/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    mine = overview.json()["my_team"]
    assert mine["flow_nano"] == 2_500_000_000
    assert mine["duel_settlements"] == 1


@pytest.mark.asyncio
async def test_invite_token_is_hashed_and_public_card_is_jpeg(client, app) -> None:
    headers = await authenticate(client, 8_400_000_001)
    created = await client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": "Белый шум", "tag": "ШУМ", "join_policy": "invite"},
    )
    slug = created.json()["slug"]

    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 8_400_000_001))
        team = await db.scalar(select(Team).where(Team.slug == slug))
        assert user is not None and team is not None
        invite, token = await create_invite(db, team, user)
        await db.commit()
        stored = await db.get(TeamInvite, invite.id)
        assert stored is not None
        assert stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in stored.token_hash

    card = await client.get(f"/api/v1/team-cards/{slug}.jpg")
    assert card.status_code == 200
    assert card.headers["content-type"] == "image/jpeg"
    assert card.content.startswith(b"\xff\xd8")


@pytest.mark.asyncio
async def test_score_stays_with_membership_at_chain_time(client, app) -> None:
    first_owner = await authenticate(client, 8_500_000_001)
    second_owner = await authenticate(client, 8_500_000_002)
    member_headers = await authenticate(client, 8_500_000_003)
    first = await client.post(
        "/api/v1/teams",
        headers=first_owner,
        json={"name": "Первая волна", "tag": "ВОЛНА1", "join_policy": "open"},
    )
    second = await client.post(
        "/api/v1/teams",
        headers=second_owner,
        json={"name": "Вторая волна", "tag": "ВОЛНА2", "join_policy": "open"},
    )
    first_team_id = first.json()["id"]
    second_team_id = second.json()["id"]
    first_slug = first.json()["slug"]
    second_slug = second.json()["slug"]
    assert (
        await client.post(f"/api/v1/teams/{first_slug}/join", headers=member_headers, json={})
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/teams/{first_slug}/leave", headers=member_headers)
    ).status_code == 204

    old_event_at = datetime.now(UTC) - timedelta(hours=27)
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 8_500_000_003))
        membership = await db.scalar(
            select(TeamMembership).where(TeamMembership.user_id == user.id)
        )
        assert user is not None and membership is not None
        membership.joined_at = old_event_at - timedelta(hours=1)
        membership.left_at = old_event_at + timedelta(hours=1)
        await db.commit()
        assert await record_team_score_event(
            db,
            user_id=user.id,
            source_kind="bank_entry",
            source_entity_id="historic-position",
            source_key="bank_entry:-3:historic-position",
            amount_nano=1_000_000_000,
            network=-3,
            tx_hash="c" * 64,
            event_at=old_event_at,
        )
        await db.commit()

    joined_second = await client.post(
        f"/api/v1/teams/{second_slug}/join", headers=member_headers, json={}
    )
    assert joined_second.status_code == 200, joined_second.text
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 8_500_000_003))
        assert user is not None
        assert await record_team_score_event(
            db,
            user_id=user.id,
            source_kind="bank_entry",
            source_entity_id="current-position",
            source_key="bank_entry:-3:current-position",
            amount_nano=2_000_000_000,
            network=-3,
            tx_hash="d" * 64,
            event_at=datetime.now(UTC),
        )
        await db.commit()
        events = (
            (await db.execute(select(TeamScoreEvent).where(TeamScoreEvent.user_id == user.id)))
            .scalars()
            .all()
        )
        assert {(event.team_id, event.amount_nano) for event in events} == {
            (first_team_id, 1_000_000_000),
            (second_team_id, 2_000_000_000),
        }


@pytest.mark.asyncio
async def test_owner_can_transfer_team_without_two_active_owners(client) -> None:
    owner = await authenticate(client, 8_600_000_001)
    successor = await authenticate(client, 8_600_000_002)
    created = await client.post(
        "/api/v1/teams",
        headers=owner,
        json={"name": "Смена сигнала", "tag": "СМЕНА", "join_policy": "open"},
    )
    slug = created.json()["slug"]
    joined = await client.post(f"/api/v1/teams/{slug}/join", headers=successor, json={})
    successor_id = next(
        member["user_id"] for member in joined.json()["team"]["top_members"] if member["is_me"]
    )
    transferred = await client.post(
        f"/api/v1/teams/{slug}/transfer",
        headers=owner,
        json={"user_id": successor_id},
    )
    assert transferred.status_code == 204, transferred.text
    assert (await client.get(f"/api/v1/teams/{slug}", headers=successor)).json()[
        "my_role"
    ] == "owner"
    assert (await client.get(f"/api/v1/teams/{slug}", headers=owner)).json()["my_role"] == "admin"


@pytest.mark.asyncio
async def test_team_share_prepares_telegram_card_with_invite_and_referral(
    client, app, monkeypatch
) -> None:
    class PreparedBot:
        def __init__(self) -> None:
            self.kwargs = None

        async def save_prepared_inline_message(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                id="team-prepared-message",
                expiration_date=int(datetime.now(UTC).timestamp()) + 300,
            )

    headers = await authenticate(client, 8_700_000_001)
    created = await client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": "Общий ритм", "tag": "РИТМ", "join_policy": "open"},
    )
    bot = PreparedBot()
    monkeypatch.setattr(app.state, "bot", bot)

    response = await client.post(
        f"/api/v1/teams/{created.json()['slug']}/share",
        headers=headers,
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["prepared_message_id"] == "team-prepared-message"
    token = response.json()["fallback_query"].removeprefix("team ")
    assert len(token) >= 12
    assert bot.kwargs is not None
    result = bot.kwargs["result"]
    button_url = result.reply_markup.inline_keyboard[0][0].url
    assert f"team_{token}-ref_" in button_url
    assert result.photo_url.startswith("https://loop.test/api/v1/team-cards/")


@pytest.mark.asyncio
async def test_team_mutations_are_authenticated_and_score_has_no_client_endpoint(client) -> None:
    assert (await client.get("/api/v1/teams/overview")).status_code == 401
    headers = await authenticate(client, 8_800_000_001)
    rejected = await client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": "<script>alert(1)</script>", "tag": "SAFE", "join_policy": "open"},
    )
    assert rejected.status_code == 422
    no_score_endpoint = await client.post(
        "/api/v1/teams/score",
        headers=headers,
        json={"amount_nano": 999_000_000_000},
    )
    assert no_score_endpoint.status_code in {404, 405}


@pytest.mark.asyncio
async def test_weekly_ranking_query_handles_hundreds_of_unlimited_teams(client, app) -> None:
    headers = await authenticate(client, 8_900_000_001)
    async with app.state.session_factory() as db:
        season = await ensure_season(db)
        for index in range(250):
            user_id = f"u{index:035d}"
            team_id = f"t{index:035d}"
            db.add(
                User(
                    id=user_id,
                    telegram_id=8_910_000_000 + index,
                    first_name=f"Игрок {index}",
                )
            )
            db.add(
                Team(
                    id=team_id,
                    slug=f"load-{index}",
                    name=f"Команда {index}",
                    tag=f"T{index:04d}",
                    mark=index % 12,
                    join_policy="open",
                    state="active",
                    owner_user_id=user_id,
                )
            )
            db.add(
                TeamMembership(
                    id=f"m{index:035d}",
                    team_id=team_id,
                    user_id=user_id,
                    role="owner",
                    state="active",
                )
            )
            db.add(
                TeamSeasonStats(
                    id=f"s{index:035d}",
                    season_id=season.id,
                    team_id=team_id,
                    flow_nano=index * 1_000_000_000,
                    bank_entries=index,
                    bank_payouts=index // 2,
                    duel_settlements=index // 3,
                    active_members=1,
                )
            )
        await db.commit()

    response = await client.get("/api/v1/teams/overview", headers=headers)
    assert response.status_code == 200, response.text
    leaderboard = response.json()["leaderboard"]
    assert len(leaderboard) == 30
    assert leaderboard[0]["rank"] == 1
    assert leaderboard[0]["flow_nano"] == 249_000_000_000
    assert [item["flow_nano"] for item in leaderboard] == sorted(
        (item["flow_nano"] for item in leaderboard), reverse=True
    )


@pytest.mark.asyncio
async def test_owner_controls_brand_and_roles_while_admin_controls_membership(client) -> None:
    owner = await authenticate(client, 8_950_000_001)
    admin = await authenticate(client, 8_950_000_002)
    created = await client.post(
        "/api/v1/teams",
        headers=owner,
        json={"name": "Новый контур", "tag": "КОНТУР", "join_policy": "open"},
    )
    slug = created.json()["slug"]
    joined = await client.post(f"/api/v1/teams/{slug}/join", headers=admin, json={})
    admin_id = next(
        item["user_id"] for item in joined.json()["team"]["top_members"] if item["is_me"]
    )
    promoted = await client.patch(
        f"/api/v1/teams/{slug}/members/{admin_id}",
        headers=owner,
        json={"role": "admin"},
    )
    assert promoted.status_code == 204

    branded = await client.patch(
        f"/api/v1/teams/{slug}",
        headers=owner,
        json={
            "name": "Белый контур",
            "description": "Собираем сильную неделю вместе.",
            "mark": 5,
        },
    )
    assert branded.status_code == 200, branded.text
    assert branded.json()["name"] == "Белый контур"
    assert branded.json()["description"] == "Собираем сильную неделю вместе."
    assert branded.json()["mark"] == 5

    forbidden_brand = await client.patch(
        f"/api/v1/teams/{slug}",
        headers=admin,
        json={"description": "Перехват управления"},
    )
    assert forbidden_brand.status_code == 403
    policy = await client.patch(
        f"/api/v1/teams/{slug}",
        headers=admin,
        json={"join_policy": "request"},
    )
    assert policy.status_code == 200
    assert policy.json()["join_policy"] == "request"
