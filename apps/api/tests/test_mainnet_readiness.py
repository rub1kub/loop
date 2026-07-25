import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAINNET_ADDRESS = "EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt"
TESTNET_ADDRESS = "kQD9vsBIFke3V_cxWQaW8ostPE-3ama0D7Hm_YGac02xo6yP"


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_contract_balance_must_cover_locked_value_and_reserve() -> None:
    verifier = load_script("verify-contracts.py")
    verifier.validate_live_balance(
        "DuelEscrow",
        live_balance=1_000,
        live_locked=700,
        min_reserve=300,
    )
    with pytest.raises(ValueError, match="does not cover"):
        verifier.validate_live_balance(
            "DuelEscrow",
            live_balance=999,
            live_locked=700,
            min_reserve=300,
        )


def test_mainnet_gate_rejects_test_only_addresses() -> None:
    readiness = load_script("check-mainnet-readiness.py")
    readiness.require_mainnet_address(MAINNET_ADDRESS, "owner")
    with pytest.raises(readiness.ReadinessError, match="mainnet basechain"):
        readiness.require_mainnet_address(TESTNET_ADDRESS, "owner")


def test_post_deploy_manifest_requires_smoke_and_source_proof(tmp_path: Path) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    commit = "a" * 40
    release = {"owner": MAINNET_ADDRESS, "treasury": MAINNET_ADDRESS}
    manifest = {
        "contract": "DuelEscrow",
        "network": "mainnet",
        "source_commit": commit,
        "configuration": {
            "owner": MAINNET_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "network_id": -239,
        },
        "verified_smoke": {"settlement_transaction": "proof"},
        "verified_canary": {
            "first_wallet": MAINNET_ADDRESS,
            "second_wallet": "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c",
            "duel_id": 1,
            "query_id": 1,
            "settlement_transaction": "proof",
            "settlement_transaction_lt": 1,
            "masterchain_seqno": 1,
        },
        "source_verification": {
            "verified": True,
            "url": "https://verifier.ton.org/proof",
        },
    }
    path = tmp_path / "duel.json"
    path.write_text(json.dumps(manifest))
    readiness.validate_manifest(
        path,
        contract="DuelEscrow",
        release=release,
        audited_commit=commit,
    )
    del manifest["verified_smoke"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.ReadinessError, match="smoke proof"):
        readiness.validate_manifest(
            path,
            contract="DuelEscrow",
            release=release,
            audited_commit=commit,
        )


def test_post_deploy_manifest_requires_two_distinct_canary_wallets(
    tmp_path: Path,
) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    commit = "a" * 40
    release = {"owner": MAINNET_ADDRESS, "treasury": MAINNET_ADDRESS}
    manifest = {
        "contract": "DuelEscrow",
        "network": "mainnet",
        "source_commit": commit,
        "configuration": {
            "owner": MAINNET_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "network_id": -239,
        },
        "verified_smoke": {"transaction": "proof"},
        "verified_canary": {
            "first_wallet": MAINNET_ADDRESS,
            "second_wallet": MAINNET_ADDRESS,
            "duel_id": 1,
            "settlement_transaction": "proof",
            "settlement_transaction_lt": 1,
            "masterchain_seqno": 1,
        },
        "source_verification": {
            "verified": True,
            "url": "https://verifier.ton.org/proof",
        },
    }
    path = tmp_path / "duel.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.ReadinessError, match="must be distinct"):
        readiness.validate_manifest(
            path,
            contract="DuelEscrow",
            release=release,
            audited_commit=commit,
        )
