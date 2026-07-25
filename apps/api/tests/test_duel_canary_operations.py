import importlib.util
import io
import json
import subprocess
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas import DuelCanaryReport

ROOT = Path(__file__).resolve().parents[3]


def load_script(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_script("loop_run_duel_canary", "run-duel-canary.py")
HEALTH = load_script("loop_check_duel_health", "check-duel-health.py")


def wallets(first_balance: int, second_balance: int) -> dict[str, dict[str, Any]]:
    return {
        "loop-canary-a": {"address": "a", "balance": first_balance},
        "loop-canary-b": {"address": "b", "balance": second_balance},
    }


def test_canary_can_parse_acton_proof_from_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(
        args=["acton"],
        returncode=0,
        stdout="",
        stderr="DUEL_CANARY_PROOF duel_id=42 settlement_hash=ab\n",
    )
    monkeypatch.setattr(RUNNER.subprocess, "run", lambda *_args, **_kwargs: completed)

    output = RUNNER.run(["acton"], {}, echo=False, include_stderr=True)

    assert RUNNER.PROOF_PATTERN.search(output)


def mainnet_wallets(first_balance: int, second_balance: int) -> dict[str, dict[str, Any]]:
    return {
        "loop-mainnet-canary-a": {"address": "a", "balance": first_balance},
        "loop-mainnet-canary-b": {"address": "b", "balance": second_balance},
    }


def test_canary_refills_only_wallet_below_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots: Iterator[dict[str, dict[str, Any]]] = iter(
        [
            wallets(900_000_000, 2_000_000_000),
            wallets(900_000_000, 2_000_000_000),
            wallets(2_900_000_000, 2_000_000_000),
        ]
    )
    commands: list[list[str]] = []
    sleeps: list[int] = []
    monkeypatch.setattr(RUNNER, "wallet_snapshot", lambda _environment: next(snapshots))
    monkeypatch.setattr(
        RUNNER,
        "run",
        lambda command, _environment, **_kwargs: commands.append(command) or "",
    )
    monkeypatch.setattr(RUNNER.time, "sleep", sleeps.append)

    result = RUNNER.ensure_testnet_funding({}, "loop-canary-a", "loop-canary-b", 1_800_000_000)

    assert result["loop-canary-a"]["balance"] == 2_900_000_000
    assert sleeps == [RUNNER.FUNDING_POLL_INTERVAL_SECONDS]
    assert commands == [
        [
            "acton",
            "wallet",
            "airdrop",
            "loop-canary-a",
            "--net",
            "testnet",
            "--json",
        ]
    ]


def test_canary_fails_closed_when_airdrop_stays_below_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        RUNNER,
        "wallet_snapshot",
        lambda _environment: wallets(900_000_000, 2_000_000_000),
    )
    monkeypatch.setattr(RUNNER, "run", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(RUNNER.time, "sleep", lambda _seconds: None)

    with pytest.raises(SystemExit, match="stayed below"):
        RUNNER.ensure_testnet_funding({}, "loop-canary-a", "loop-canary-b", 1_800_000_000)


def test_mainnet_canary_never_requests_an_airdrop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        RUNNER,
        "wallet_snapshot",
        lambda _environment: mainnet_wallets(1_000_000_000, 2_000_000_000),
    )
    with pytest.raises(SystemExit, match="below the configured safety floor"):
        RUNNER.require_mainnet_funding(
            {},
            "loop-mainnet-canary-a",
            "loop-mainnet-canary-b",
            1_800_000_000,
        )


def test_canary_formats_manifest_ready_finality_evidence() -> None:
    evidence = RUNNER.canary_evidence(
        {
            "status": "verified",
            "duel_id": 42,
            "settlement_transaction": "ab" * 32,
            "settlement_transaction_lt": 123,
            "masterchain_seqno": 456,
        },
        mainnet_wallets(2_000_000_000, 2_000_000_000),
        "loop-mainnet-canary-a",
        "loop-mainnet-canary-b",
    )
    assert evidence == {
        "first_wallet": "a",
        "second_wallet": "b",
        "duel_id": 42,
        "query_id": 42,
        "settlement_transaction": "ab" * 32,
        "settlement_transaction_lt": 123,
        "masterchain_seqno": 456,
    }


