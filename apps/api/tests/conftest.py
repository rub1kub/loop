import os

os.environ.update(
    LOOP_APP_ENV="test",
    LOOP_DATABASE_URL="sqlite+aiosqlite:///:memory:",
    LOOP_REDIS_URL="redis://localhost:6399/15",
    LOOP_AUTO_CREATE_SCHEMA="true",
    LOOP_BOT_TOKEN="123456:test-token",
    LOOP_SESSION_SECRET="test-session-secret-with-enough-entropy",
    LOOP_PUBLIC_ORIGIN="https://loop.test",
    LOOP_CORS_ORIGINS="https://loop.test",
    LOOP_BANK_CONTRACT_ADDRESS="0:" + "12" * 32,
    LOOP_TON_CONTRACT_ADDRESS="0:" + "11" * 32,
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app
from app.nonce_store import MemoryChallengeStore


@pytest.fixture(autouse=True)
def reset_settings() -> None:
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def app():
    application = create_app()
    async with application.router.lifespan_context(application):
        application.state.challenge_store = MemoryChallengeStore()
        yield application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://loop.test") as http:
        yield http
