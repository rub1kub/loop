import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
MAINNET_ADDRESS = "EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt"
TESTNET_ADDRESS = "kQD9vsBIFke3V_cxWQaW8ostPE-3ama0D7Hm_YGac02xo6yP"
MAINNET_ZERO_ADDRESS = "EQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAM9c"


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
    release = {
        "owner": MAINNET_ADDRESS,
        "treasury": MAINNET_ADDRESS,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 2_000_000_000,
        },
    }
    manifest = {
        "contract": "DuelEscrow",
        "network": "mainnet",
        "source_commit": commit,
        "configuration": {
            "owner": MAINNET_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "network_id": -239,
            "paused": True,
            "locked_nano": 0,
            "max_pool_nano": 2_000_000_000,
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
    release = {
        "owner": MAINNET_ADDRESS,
        "treasury": MAINNET_ADDRESS,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 2_000_000_000,
        },
    }
    manifest = {
        "contract": "DuelEscrow",
        "network": "mainnet",
        "source_commit": commit,
        "configuration": {
            "owner": MAINNET_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "network_id": -239,
            "paused": True,
            "locked_nano": 0,
            "max_pool_nano": 2_000_000_000,
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


def test_post_deploy_requires_paused_drained_contract(tmp_path: Path) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    commit = "a" * 40
    release = {
        "owner": MAINNET_ADDRESS,
        "treasury": MAINNET_ADDRESS,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 2_000_000_000,
        },
    }
    manifest = {
        "contract": "BankQueue",
        "network": "mainnet",
        "source_commit": commit,
        "configuration": {
            "owner": MAINNET_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "paused": False,
            "locked_nano": 0,
            "completed_positions": 0,
            "head_queue_index": 0,
            "next_queue_index": 0,
            "principal_limit_nano": 5_000_000_000,
        },
        "verified_smoke": {"transaction": "proof"},
        "source_verification": {
            "verified": True,
            "url": "https://verifier.ton.org/proof",
        },
    }
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.ReadinessError, match="must remain paused"):
        readiness.validate_manifest(
            path,
            contract="BankQueue",
            release=release,
            audited_commit=commit,
        )
    manifest["configuration"]["paused"] = True
    manifest["configuration"]["locked_nano"] = 1
    path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.ReadinessError, match="locked value"):
        readiness.validate_manifest(
            path,
            contract="BankQueue",
            release=release,
            audited_commit=commit,
        )


def test_bank_mainnet_smoke_must_use_a_distinct_shadow_contract(
    tmp_path: Path,
) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    commit = "a" * 40
    release = {
        "owner": MAINNET_ADDRESS,
        "treasury": MAINNET_ADDRESS,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 2_000_000_000,
        },
    }
    manifest = {
        "contract": "BankQueue",
        "address": MAINNET_ADDRESS,
        "network": "mainnet",
        "source_commit": commit,
        "configuration": {
            "owner": MAINNET_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "paused": True,
            "locked_nano": 0,
            "completed_positions": 0,
            "head_queue_index": 0,
            "next_queue_index": 0,
            "principal_limit_nano": 5_000_000_000,
        },
        "verified_smoke": {
            "contract_address": MAINNET_ZERO_ADDRESS,
            "treasury": MAINNET_ADDRESS,
            "first_wallet": MAINNET_ADDRESS,
            "second_wallet": MAINNET_ZERO_ADDRESS,
            "position_id": 1,
            "principal_nano": 1,
            "first_transaction": "first",
            "first_transaction_lt": 1,
            "first_masterchain_seqno": 1,
            "funding_position_id": 2,
            "funding_principal_nano": 1,
            "funding_transaction": "second",
            "funding_transaction_lt": 2,
            "funding_masterchain_seqno": 2,
            "payout_nano": 1,
        },
        "source_verification": {
            "verified": True,
            "url": "https://verifier.ton.org/proof",
        },
    }
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(manifest))
    readiness.validate_manifest(
        path,
        contract="BankQueue",
        release=release,
        audited_commit=commit,
    )
    manifest["verified_smoke"]["contract_address"] = MAINNET_ADDRESS
    path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.ReadinessError, match="separate shadow"):
        readiness.validate_manifest(
            path,
            contract="BankQueue",
            release=release,
            audited_commit=commit,
        )


def test_post_deploy_runtime_must_match_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    commit = "a" * 40
    report_hash = "b" * 64
    release = {
        "external_audit": {"report_sha256": report_hash},
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 2_000_000_000,
        },
    }
    values = {
        "LOOP_TON_NETWORK_ID": "-239",
        "LOOP_MAINNET_ENABLED": "true",
        "LOOP_REQUIRE_DUEL_CANARY": "true",
        "LOOP_TONCENTER_URL": "https://toncenter.com",
        "LOOP_MAINNET_RELEASE_COMMIT": commit,
        "LOOP_MAINNET_AUDITED_COMMIT": commit,
        "LOOP_MAINNET_AUDIT_REPORT_SHA256": report_hash,
        "LOOP_BANK_MAX_PRINCIPAL_NANO": "5000000000",
        "LOOP_MAX_POOL_NANO": "2000000000",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    readiness.validate_runtime_environment(release, commit)
    monkeypatch.setenv("LOOP_MAX_POOL_NANO", "10000000000")
    with pytest.raises(readiness.ReadinessError, match="does not match"):
        readiness.validate_runtime_environment(release, commit)
