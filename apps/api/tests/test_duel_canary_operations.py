import importlib.util
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


def test_canary_refills_only_wallet_below_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshots: Iterator[dict[str, dict[str, Any]]] = iter(
        [wallets(900_000_000, 2_000_000_000), wallets(2_900_000_000, 2_000_000_000)]
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(RUNNER, "wallet_snapshot", lambda _environment: next(snapshots))
    monkeypatch.setattr(
        RUNNER,
        "run",
        lambda command, _environment, **_kwargs: commands.append(command) or "",
    )

    result = RUNNER.ensure_testnet_funding({}, "loop-canary-a", "loop-canary-b", 1_800_000_000)

    assert result["loop-canary-a"]["balance"] == 2_900_000_000
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
    snapshots: Iterator[dict[str, dict[str, Any]]] = iter(
        [wallets(900_000_000, 2_000_000_000), wallets(900_000_000, 2_000_000_000)]
    )
    monkeypatch.setattr(RUNNER, "wallet_snapshot", lambda _environment: next(snapshots))
    monkeypatch.setattr(RUNNER, "run", lambda *_args, **_kwargs: "")

    with pytest.raises(SystemExit, match="stayed below"):
        RUNNER.ensure_testnet_funding({}, "loop-canary-a", "loop-canary-b", 1_800_000_000)


def test_canary_report_requires_both_wallet_balances() -> None:
    with pytest.raises(ValidationError):
        DuelCanaryReport(
            network=-3,
            contract_address="0:" + "1" * 64,
            duel_id=1,
            settlement_tx_hash="2" * 64,
        )


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
