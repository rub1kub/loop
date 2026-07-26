#!/usr/bin/env python3
"""Fail-closed release evidence gate for LOOP mainnet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from tonsdk.utils import Address  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_FILE = ROOT / "deployments" / "mainnet" / "release.json"
COMMIT = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)
HASH = re.compile(r"[0-9a-f]{64}", re.IGNORECASE)
INITIAL_VALUE_CAP_NANO = 10_000_000_000
UNREVIEWED_VALUE_CAP_NANO = 1_000_000_000
MIN_SOAK_DAYS = 30


class ReadinessError(RuntimeError):
    """Raised when a mandatory mainnet release gate is missing."""


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise ReadinessError(f"missing release evidence: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReadinessError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"{path} must contain a JSON object")
    return value


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ReadinessError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def require_mainnet_address(value: Any, name: str) -> str:
    try:
        address = Address(str(value))
    except Exception as exc:
        raise ReadinessError(f"{name} must be a valid TON address") from exc
    if not address.is_user_friendly or address.is_test_only or address.wc != 0:
        raise ReadinessError(f"{name} must be a mainnet basechain friendly address")
    return address.to_string(
        is_user_friendly=False,
        is_url_safe=True,
        is_bounceable=True,
        is_test_only=False,
    ).lower()



def validate_external_audit(audit: dict[str, Any]) -> None:
    if not str(audit.get("provider", "")).strip():
        raise ReadinessError("external audit provider is required")
    try:
        completed_at = date.fromisoformat(str(audit.get("completed_at", "")))
    except ValueError as exc:
        raise ReadinessError("external audit completion date is invalid") from exc
    if completed_at > date.today():
        raise ReadinessError("external audit completion date cannot be in the future")
    require_pinned_document(
        audit.get("report_path"),
        audit.get("report_sha256"),
        ROOT / "docs" / "audits",
        "audit report",
    )


def validate_self_reviewed(block: dict[str, Any]) -> None:
    """Gate for a release that ships without independent review.

    An audit buys an outside opinion, and nothing here reproduces that. What
    this path can enforce is that the absence is deliberate, disclosed in a
    file the release is pinned to, compensated by a low value cap, backed by a
    standing offer to pay for bugs, and preceded by real time on testnet.
    """
    acknowledgement = str(block.get("acknowledgement", "")).strip()
    if acknowledgement != "NO INDEPENDENT AUDIT - OWNER ACCEPTS THE RISK":
        raise ReadinessError(
            "an unreviewed release requires the exact owner acknowledgement string"
        )
    require_pinned_document(
        block.get("disclosure_path"),
        block.get("disclosure_sha256"),
        ROOT / "docs",
        "public disclosure",
    )
    for name in ("adversarial_review_path", "bounty_policy_path"):
        target = ROOT / str(block.get(name, ""))
        try:
            target.relative_to(ROOT / "docs")
        except ValueError as exc:
            raise ReadinessError(f"{name} must live under docs/") from exc
        if not target.is_file():
            raise ReadinessError(f"{name} is missing: {target}")
    contact = str(block.get("bounty_contact", "")).strip()
    if not contact:
        raise ReadinessError("an unreviewed release must publish a bug bounty contact")
    reward = block.get("bounty_max_reward_nano")
    if not isinstance(reward, int) or reward <= 0:
        raise ReadinessError("the bug bounty must state a real maximum reward")
    try:
        soak_started = date.fromisoformat(str(block.get("testnet_soak_started", "")))
    except ValueError as exc:
        raise ReadinessError("testnet soak start date is invalid") from exc
    soaked = (date.today() - soak_started).days
    if soaked < MIN_SOAK_DAYS:
        raise ReadinessError(
            f"unreviewed release needs {MIN_SOAK_DAYS} days on testnet, has {soaked}"
        )


def require_pinned_document(
    relative_path: Any,
    expected_hash: Any,
    root: Path,
    label: str,
) -> None:
    digest = str(expected_hash or "")
    if HASH.fullmatch(digest) is None or set(digest) == {"0"}:
        raise ReadinessError(f"{label} SHA-256 is required")
    target = ROOT / str(relative_path or "")
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ReadinessError(f"{label} must be stored under {root.name}") from exc
    if not target.is_file():
        raise ReadinessError(f"{label} is missing: {target}")
    if hashlib.sha256(target.read_bytes()).hexdigest().lower() != digest.lower():
        raise ReadinessError(f"{label} SHA-256 mismatch")


def validate_assurance(release: dict[str, Any]) -> None:
    audit = release.get("external_audit")
    self_reviewed = release.get("self_reviewed")
    if isinstance(audit, dict) and isinstance(self_reviewed, dict):
        raise ReadinessError("declare either an external audit or a self-reviewed release")
    if isinstance(audit, dict):
        validate_external_audit(audit)
        return
    if isinstance(self_reviewed, dict):
        validate_self_reviewed(self_reviewed)
        return
    raise ReadinessError("release must declare external_audit or self_reviewed assurance")


def validate_release_evidence(release: dict[str, Any], release_file: Path) -> str:
    release_commit = os.getenv("LOOP_RELEASE_COMMIT", "")
    if release_commit:
        if COMMIT.fullmatch(release_commit) is None:
            raise ReadinessError("LOOP_RELEASE_COMMIT must be a 40-character Git commit")
        head = release_commit
    else:
        head = git("rev-parse", "HEAD")
        if git("status", "--porcelain"):
            raise ReadinessError("mainnet release requires a clean worktree")
        if git("branch", "--show-current") != "main":
            raise ReadinessError("mainnet release must be cut from main")
    audited_commit = str(release.get("audited_commit", ""))
    if COMMIT.fullmatch(audited_commit) is None or audited_commit.lower() != head.lower():
        raise ReadinessError("HEAD must equal the externally audited commit")

    validate_assurance(release)

    require_mainnet_address(release.get("owner"), "owner")
    require_mainnet_address(release.get("treasury"), "treasury")
    public_key = str(release.get("duel_invite_signer_public_key", ""))
    if HASH.fullmatch(public_key) is None or set(public_key) == {"0"}:
        raise ReadinessError("DUEL invite signer public key is invalid")
    limits = release.get("initial_limits")
    if not isinstance(limits, dict):
        raise ReadinessError("initial mainnet limits are required")
    # Without an independent review the only honest lever left is exposure, so
    # the unreviewed path caps a position at a tenth of what a reviewed one may
    # carry. This is not a formality: it is the whole compensating control.
    cap = (
        INITIAL_VALUE_CAP_NANO
        if isinstance(release.get("external_audit"), dict)
        else UNREVIEWED_VALUE_CAP_NANO
    )
    for key in ("bank_max_principal_nano", "duel_max_pool_nano"):
        value = limits.get(key)
        if not isinstance(value, int) or value <= 0 or value > cap:
            raise ReadinessError(
                f"{key} must be within the {cap // 1_000_000_000} GRAM launch cap"
            )
    if release_file.parent != ROOT / "deployments" / "mainnet":
        raise ReadinessError("release evidence must live under deployments/mainnet")
    return head


def require_environment_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ReadinessError(f"{name} is required for the mainnet application release")
    return value


def validate_runtime_environment(
    release: dict[str, Any],
    audited_commit: str,
) -> None:
    if require_environment_value("LOOP_TON_NETWORK_ID") != "-239":
        raise ReadinessError("runtime TON network must be mainnet")
    if require_environment_value("LOOP_MAINNET_ENABLED").lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise ReadinessError("runtime mainnet flag must be enabled")
    if require_environment_value("LOOP_REQUIRE_DUEL_CANARY").lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise ReadinessError("runtime two-wallet DUEL canary must be required")
    if "testnet" in require_environment_value("LOOP_TONCENTER_URL").lower():
        raise ReadinessError("runtime TON provider must not target testnet")

    assurance = release.get("external_audit") or release["self_reviewed"]
    expected_report_hash = str(
        assurance.get("report_sha256") or assurance.get("disclosure_sha256")
    ).lower()
    expected_values = {
        "LOOP_MAINNET_RELEASE_COMMIT": audited_commit.lower(),
        "LOOP_MAINNET_AUDITED_COMMIT": audited_commit.lower(),
        "LOOP_MAINNET_AUDIT_REPORT_SHA256": expected_report_hash,
        "LOOP_BANK_MAX_PRINCIPAL_NANO": str(
            release["initial_limits"]["bank_max_principal_nano"]
        ),
        "LOOP_MAX_POOL_NANO": str(release["initial_limits"]["duel_max_pool_nano"]),
    }
    for name, expected in expected_values.items():
        if require_environment_value(name).lower() != expected:
            raise ReadinessError(f"{name} does not match the audited release")


def validate_manifest(
    path: Path,
    *,
    contract: str,
    release: dict[str, Any],
    audited_commit: str,
) -> None:
    manifest = read_object(path)
    if manifest.get("contract") != contract or manifest.get("network") != "mainnet":
        raise ReadinessError(f"{contract}: wrong contract or network in manifest")
    if str(manifest.get("source_commit", "")).lower() != audited_commit.lower():
        raise ReadinessError(f"{contract}: deployment is not from the audited commit")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, dict):
        raise ReadinessError(f"{contract}: configuration is missing")
    if require_mainnet_address(configuration.get("owner"), f"{contract} owner") != (
        require_mainnet_address(release.get("owner"), "release owner")
    ):
        raise ReadinessError(f"{contract}: owner mismatch")
    if require_mainnet_address(configuration.get("treasury"), f"{contract} treasury") != (
        require_mainnet_address(release.get("treasury"), "release treasury")
    ):
        raise ReadinessError(f"{contract}: treasury mismatch")
    if contract == "DuelEscrow" and int(configuration.get("network_id", 0)) != -239:
        raise ReadinessError("DuelEscrow: mainnet domain is missing")
    if configuration.get("paused") is not True:
        raise ReadinessError(f"{contract}: contract must remain paused at application activation")
    if int(configuration.get("locked_nano", -1)) != 0:
        raise ReadinessError(f"{contract}: locked value must be zero at application activation")
    limits = release["initial_limits"]
    if contract == "BankQueue" and int(configuration.get("principal_limit_nano", 0)) < int(
        limits["bank_max_principal_nano"]
    ):
        raise ReadinessError("BankQueue: application limit exceeds the contract limit")
    if contract == "BankQueue" and any(
        int(configuration.get(name, -1)) != 0
        for name in (
            "completed_positions",
            "head_queue_index",
            "next_queue_index",
        )
    ):
        raise ReadinessError("BankQueue: production queue must start pristine")
    if contract == "DuelEscrow" and int(configuration.get("max_pool_nano", 0)) < int(
        limits["duel_max_pool_nano"]
    ):
        raise ReadinessError("DuelEscrow: application limit exceeds the contract limit")
    smoke = manifest.get("verified_smoke")
    if not isinstance(smoke, dict):
        raise ReadinessError(f"{contract}: finalized smoke proof is missing")
    if contract == "BankQueue":
        production_address = require_mainnet_address(
            manifest.get("address"), "BANK production contract"
        )
        shadow_address = require_mainnet_address(
            smoke.get("contract_address"), "BANK shadow smoke contract"
        )
        if shadow_address == production_address:
            raise ReadinessError(
                "BankQueue: payout smoke must run on a separate shadow contract"
            )
        first_wallet = require_mainnet_address(
            smoke.get("first_wallet"), "BANK smoke first wallet"
        )
        second_wallet = require_mainnet_address(
            smoke.get("second_wallet"), "BANK smoke second wallet"
        )
        require_mainnet_address(smoke.get("treasury"), "BANK smoke treasury")
        if first_wallet == second_wallet:
            raise ReadinessError("BankQueue: smoke wallets must be distinct")
        required_positive_integers = (
            "position_id",
            "first_transaction_lt",
            "first_masterchain_seqno",
            "funding_position_id",
            "funding_transaction_lt",
            "funding_masterchain_seqno",
            "principal_nano",
            "funding_principal_nano",
            "payout_nano",
        )
        if (
            not str(smoke.get("first_transaction", "")).strip()
            or not str(smoke.get("funding_transaction", "")).strip()
            or any(
                not isinstance(smoke.get(name), int) or int(smoke[name]) <= 0
                for name in required_positive_integers
            )
        ):
            raise ReadinessError("BankQueue: shadow smoke finality evidence is invalid")
    elif contract == "DuelEscrow":
        canary = manifest.get("verified_canary")
        if not isinstance(canary, dict):
            raise ReadinessError("DuelEscrow: finalized two-wallet canary proof is missing")
        first_wallet = require_mainnet_address(
            canary.get("first_wallet"), "DUEL canary first wallet"
        )
        second_wallet = require_mainnet_address(
            canary.get("second_wallet"), "DUEL canary second wallet"
        )
        if first_wallet == second_wallet:
            raise ReadinessError("DuelEscrow: canary wallets must be distinct")
        if (
            not str(canary.get("settlement_transaction", "")).strip()
            or not isinstance(canary.get("duel_id"), int)
            or not 0 < canary["duel_id"] < 2**64
            or not isinstance(canary.get("settlement_transaction_lt"), int)
            or canary["settlement_transaction_lt"] <= 0
            or not isinstance(canary.get("masterchain_seqno"), int)
            or canary["masterchain_seqno"] <= 0
        ):
            raise ReadinessError("DuelEscrow: canary finality evidence is invalid")
    source_verification = manifest.get("source_verification")
    if (
        not isinstance(source_verification, dict)
        or source_verification.get("verified") is not True
        or not str(source_verification.get("url", "")).startswith("https://")
    ):
        raise ReadinessError(f"{contract}: published source verification is missing")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("pre-deploy", "post-deploy"), required=True)
    parser.add_argument("--release-file", type=Path, default=DEFAULT_RELEASE_FILE)
    args = parser.parse_args()
    try:
        release_file = args.release_file.resolve()
        release = read_object(release_file)
        audited_commit = validate_release_evidence(release, release_file)
        if args.phase == "post-deploy":
            validate_runtime_environment(release, audited_commit)
            validate_manifest(
                release_file.parent / "bank.json",
                contract="BankQueue",
                release=release,
                audited_commit=audited_commit,
            )
            validate_manifest(
                release_file.parent / "duel.json",
                contract="DuelEscrow",
                release=release,
                audited_commit=audited_commit,
            )
    except (ReadinessError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "ready": True,
                "phase": args.phase,
                "audited_commit": audited_commit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
