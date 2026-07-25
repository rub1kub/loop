from typing import Any

import pytest

from app.config import Settings
from app.network_switch_preflight import run_preflight
from app.ton import ContractAdminState


class FakeTonClient:
    def __init__(self, *, paused: bool = True, locked_nano: int = 0) -> None:
        self.paused = paused
        self.locked_nano = locked_nano

    async def get_contract_admin_state(
        self, mode: str, address: str
    ) -> ContractAdminState:
        assert mode in {"bank", "duel"}
        assert address
        return ContractAdminState(
            owner="0:" + "11" * 32,
            treasury="0:" + "22" * 32,
            fee_bps=100 if mode == "bank" else 250,
            paused=self.paused,
            locked_nano=self.locked_nano,
            extended_controls=True,
        )


@pytest.mark.asyncio
async def test_network_switch_requires_paused_drained_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def idle_counts(_engine: Any, network: int) -> tuple[int, int, int, int]:
        assert network == -3
        return 0, 0, 0, 0

    monkeypatch.setattr(
        "app.network_switch_preflight.active_projection_counts", idle_counts
    )
    settings = Settings(
        _env_file=None,
        app_env="test",
        ton_network_id=-3,
        bank_contract_address="0:" + "12" * 32,
        duel_contract_address="0:" + "13" * 32,
    )
    proof = await run_preflight(
        settings,
        -239,
        ton_client=FakeTonClient(),  # type: ignore[arg-type]
        engine=object(),  # type: ignore[arg-type]
    )
    assert proof.source_network == -3
    assert proof.target_network == -239

    with pytest.raises(RuntimeError, match="must be paused"):
        await run_preflight(
            settings,
            -239,
            ton_client=FakeTonClient(paused=False),  # type: ignore[arg-type]
            engine=object(),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_network_switch_rejects_live_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def active_counts(_engine: Any, _network: int) -> tuple[int, int, int, int]:
        return 1, 0, 0, 0

    monkeypatch.setattr(
        "app.network_switch_preflight.active_projection_counts", active_counts
    )
    settings = Settings(
        _env_file=None,
        app_env="test",
        ton_network_id=-3,
        bank_contract_address="0:" + "12" * 32,
        duel_contract_address="0:" + "13" * 32,
    )
    with pytest.raises(RuntimeError, match="not drained"):
        await run_preflight(
            settings,
            -239,
            ton_client=FakeTonClient(locked_nano=1),  # type: ignore[arg-type]
            engine=object(),  # type: ignore[arg-type]
        )
