from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.duel_v11_preflight import run_preflight
from app.modules.duel.models import DuelOffer, OfferState

PREVIOUS_CONTRACT = "0:" + "22" * 32
TARGET_CONTRACT = "0:" + "11" * 32


def getter_client(locked: int) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/runGetMethod"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "exit_code": 0,
                    "stack": [
                        ["cell", {"bytes": ""}],
                        ["cell", {"bytes": ""}],
                        ["num", "0xfa"],
                        ["num", "0x0"],
                        ["num", hex(locked)],
                    ],
                },
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_duel_v11_preflight_proves_idle_contract_and_projection(app) -> None:
    async with getter_client(0) as http:
        proof = await run_preflight(
            Settings(),
            PREVIOUS_CONTRACT,
            TARGET_CONTRACT,
            http=http,
            engine=app.state.engine,
        )

    assert proof.previous_locked_nano == 0
    assert proof.active_offers == 0
    assert proof.active_duels == 0


async def test_duel_v11_preflight_rejects_locked_contract(app) -> None:
    async with getter_client(1_000_000_000) as http:
        with pytest.raises(RuntimeError, match="still locks"):
            await run_preflight(
                Settings(),
                PREVIOUS_CONTRACT,
                TARGET_CONTRACT,
                http=http,
                engine=app.state.engine,
            )


async def test_duel_v11_preflight_rejects_active_projection(app) -> None:
    async with app.state.session_factory() as db:
        db.add(
            DuelOffer(
                onchain_offer_id=901,
                query_id=901,
                owner_wallet="0:" + "33" * 32,
                network=-3,
                contract_address=PREVIOUS_CONTRACT,
                chance_bps=5_000,
                total_pool_nano=2_000_000_000,
                stake_nano=1_000_000_000,
                opponent_stake_nano=1_000_000_000,
                fee_bps=250,
                payout_nano=1_950_000_000,
                commitment_hex="44" * 32,
                state=OfferState.OPEN.value,
                expires_at=datetime.now(UTC),
            )
        )
        await db.commit()

    async with getter_client(0) as http:
        with pytest.raises(RuntimeError, match="projection is not idle"):
            await run_preflight(
                Settings(),
                PREVIOUS_CONTRACT,
                TARGET_CONTRACT,
                http=http,
                engine=app.state.engine,
            )
