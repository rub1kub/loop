#!/usr/bin/env python3
"""Safely rehearse or broadcast the LOOP BANK two-wallet payout canary."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from typing import Any

import httpx

PROOF_PATTERN = re.compile(
    r"BANK_CANARY_PROOF first_position=(?P<first>\d+) "
    r"second_position=(?P<second>\d+) first_hash=(?P<first_hash>[0-9a-fA-F]{1,64}) "
    r"funding_hash=(?P<funding_hash>[0-9a-fA-F]{1,64})"
)
NETWORK_IDS = {"testnet": -3, "mainnet": -239}
TONCENTER_URLS = {
    "testnet": "https://testnet.toncenter.com",
    "mainnet": "https://toncenter.com",
}
WALLET_ALIASES = {
    "testnet": ("loop-canary-a", "loop-canary-b"),
    "mainnet": ("loop-mainnet-canary-a", "loop-mainnet-canary-b"),
}
MINIMUM_BALANCE_NANO = 1_300_000_000
POLL_ATTEMPTS = 12
POLL_SECONDS = 5


def run(command: list[str], environment: dict[str, str], *, echo: bool = True) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if echo:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout + result.stderr


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def wallet_snapshot(environment: dict[str, str]) -> dict[str, dict[str, Any]]:
    raw = run(
        ["acton", "wallet", "list", "--balance", "--json"],
        environment,
        echo=False,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit("Acton returned an invalid wallet inventory") from exc
    if payload.get("success") is not True or not isinstance(
        payload.get("wallets"), list
    ):
        raise SystemExit("Acton wallet inventory failed")
    return {
        str(item["name"]): item
        for item in payload["wallets"]
        if isinstance(item, dict) and "name" in item
    }


def require_wallets(
    snapshot: dict[str, dict[str, Any]], aliases: tuple[str, str]
) -> None:
    first, second = aliases
    if first not in snapshot or second not in snapshot:
        raise SystemExit("both audited BANK canary wallet aliases must already exist")
    if snapshot[first].get("address") == snapshot[second].get("address"):
        raise SystemExit("BANK canary wallets must resolve to distinct addresses")


def ensure_funding(
    environment: dict[str, str],
    aliases: tuple[str, str],
    *,
    network: str,
) -> dict[str, dict[str, Any]]:
    snapshot = wallet_snapshot(environment)
    require_wallets(snapshot, aliases)
    if network == "testnet":
        for alias in aliases:
            balance = snapshot[alias].get("balance")
            if not isinstance(balance, int) or balance < 0:
                raise SystemExit(f"Acton returned no balance for {alias}")
            if balance < MINIMUM_BALANCE_NANO:
                run(
                    ["acton", "wallet", "airdrop", alias, "--net", "testnet", "--json"],
                    environment,
                    echo=False,
                )
    for attempt in range(POLL_ATTEMPTS):
        snapshot = wallet_snapshot(environment)
        require_wallets(snapshot, aliases)
        if all(
            isinstance(snapshot[alias].get("balance"), int)
            and snapshot[alias]["balance"] >= MINIMUM_BALANCE_NANO
            for alias in aliases
        ):
            return snapshot
        if network == "mainnet":
            break
        if attempt + 1 < POLL_ATTEMPTS:
            time.sleep(POLL_SECONDS)
    raise SystemExit("BANK canary wallets are below the 1.3 GRAM safety floor")


def normalize_hash(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]{1,64}", value):
        return value.zfill(64).lower()
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_")
    except ValueError as exc:
        raise SystemExit("BANK canary emitted an invalid transaction hash") from exc
    if len(raw) != 32:
        raise SystemExit("BANK canary transaction hash must contain 32 bytes")
    return raw.hex()


def successful_transaction(transaction: dict[str, Any]) -> bool:
    description = transaction.get("description") or {}
    compute = description.get("compute_ph") or {}
    action = description.get("action") or {}
    return bool(
        not transaction.get("emulated")
        and not description.get("aborted")
        and compute.get("success") is True
        and action.get("success") is not False
    )


def finalized_transaction(network: str, transaction_hash: str) -> dict[str, int | str]:
    api_key = os.getenv("LOOP_TONCENTER_API_KEY") or os.getenv(
        "TONCENTER_MAINNET_API_KEY"
        if network == "mainnet"
        else "TONCENTER_TESTNET_API_KEY"
    )
    headers = {"X-API-Key": api_key} if api_key else {}
    for attempt in range(POLL_ATTEMPTS):
        try:
            response = httpx.get(
                f"{TONCENTER_URLS[network]}/api/v3/transactions",
                params={"hash": transaction_hash, "limit": 2},
                headers=headers,
                timeout=30,
            )
            if response.status_code in {401, 403} and headers:
                headers = {}
                continue
            if response.status_code not in {404, 429, 500, 502, 503, 504}:
                response.raise_for_status()
                transactions = response.json().get("transactions", [])
                if len(transactions) > 1:
                    raise SystemExit("BANK canary transaction is ambiguous")
                if len(transactions) == 1:
                    transaction = transactions[0]
                    if not successful_transaction(transaction):
                        raise SystemExit("BANK canary transaction was not successful")
                    logical_time = int(transaction.get("lt", 0))
                    masterchain_seqno = int(transaction.get("mc_block_seqno", 0))
                    if logical_time <= 0 or masterchain_seqno <= 0:
                        raise SystemExit("BANK canary transaction lacks finality")
                    return {
                        "transaction": transaction_hash,
                        "transaction_lt": logical_time,
                        "masterchain_seqno": masterchain_seqno,
                    }
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError):
            pass
        if attempt + 1 < POLL_ATTEMPTS:
            time.sleep(POLL_SECONDS)
    raise SystemExit("BANK canary transactions were not finalized before timeout")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--network", choices=tuple(NETWORK_IDS), default="testnet")
    parser.add_argument("--first-wallet", required=True)
    parser.add_argument("--second-wallet", required=True)
    parser.add_argument("--treasury", required=True)
    parser.add_argument("--production-contract")
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="broadcast after a successful fork rehearsal",
    )
    args = parser.parse_args()

    aliases = (args.first_wallet, args.second_wallet)
    if aliases != WALLET_ALIASES[args.network]:
        raise SystemExit("BANK canary aliases do not match the audited identities")
    try:
        configured_network = int(
            os.getenv("LOOP_TON_NETWORK_ID", str(NETWORK_IDS[args.network]))
        )
    except ValueError as exc:
        raise SystemExit("LOOP_TON_NETWORK_ID must be an integer") from exc
    if configured_network != NETWORK_IDS[args.network]:
        raise SystemExit("BANK canary network does not match LOOP_TON_NETWORK_ID")

    if args.network == "mainnet":
        if not args.production_contract:
            raise SystemExit("--production-contract is required for mainnet")
        if args.production_contract == args.contract:
            raise SystemExit("mainnet BANK canary must target a separate shadow contract")
        if args.broadcast and not env_flag("LOOP_ALLOW_MAINNET_CANARY"):
            raise SystemExit("set LOOP_ALLOW_MAINNET_CANARY=1 to broadcast on mainnet")
        run(
            [
                ".venv/bin/python",
                "scripts/check-mainnet-readiness.py",
                "--phase",
                "pre-deploy",
            ],
            os.environ.copy(),
            echo=False,
        )
    elif args.broadcast and not env_flag("LOOP_ALLOW_TESTNET_CANARY"):
        raise SystemExit("set LOOP_ALLOW_TESTNET_CANARY=1 to broadcast on testnet")

    environment = os.environ.copy()
    snapshot = wallet_snapshot(environment)
    require_wallets(snapshot, aliases)
    first_position = (
        8_600_000_000_000_000
        + (time.time_ns() // 1_000_000 % 100_000_000_000) * 2
    )
    second_position = first_position + 1
    script = (
        "scripts/canary-bank-two-wallet-live.tolk"
        if args.network == "testnet"
        else "scripts/canary-bank-two-wallet-live-mainnet.tolk"
    )
    script_args = [
        script,
        args.contract,
        str(first_position),
        str(second_position),
    ]
    run(["acton", "script", "--fork-net", args.network, *script_args], environment)
    if not args.broadcast:
        print(
            f"BANK_CANARY_EMULATED first_position={first_position} "
            f"second_position={second_position}"
        )
        return

    funded = ensure_funding(environment, aliases, network=args.network)
    output = run(
        [
            "acton",
            "script",
            "--net",
            args.network,
            "--explorer",
            "tonviewer",
            *script_args,
        ],
        environment,
    )
    proof = PROOF_PATTERN.search(output)
    if not proof:
        raise SystemExit("BANK canary completed without a parseable proof")
    first_hash = normalize_hash(proof.group("first_hash"))
    funding_hash = normalize_hash(proof.group("funding_hash"))
    first_finality = finalized_transaction(args.network, first_hash)
    funding_finality = finalized_transaction(args.network, funding_hash)
    evidence = {
        "contract_address": args.contract,
        "treasury": args.treasury,
        "first_wallet": funded[aliases[0]]["address"],
        "second_wallet": funded[aliases[1]]["address"],
        "position_id": int(proof.group("first")),
        "principal_nano": 1_000_000_000,
        "multiplier_bps": 12_500,
        "gas_nano": 80_000_000,
        "fee_nano": 10_000_000,
        "first_transaction": first_finality["transaction"],
        "first_transaction_lt": first_finality["transaction_lt"],
        "first_masterchain_seqno": first_finality["masterchain_seqno"],
        "funding_position_id": int(proof.group("second")),
        "funding_principal_nano": 1_000_000_000,
        "funding_multiplier_bps": 12_500,
        "funding_gas_nano": 80_000_000,
        "funding_fee_nano": 10_000_000,
        "funding_transaction": funding_finality["transaction"],
        "funding_transaction_lt": funding_finality["transaction_lt"],
        "funding_masterchain_seqno": funding_finality["masterchain_seqno"],
        "payout_nano": 1_250_000_000,
        "remaining_funding_nano": 730_000_000,
    }
    print("BANK_CANARY_EVIDENCE " + json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
