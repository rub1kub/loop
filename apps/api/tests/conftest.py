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
    LOOP_CONTROL_ADMIN_WALLET="0:" + "22" * 32,
    LOOP_BANK_CONTRACT_ADDRESS="0:" + "12" * 32,
    LOOP_BANK_CONTRACT_CODE_HASH="AA" * 32,
    LOOP_TON_CONTRACT_ADDRESS="0:" + "11" * 32,
    LOOP_TON_CONTRACT_CODE_HASH="BB" * 32,
    LOOP_DUEL_INVITE_SIGNING_KEY=(
        "0102030405060708090a0b0c0d0e0f00112233445566778899aabbccddeeff00"
    ),
    LOOP_DUEL_INVITE_PUBLIC_KEY=(
        "42a8ada72bbd29ec106cc16aaca1b6d6d572962f7b8de922c295b30b5594bffd"
    ),
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import create_app
from app.nonce_store import MemoryChallengeStore
from app.ton import TonClient


@pytest.fixture(autouse=True)
def reset_settings() -> None:
    get_settings.cache_clear()


class OpenContractsTonClient(TonClient):
    """The real client, with one answer replaced: the contracts are open.

    Quoting now refuses when the contract is paused — and fails closed when it
    cannot ask — so tests need a provider that answers this one question.
    Everything else stays the real implementation, which tests already patch or
    replace where they need to.
    """

    async def get_contract_admin_state(self, mode: str, address: str):
        from app.ton import ContractAdminState

        del mode, address
        return ContractAdminState(
            owner="0:" + "11" * 32,
            treasury="0:" + "11" * 32,
            fee_bps=1000,
            paused=False,
            locked_nano=0,
            extended_controls=True,
        )


@pytest_asyncio.fixture
async def app():
    application = create_app()
    async with application.router.lifespan_context(application):
        application.state.challenge_store = MemoryChallengeStore()
        application.state.ton_client = OpenContractsTonClient(
            application.state.http, get_settings()
        )
        yield application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://loop.test") as http:
        yield http
