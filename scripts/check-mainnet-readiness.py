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

    audit = release.get("external_audit")
    if not isinstance(audit, dict) or not str(audit.get("provider", "")).strip():
        raise ReadinessError("external audit provider is required")
    try:
        completed_at = date.fromisoformat(str(audit.get("completed_at", "")))
    except ValueError as exc:
        raise ReadinessError("external audit completion date is invalid") from exc
    if completed_at > date.today():
        raise ReadinessError("external audit completion date cannot be in the future")
    expected_report_hash = str(audit.get("report_sha256", ""))
    if HASH.fullmatch(expected_report_hash) is None or set(expected_report_hash) == {"0"}:
        raise ReadinessError("external audit report SHA-256 is required")
    report_path = ROOT / str(audit.get("report_path", ""))
    try:
        report_path.relative_to(ROOT / "docs" / "audits")
    except ValueError as exc:
        raise ReadinessError("audit report must be stored under docs/audits") from exc
    if not report_path.is_file():
        raise ReadinessError(f"audit report is missing: {report_path}")
    actual_report_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    if actual_report_hash.lower() != expected_report_hash.lower():
        raise ReadinessError("audit report SHA-256 mismatch")

    require_mainnet_address(release.get("owner"), "owner")
    require_mainnet_address(release.get("treasury"), "treasury")
    public_key = str(release.get("duel_invite_signer_public_key", ""))
    if HASH.fullmatch(public_key) is None or set(public_key) == {"0"}:
        raise ReadinessError("DUEL invite signer public key is invalid")
    limits = release.get("initial_limits")
    if not isinstance(limits, dict):
        raise ReadinessError("initial mainnet limits are required")
    for key in ("bank_max_principal_nano", "duel_max_pool_nano"):
        value = limits.get(key)
        if not isinstance(value, int) or value <= 0 or value > INITIAL_VALUE_CAP_NANO:
            raise ReadinessError(f"{key} must be within the initial 10 GRAM cap")
    if release_file.parent != ROOT / "deployments" / "mainnet":
        raise ReadinessError("release evidence must live under deployments/mainnet")
    return head


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
    if not isinstance(manifest.get("verified_smoke"), dict):
        raise ReadinessError(f"{contract}: finalized smoke proof is missing")
    if contract == "DuelEscrow":
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