def test_canary_reads_finalized_successful_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "transactions": [
            {
                "lt": "123",
                "mc_block_seqno": 456,
                "emulated": False,
                "description": {
                    "aborted": False,
                    "compute_ph": {"success": True},
                    "action": {"success": True},
                },
            }
        ]
    }
    monkeypatch.setattr(
        RUNNER.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(json.dumps(payload).encode()),
    )
    assert RUNNER.fetch_settlement_finality("mainnet", "ab" * 32, 42) == {
        "status": "verified",
        "duel_id": 42,
        "settlement_transaction": "ab" * 32,
        "settlement_transaction_lt": 123,
        "masterchain_seqno": 456,
    }


def test_canary_retries_temporary_finality_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "transactions": [
            {
                "lt": "123",
                "mc_block_seqno": 456,
                "emulated": False,
                "description": {
                    "aborted": False,
                    "compute_ph": {"success": True},
                    "action": {"success": True},
                },
            }
        ]
    }
    responses: Iterator[Any] = iter(
        [
            RUNNER.urllib.error.URLError("temporary failure"),
            io.BytesIO(json.dumps(payload).encode()),
        ]
    )

    def urlopen(*_args: Any, **_kwargs: Any) -> Any:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    sleeps: list[int] = []
    monkeypatch.setattr(RUNNER.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(RUNNER.time, "sleep", sleeps.append)

    assert RUNNER.fetch_settlement_finality("testnet", "ab" * 32, 42)["status"] == "verified"
    assert sleeps == [RUNNER.FINALITY_POLL_INTERVAL_SECONDS]


def test_canary_retries_without_rejected_provider_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "transactions": [
            {
                "lt": "123",
                "mc_block_seqno": 456,
                "emulated": False,
                "description": {
                    "aborted": False,
                    "compute_ph": {"success": True},
                    "action": {"success": True},
                },
            }
        ]
    }
    requests: list[Any] = []

    def urlopen(request: Any, **_kwargs: Any) -> Any:
        requests.append(request)
        if len(requests) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "rejected key",
                {},
                None,
            )
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setenv("LOOP_TONCENTER_API_KEY", "rejected")
    monkeypatch.setattr(RUNNER.urllib.request, "urlopen", urlopen)

    assert RUNNER.fetch_settlement_finality("testnet", "ab" * 32, 42)["status"] == "verified"
    assert requests[0].get_header("X-api-key") == "rejected"
    assert requests[1].get_header("X-api-key") is None


def test_canary_report_requires_both_wallet_balances() -> None:
    with pytest.raises(ValidationError):
        DuelCanaryReport(
            network=-3,
            contract_address="0:" + "1" * 64,
            duel_id=1,
            settlement_tx_hash="2" * 64,
        )


@pytest.mark.asyncio
async def test_canary_report_uses_api_namespace_and_requires_auth(client: Any) -> None:
    report = {
        "network": -3,
        "contract_address": "0:" + "1" * 64,
        "duel_id": 1,
        "settlement_tx_hash": "2" * 64,
        "first_wallet_balance_nano": 2_000_000_000,
        "second_wallet_balance_nano": 2_000_000_000,
    }

    assert (await client.post("/api/internal/duel-canary", json=report)).status_code == 401
    assert (await client.post("/internal/duel-canary", json=report)).status_code == 404


def test_duel_health_rejects_low_canary_balance() -> None:
    metrics = {name: 0.0 for name in HEALTH.REQUIRED_METRICS}
    metrics.update(
        {
            "loop_duel_worker_healthy": 1.0,
            "loop_duel_canary_success": 1.0,
            "loop_duel_canary_age_seconds": 60.0,
            "loop_duel_canary_min_wallet_balance_nano": 999_999_999.0,
        }
    )

    with pytest.raises(HEALTH.DuelHealthError, match="below the balance floor"):
        HEALTH.evaluate_metrics(
            metrics,
            require_canary=True,
            canary_max_age=7_200,
            canary_min_balance=1_000_000_000,
        )
