#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

PROOF_PATTERN = re.compile(
    r"DUEL_CANARY_PROOF duel_id=(?P<duel_id>\d+) settlement_hash=(?P<hash>[0-9a-fA-F]{64})"
)


def run(command: list[str], environment: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LOOP two-wallet DUEL testnet canary")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--first-wallet", required=True)
    parser.add_argument("--second-wallet", required=True)
    parser.add_argument("--origin", default=os.getenv("LOOP_PUBLIC_ORIGIN", ""))
    args = parser.parse_args()

    signing_key = os.environ.get("LOOP_DUEL_INVITE_SIGNING_KEY", "")
    metrics_token = os.environ.get("LOOP_METRICS_TOKEN", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signing_key):
        raise SystemExit("LOOP_DUEL_INVITE_SIGNING_KEY must be 32-byte hex")
    if not metrics_token or not args.origin.startswith("https://"):
        raise SystemExit("LOOP_METRICS_TOKEN and HTTPS LOOP_PUBLIC_ORIGIN are required")

    wallet_result = json.loads(run(["acton", "wallet", "list", "--json"], os.environ.copy()))
    addresses = {
        item["name"]: item["address"] for item in wallet_result.get("wallets", [])
    }
    if args.first_wallet not in addresses or args.second_wallet not in addresses:
        raise SystemExit("both canary wallet aliases must already exist")
    if addresses[args.first_wallet] == addresses[args.second_wallet]:
        raise SystemExit("canary wallets must resolve to distinct addresses")

    now = int(time.time())
    first_offer_id = 8_500_000_000_000_000 + (now % 100_000_000) * 2
    second_offer_id = first_offer_id + 1
    expires_at = now + 600
    environment = os.environ.copy()
    environment["LOOP_DUEL_CANARY_SIGNING_SEED"] = f"0x{signing_key}"
    common = [
        "acton",
        "script",
        "scripts/canary-duel-two-wallet.tolk",
        args.contract,
        args.first_wallet,
        args.second_wallet,
        str(first_offer_id),
        str(second_offer_id),
        str(expires_at),
    ]
    run([*common, "--fork-net", "testnet"], environment)
    live_output = run([*common, "--net", "testnet", "--explorer", "tonviewer"], environment)
    proof = PROOF_PATTERN.search(live_output)
    if not proof:
        raise SystemExit("canary completed without a parseable settlement proof")

    payload = json.dumps(
        {
            "network": -3,
            "contract_address": args.contract,
            "duel_id": int(proof.group("duel_id")),
            "settlement_tx_hash": proof.group("hash"),
        }
    ).encode()
    request = urllib.request.Request(
        f"{args.origin.rstrip('/')}/internal/duel-canary",
        data=payload,
        headers={
            "Authorization": f"Bearer {metrics_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise SystemExit(f"canary proof endpoint returned HTTP {response.status}")
    print(f"DUEL_CANARY_REPORTED duel_id={proof.group('duel_id')}")


if __name__ == "__main__":
    main()
