import hashlib
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


def self_reviewed_release(**overrides: object) -> dict[str, object]:
    disclosure = ROOT / "docs" / "no-audit-disclosure.md"
    digest = hashlib.sha256(disclosure.read_bytes()).hexdigest()
    block = {
        "acknowledgement": "NO INDEPENDENT AUDIT - OWNER ACCEPTS THE RISK",
        "disclosure_path": "docs/no-audit-disclosure.md",
        "disclosure_sha256": digest,
        "adversarial_review_path": "docs/reviews/internal-review-2026-07-26.md",
        "bounty_policy_path": "docs/security-bounty.md",
        "bounty_contact": "https://t.me/rub1kub",
        "bounty_max_reward_nano": 500_000_000_000,
    }
    block.update(overrides)
    return {"self_reviewed": block}


def test_unreviewed_release_is_accepted_only_with_every_compensating_control() -> None:
    readiness = load_script("check-mainnet-readiness.py")
    readiness.validate_assurance(self_reviewed_release())

    # Declaring both would let a weak path ride on a strong one's name.
    with pytest.raises(readiness.ReadinessError, match="either an external audit"):
        readiness.validate_assurance(
            {**self_reviewed_release(), "external_audit": {"provider": "x"}}
        )
    # Shipping unreviewed must be a deliberate, exact statement.
    with pytest.raises(readiness.ReadinessError, match="acknowledgement"):
        readiness.validate_assurance(self_reviewed_release(acknowledgement="probably fine"))
    # The disclosure the release points at must be the one users can read.
    with pytest.raises(readiness.ReadinessError, match="SHA-256 mismatch"):
        readiness.validate_assurance(self_reviewed_release(disclosure_sha256="ab" * 32))
    # Paying for bugs replaces paying for a search, so it cannot be decorative.
    with pytest.raises(readiness.ReadinessError, match="bug bounty contact"):
        readiness.validate_assurance(self_reviewed_release(bounty_contact="  "))
    with pytest.raises(readiness.ReadinessError, match="maximum reward"):
        readiness.validate_assurance(self_reviewed_release(bounty_max_reward_nano=0))
    with pytest.raises(readiness.ReadinessError, match="external_audit or self_reviewed"):
        readiness.validate_assurance({})


def test_unreviewed_release_caps_value_below_a_reviewed_one(monkeypatch) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    # Pin the release commit so the gate does not consult the live worktree.
    monkeypatch.setenv("LOOP_RELEASE_COMMIT", "a" * 40)
    release_dir = ROOT / "deployments" / "mainnet"
    base = {
        **self_reviewed_release(),
        "audited_commit": "a" * 40,
        "owner": MAINNET_ADDRESS,
        "treasury": MAINNET_ADDRESS,
        "duel_invite_signer_public_key": "b" * 64,
    }
    # A reviewed release may carry 10 GRAM; an unreviewed one is held at 5,
    # raised from 1 over the opening evening by the owner. The cap is the
    # compensating control rather than a formality, so the gate still has to bite.
    over_cap = {
        **base,
        "initial_limits": {
            "bank_max_principal_nano": 9_000_000_000,
            "duel_max_pool_nano": 1_000_000_000,
        },
    }
    with pytest.raises(readiness.ReadinessError, match="5 GRAM launch cap"):
        readiness.validate_release_evidence(over_cap, release_dir / "release.json")

    at_cap = {
        **base,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 1_000_000_000,
        },
    }
    assert readiness.validate_release_evidence(at_cap, release_dir / "release.json") == "a" * 40

    just_over = {
        **base,
        "initial_limits": {
            "bank_max_principal_nano": 6_000_000_000,
            "duel_max_pool_nano": 1_000_000_000,
        },
    }
    with pytest.raises(readiness.ReadinessError, match="5 GRAM launch cap"):
        readiness.validate_release_evidence(just_over, release_dir / "release.json")

    # The cap is per participant, and a DUEL pool holds two of them: measured
    # against the pool it made DUEL twice as strict as BANK for no reason.
    two_players = {
        **base,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 10_000_000_000,
        },
    }
    assert (
        readiness.validate_release_evidence(two_players, release_dir / "release.json") == "a" * 40
    )

    three_players = {
        **base,
        "initial_limits": {
            "bank_max_principal_nano": 5_000_000_000,
            "duel_max_pool_nano": 11_000_000_000,
        },
    }
    with pytest.raises(readiness.ReadinessError, match="5 GRAM launch cap"):
        readiness.validate_release_evidence(three_players, release_dir / "release.json")

    within_cap = {
        **base,
        "initial_limits": {
            "bank_max_principal_nano": 1_000_000_000,
            "duel_max_pool_nano": 1_000_000_000,
        },
    }
    assert readiness.validate_release_evidence(within_cap, release_dir / "release.json") == "a" * 40


