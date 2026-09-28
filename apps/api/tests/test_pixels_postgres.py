"""Run against a disposable local PostgreSQL database, never the application's database."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base
from app.models import User
from app.modules.pixels import router as pixel_router
from app.modules.pixels import service
from app.modules.pixels.models import PixelMove, PixelRound
from app.modules.pixels.schemas import PixelPlaceRequest
from app.security import issue_session


@pytest_asyncio.fixture
async def pg_store(monkeypatch):
    url = os.environ.get("LOOP_PIXEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Provide the dedicated local pixel test database")
    target = make_url(url)
    if target.host != "127.0.0.1" or target.database != "loop_pixels_test":
        pytest.fail("Pixel concurrency tests require the dedicated loop_pixels_test database")
    schema = "pixels_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url,
        connect_args={"server_settings": {"search_path": schema}},
        pool_size=16,
        max_overflow=16,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    at = [datetime(2026, 9, 28, 12, tzinfo=UTC)]
    monkeypatch.setattr(service, "utc_now", lambda: at[0])
    monkeypatch.setattr(pixel_router, "utc_now", lambda: at[0])
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        board = await service.ensure_round(db, at[0])
        users = [User(telegram_id=9_800_000_000 + i, first_name="Pixel test") for i in range(24)]
        db.add_all(users)
        await db.commit()
        ids = [u.id for u in users]
        board_id = board.id
    try:
        yield factory, ids, board_id, at
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def attempt(factory, user_id, body):
    async with factory() as db:
        user = await db.get(User, user_id)
        try:
            receipt = await service.place(db, user, body)
            await db.commit()
            return 200, receipt
        except HTTPException as exc:
            await db.rollback()
            return exc.status_code, None


async def test_parallel_devices_cannot_spend_two_moves(pg_store):
    factory, users, board, _ = pg_store
    results = await asyncio.gather(
        *[
            attempt(
                factory,
                users[0],
                PixelPlaceRequest(round_id=board, x=i, y=2, color=4, operation_id=uuid4()),
            )
            for i in range(16)
        ]
    )
    assert sorted(status for status, _ in results) == [200] + [429] * 15
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PixelMove)) == 1


async def test_parallel_retries_all_confirm_one_revision(pg_store):
    factory, users, board, _ = pg_store
    body = PixelPlaceRequest(round_id=board, x=5, y=6, color=9, operation_id=uuid4())
    results = await asyncio.gather(*[attempt(factory, users[0], body) for _ in range(16)])
    assert all(status == 200 and receipt.revision == 1 for status, receipt in results)
    assert sum(not receipt.replayed for _, receipt in results) == 1


async def test_competing_pixels_commit_in_one_global_order(pg_store):
    factory, users, board, _ = pg_store
    results = await asyncio.gather(
        *[
            attempt(
                factory,
                users[i],
                PixelPlaceRequest(round_id=board, x=64, y=64, color=i + 1, operation_id=uuid4()),
            )
            for i in range(15)
        ]
    )
    assert all(status == 200 for status, _ in results)
    assert sorted(receipt.revision for _, receipt in results) == list(range(1, 16))
    final = max((receipt for _, receipt in results), key=lambda r: r.revision)
    async with factory() as db:
        snapshot = await db.get(PixelRound, board)
        assert snapshot.revision == 15
        assert snapshot.pixels[64 * 128 + 64] == final.color


async def test_lock_wait_cannot_sneak_a_pixel_past_deadline(pg_store):
    factory, users, board, at = pg_store
    async with factory() as owner:
        locked = await owner.scalar(
            select(PixelRound).where(PixelRound.id == board).with_for_update()
        )
        task = asyncio.create_task(
            attempt(
                factory,
                users[0],
                PixelPlaceRequest(round_id=board, x=0, y=0, color=1, operation_id=uuid4()),
            )
        )
        await asyncio.sleep(0.1)
        assert not task.done()
        at[0] = locked.ends_at + timedelta(seconds=1)
        await owner.commit()
    assert (await asyncio.wait_for(task, 5))[0] == 409


async def test_move_record_failure_rolls_back_color_score_and_cooldown(pg_store):
    factory, users, board, _ = pg_store
    async with factory() as db:
        user = await db.get(User, users[0])
        await service.place(
            db, user, PixelPlaceRequest(round_id=board, x=3, y=4, color=6, operation_id=uuid4())
        )
        await db.rollback()
    result = await attempt(
        factory,
        users[0],
        PixelPlaceRequest(round_id=board, x=3, y=4, color=6, operation_id=uuid4()),
    )
    assert result[0] == 200 and result[1].revision == 1


@pytest_asyncio.fixture
async def pixel_redis():
    url = os.environ.get("LOOP_PIXEL_TEST_REDIS_URL")
    if not url:
        pytest.skip("Provide the dedicated local pixel test Redis")
    if url != "redis://127.0.0.1:55440/0":
        pytest.fail("Pixel synchronization tests require the dedicated local Redis")
    client = Redis.from_url(url, decode_responses=True)
    await client.ping()
    try:
        yield client
    finally:
        await client.aclose()


async def await_lease(redis, user_id):
    async with asyncio.timeout(3):
        while not await redis.exists(f"loop:pixels:watch:{user_id}:0"):  # noqa: ASYNC110
            await asyncio.sleep(0.01)


async def test_long_poll_releases_connection_and_wakes_after_commit(
    pg_store, pixel_redis, app, client, monkeypatch
):
    factory, users, board, _ = pg_store
    monkeypatch.setattr(app.state, "session_factory", factory)
    monkeypatch.setattr(app.state, "redis", pixel_redis)
    get_settings().pixel_battle_enabled = True
    token, _ = issue_session(users[0], 9_800_000_000, str(uuid4()), get_settings())
    headers = {"Authorization": f"Bearer {token}"}
    waiting = asyncio.create_task(
        client.get(
            "/api/v1/pixels",
            headers=headers,
            params={"round_id": board, "after": 0, "wait": 20},
        )
    )
    try:
        await await_lease(pixel_redis, users[0])
        await attempt(
            factory,
            users[1],
            PixelPlaceRequest(round_id=board, x=20, y=10, color=4, operation_id=uuid4()),
        )
        await pixel_redis.publish(pixel_router.CHANNEL, "changed")
        result = await asyncio.wait_for(waiting, 3)
        assert result.status_code == 200
        assert result.headers["Cache-Control"] == "private, no-store"
        assert result.json()["round"]["revision"] == 1
        assert result.json()["changes"] == [{"revision": 1, "index": 1300, "color": 4}]
        assert not await pixel_redis.exists(f"loop:pixels:watch:{users[0]}:0")
    finally:
        if not waiting.done():
            waiting.cancel()
            await asyncio.gather(waiting, return_exceptions=True)


async def test_watch_limit_and_cancellation_release_only_owned_leases(pg_store, pixel_redis):
    factory, users, board, _ = pg_store

    async def disconnected():
        return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=pixel_redis)),
        is_disconnected=disconnected,
    )
    keys = [f"loop:pixels:watch:{users[0]}:{i}" for i in range(3)]
    for key in keys:
        await pixel_redis.set(key, "another-device", ex=25)
    try:
        async with factory() as db:
            with pytest.raises(HTTPException) as blocked:
                await pixel_router.wait_for_change(request, db, users[0], board, 0, 20)
            assert blocked.value.status_code == 429
            assert not db.in_transaction()
        assert await pixel_redis.mget(keys) == ["another-device"] * 3
    finally:
        await pixel_redis.delete(*keys)
    async with factory() as db:
        task = asyncio.create_task(
            pixel_router.wait_for_change(request, db, users[0], board, 0, 20)
        )
        await await_lease(pixel_redis, users[0])
        # Allow subscribe + the last revision check to finish before canceling.
        await asyncio.sleep(0.05)
        assert not db.in_transaction()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not await pixel_redis.exists(*keys)


async def test_read_budget_is_shared_between_devices(pg_store, pixel_redis):
    _, users, _, _ = pg_store
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=pixel_redis)))
    settings = SimpleNamespace(app_env="production")
    for _ in range(120):
        await pixel_router.read_budget(request, users[0], settings)
    with pytest.raises(HTTPException) as blocked:
        await pixel_router.read_budget(request, users[0], settings)
    assert blocked.value.status_code == 429
    await pixel_router.read_budget(request, users[1], settings)


async def test_first_visitors_create_a_single_new_round(pg_store):
    factory, _, _, at = pg_store
    next_week = at[0] + timedelta(days=7)

    async def visit():
        async with factory() as db:
            board = await service.ensure_round(db, next_week)
            await db.commit()
            return board.id

    boards = await asyncio.gather(*[visit() for _ in range(16)])
    assert set(boards) == {"2026-10-05"}
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(PixelRound)) == 2
