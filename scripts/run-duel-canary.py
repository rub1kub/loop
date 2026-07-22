#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

PROOF_PATTERN = re.compile(
    r"DUEL_CANARY_PROOF duel_id=(?P<duel_id>\d+) settlement_hash=(?P<hash>[0-9a-fA-F]{1,64})"
)
TESTNET_NETWORK_ID = -3
DEFAULT_MIN_BALANCE_NANO = 1_800_000_000
FIRST_WALLET_ALIAS = "loop-canary-a"
SECOND_WALLET_ALIAS = "loop-canary-b"
FUNDING_POLL_ATTEMPTS = 12
FUNDING_POLL_INTERVAL_SECONDS = 5


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
        if not echo:
            sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


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


def require_canary_wallets(
    snapshot: dict[str, dict[str, Any]], first_wallet: str, second_wallet: str
) -> None:
    if first_wallet not in snapshot or second_wallet not in snapshot:
        raise SystemExit("both canary wallet aliases must already exist")
    if snapshot[first_wallet].get("address") == snapshot[second_wallet].get("address"):
        raise SystemExit("canary wallets must resolve to distinct addresses")


def ensure_testnet_funding(
    environment: dict[str, str],
    first_wallet: str,
    second_wallet: str,
    minimum_balance_nano: int,
) -> dict[str, dict[str, Any]]:
    snapshot = wallet_snapshot(environment)
    require_canary_wallets(snapshot, first_wallet, second_wallet)
    for name in (first_wallet, second_wallet):
        balance = snapshot[name].get("balance")
        if not isinstance(balance, int) or balance < 0:
            raise SystemExit(f"Acton returned no testnet balance for {name}")
        if balance < minimum_balance_nano:
            run(
                ["acton", "wallet", "airdrop", name, "--net", "testnet", "--json"],
                environment,
                echo=False,
            )

    for attempt in range(FUNDING_POLL_ATTEMPTS):
        funded = wallet_snapshot(environment)
        require_canary_wallets(funded, first_wallet, second_wallet)
        if all(
            isinstance(funded[name].get("balance"), int)
            and funded[name]["balance"] >= minimum_balance_nano
            for name in (first_wallet, second_wallet)
        ):
            return funded
        if attempt + 1 < FUNDING_POLL_ATTEMPTS:
            time.sleep(FUNDING_POLL_INTERVAL_SECONDS)
    raise SystemExit("testnet canary funding stayed below the configured safety floor")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the LOOP two-wallet DUEL testnet canary"
    )
    parser.add_argument("--contract", required=True)
    parser.add_argument("--first-wallet", required=True)
    parser.add_argument("--second-wallet", required=True)
    parser.add_argument("--origin", default=os.getenv("LOOP_PUBLIC_ORIGIN", ""))
    args = parser.parse_args()
    if (args.first_wallet, args.second_wallet) != (
        FIRST_WALLET_ALIAS,
        SECOND_WALLET_ALIAS,
    ):
        raise SystemExit(
            "canary wallet aliases must match the audited systemd identities"
        )

    signing_key = os.environ.get("LOOP_DUEL_INVITE_SIGNING_KEY", "")
    metrics_token = os.environ.get("LOOP_METRICS_TOKEN", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signing_key):
        raise SystemExit("LOOP_DUEL_INVITE_SIGNING_KEY must be 32-byte hex")
    if not metrics_token or not args.origin.startswith("https://"):
        raise SystemExit("LOOP_METRICS_TOKEN and HTTPS LOOP_PUBLIC_ORIGIN are required")

    try:
        network_id = int(os.getenv("LOOP_TON_NETWORK_ID", str(TESTNET_NETWORK_ID)))
        minimum_balance_nano = int(
            os.getenv(
                "LOOP_DUEL_CANARY_MIN_BALANCE_NANO", str(DEFAULT_MIN_BALANCE_NANO)
            )
        )
    except ValueError as exc:
        raise SystemExit(
            "canary network and balance settings must be integers"
        ) from exc
    if network_id != TESTNET_NETWORK_ID:
        raise SystemExit("DUEL canary is testnet-only")
    if minimum_balance_nano < 1_000_000_000:
        raise SystemExit("LOOP_DUEL_CANARY_MIN_BALANCE_NANO must be at least 1 GRAM")

    environment = os.environ.copy()
    funded = ensure_testnet_funding(
        environment,
        args.first_wallet,
        args.second_wallet,
        minimum_balance_nano,
    )

    now = int(time.time())
    first_offer_id = (
        8_500_000_000_000_000 + (time.time_ns() // 1_000_000 % 100_000_000_000) * 2
    )
    second_offer_id = first_offer_id + 1
    expires_at = now + 600
    environment["LOOP_DUEL_CANARY_SIGNING_SEED"] = f"0x{signing_key}"
    script_args = [
        "scripts/canary-duel-two-wallet.tolk",
        args.contract,
        str(first_offer_id),
        str(second_offer_id),
        str(expires_at),
    ]
    run(["acton", "script", "--fork-net", "testnet", *script_args], environment)
    live_output = run(
        [
            "acton",
            "script",
            "--net",
            "testnet",
            "--explorer",
            "tonviewer",
            *script_args,
        ],
        environment,
    )
    proof = PROOF_PATTERN.search(live_output)
    if not proof:
        raise SystemExit("canary completed without a parseable settlement proof")

    try:
        reported_balances = wallet_snapshot(environment)
        require_canary_wallets(reported_balances, args.first_wallet, args.second_wallet)
    except SystemExit:
        reported_balances = funded

    payload = json.dumps(
        {
            "network": TESTNET_NETWORK_ID,
            "contract_address": args.contract,
            "duel_id": int(proof.group("duel_id")),
            "settlement_tx_hash": proof.group("hash").zfill(64),
            "first_wallet_balance_nano": reported_balances[args.first_wallet][
                "balance"
            ],
            "second_wallet_balance_nano": reported_balances[args.second_wallet][
                "balance"
            ],
        }
    ).encode()
    request = urllib.request.Request(
        f"{args.origin.rstrip('/')}/api/internal/duel-canary",
        data=payload,
        headers={
            "Authorization": f"Bearer {metrics_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise SystemExit(
                    f"canary proof endpoint returned HTTP {response.status}"
                )
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"canary proof endpoint returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit("canary proof endpoint is unavailable") from exc
    print(f"DUEL_CANARY_REPORTED duel_id={proof.group('duel_id')}")


if __name__ == "__main__":
    main()