def test_attestation_may_sit_one_commit_above_the_tree_it_attests(monkeypatch) -> None:
    readiness = load_script("check-mainnet-readiness.py")
    release_dir = ROOT / "deployments" / "mainnet"
    release = {
        **self_reviewed_release(),
        "audited_commit": "a" * 40,
        "owner": MAINNET_ADDRESS,
        "treasury": MAINNET_ADDRESS,
        "duel_invite_signer_public_key": "b" * 64,
        "initial_limits": {
            "bank_max_principal_nano": 1_000_000_000,
            "duel_max_pool_nano": 1_000_000_000,
        },
    }
    # The deployed commit is the one that carries the attestation, so it can
    # never equal the commit being attested. Demanding equality made every
    # mainnet activation impossible; what the gate returns must stay the
    # audited commit, since the runtime environment is checked against it.
    monkeypatch.setenv("LOOP_RELEASE_COMMIT", "c" * 40)
    assert (
        readiness.validate_release_evidence(release, release_dir / "release.json")
        == "a" * 40
    )
    monkeypatch.setenv("LOOP_RELEASE_COMMIT", "not-a-commit")
    with pytest.raises(readiness.ReadinessError, match="LOOP_RELEASE_COMMIT"):
        readiness.validate_release_evidence(release, release_dir / "release.json")
    monkeypatch.setenv("LOOP_RELEASE_COMMIT", "c" * 40)
    with pytest.raises(readiness.ReadinessError, match="audited_commit"):
        readiness.validate_release_evidence(
            {**release, "audited_commit": "short"}, release_dir / "release.json"
        )


def test_a_recorded_chain_reading_lets_the_ceiling_follow_the_ladder(tmp_path: Path) -> None:
    # The configuration block is frozen at activation, when the ladder stood on
    # its first rung. Judged against it, the application ceiling could never
    # rise however far the contract actually climbed. A recorded live reading
    # is what the ceiling is measured against — and it has to carry a
    # masterchain seqno, so the claim can be checked rather than believed.
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
            "principal_limit_nano": 1_000_000_000,
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
        "source_verification": {"verified": True, "url": "https://verifier.ton.org/proof"},
    }
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(manifest))

    # Without a reading, the frozen rung still governs and 3 GRAM is refused.
    with pytest.raises(readiness.ReadinessError, match="exceeds the contract limit"):
        readiness.validate_manifest(
            path, contract="BankQueue", release=release, audited_commit=commit
        )

    # A reading without provenance is not evidence.
    manifest["observed_state"] = {"principal_limit_nano": 7_000_000_000}
    path.write_text(json.dumps(manifest))
    with pytest.raises(readiness.ReadinessError, match="masterchain seqno"):
        readiness.validate_manifest(
            path, contract="BankQueue", release=release, audited_commit=commit
        )

    manifest["observed_state"] = {
        "principal_limit_nano": 7_000_000_000,
        "masterchain_seqno": 84188447,
        "completed_positions": 38,
    }
    path.write_text(json.dumps(manifest))
    readiness.validate_manifest(
        path, contract="BankQueue", release=release, audited_commit=commit
    )
