#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

PROOF_PATTERN = re.compile(
    r"DUEL_CANARY_PROOF duel_id=(?P<duel_id>\d+) settlement_hash=(?P<hash>[0-9a-fA-F]{1,64})"
)
NETWORK_IDS = {"testnet": -3, "mainnet": -239}
TONCENTER_URLS = {
    "testnet": "https://testnet.toncenter.com",
    "mainnet": "https://toncenter.com",
}
DEFAULT_MIN_BALANCE_NANO = 1_800_000_000
WALLET_ALIASES = {
    "testnet": ("loop-canary-a", "loop-canary-b"),
    "mainnet": ("loop-mainnet-canary-a", "loop-mainnet-canary-b"),
}
FUNDING_POLL_ATTEMPTS = 12
FUNDING_POLL_INTERVAL_SECONDS = 5


def run(
    command: list[str],
    environment: dict[str, str],
    *,
    echo: bool = True,
    include_stderr: bool = False,
) -> str:
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
    return result.stdout + result.stderr if include_stderr else result.stdout


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


def require_mainnet_funding(
    environment: dict[str, str],
    first_wallet: str,
    second_wallet: str,
    minimum_balance_nano: int,
) -> dict[str, dict[str, Any]]:
    snapshot = wallet_snapshot(environment)
    require_canary_wallets(snapshot, first_wallet, second_wallet)
    if any(
        not isinstance(snapshot[name].get("balance"), int)
        or snapshot[name]["balance"] < minimum_balance_nano
        for name in (first_wallet, second_wallet)
    ):
        raise SystemExit("mainnet canary wallets are below the configured safety floor")
    return snapshot


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def canary_evidence(
    proof_response: dict[str, Any],
    wallet_snapshot_value: dict[str, dict[str, Any]],
    first_wallet: str,
    second_wallet: str,
) -> dict[str, Any]:
    required_ints = (
        "duel_id",
        "settlement_transaction_lt",
        "masterchain_seqno",
    )
    if proof_response.get("status") != "verified" or any(
        not isinstance(proof_response.get(name), int) or proof_response[name] <= 0
        for name in required_ints
    ):
        raise SystemExit("canary proof endpoint returned malformed finality evidence")
    transaction = proof_response.get("settlement_transaction")
    if not isinstance(transaction, str) or not transaction:
        raise SystemExit("canary proof endpoint omitted the settlement transaction")
    return {
        "first_wallet": wallet_snapshot_value[first_wallet]["address"],
        "second_wallet": wallet_snapshot_value[second_wallet]["address"],
        "duel_id": proof_response["duel_id"],
        "query_id": proof_response["duel_id"],
        "settlement_transaction": transaction,
        "settlement_transaction_lt": proof_response["settlement_transaction_lt"],
        "masterchain_seqno": proof_response["masterchain_seqno"],
    }


def fetch_settlement_finality(
    network: str,
    transaction_hash: str,
    duel_id: int,
) -> dict[str, Any]:
    query = urllib.parse.urlencode({"hash": transaction_hash, "limit": 2})
    headers: dict[str, str] = {}
    api_key = os.getenv("LOOP_TONCENTER_API_KEY") or os.getenv(
        "TONCENTER_MAINNET_API_KEY"
        if network == "mainnet"
        else "TONCENTER_TESTNET_API_KEY"
    )
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(
        f"{TONCENTER_URLS[network]}/api/v3/transactions?{query}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit("TON settlement finality provider is unavailable") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SystemExit(
            "TON settlement finality provider returned invalid JSON"
        ) from exc
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list) or len(transactions) != 1:
        raise SystemExit("TON settlement transaction is missing or ambiguous")
    transaction = transactions[0]
    description = (
        transaction.get("description") if isinstance(transaction, dict) else None
    )
    compute = description.get("compute_ph") if isinstance(description, dict) else None
    action = description.get("action") if isinstance(description, dict) else None
    if (
        not isinstance(transaction, dict)
        or transaction.get("emulated")
        or not isinstance(description, dict)
        or description.get("aborted")
        or not isinstance(compute, dict)
        or compute.get("success") is not True
        or (isinstance(action, dict) and action.get("success") is False)
    ):
        raise SystemExit("TON settlement transaction did not complete successfully")
    try:
        logical_time = int(transaction["lt"])
        masterchain_seqno = int(transaction["mc_block_seqno"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit("TON settlement finality proof is malformed") from exc
    if logical_time <= 0 or masterchain_seqno <= 0:
        raise SystemExit("TON settlement has no masterchain finality proof")
    return {
        "status": "verified",
        "duel_id": duel_id,
        "settlement_transaction": transaction_hash,
        "settlement_transaction_lt": logical_time,
        "masterchain_seqno": masterchain_seqno,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LOOP two-wallet DUEL canary")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--first-wallet", required=True)
    parser.add_argument("--second-wallet", required=True)
    parser.add_argument("--network", choices=tuple(NETWORK_IDS), default="testnet")
    parser.add_argument("--origin", default=os.getenv("LOOP_PUBLIC_ORIGIN", ""))
    parser.add_argument(
        "--evidence-only",
        action="store_true",
        help="verify finality and print manifest evidence without reporting to the API",
    )
    args = parser.parse_args()
    expected_wallets = WALLET_ALIASES[args.network]
    if (args.first_wallet, args.second_wallet) != expected_wallets:
        raise SystemExit(
            "canary wallet aliases must match the audited systemd identities"
        )

    signing_key = os.environ.get("LOOP_DUEL_INVITE_SIGNING_KEY", "")
    metrics_token = os.environ.get("LOOP_METRICS_TOKEN", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signing_key):
        raise SystemExit("LOOP_DUEL_INVITE_SIGNING_KEY must be 32-byte hex")
    if not args.evidence_only and (
        not metrics_token or not args.origin.startswith("https://")
    ):
        raise SystemExit("LOOP_METRICS_TOKEN and HTTPS LOOP_PUBLIC_ORIGIN are required")

    try:
        network_id = int(
            os.getenv("LOOP_TON_NETWORK_ID", str(NETWORK_IDS[args.network]))
        )
        minimum_balance_nano = int(
            os.getenv(
                "LOOP_DUEL_CANARY_MIN_BALANCE_NANO", str(DEFAULT_MIN_BALANCE_NANO)
            )
        )
    except ValueError as exc:
        raise SystemExit(
            "canary network and balance settings must be integers"
        ) from exc
    if network_id != NETWORK_IDS[args.network]:
        raise SystemExit("DUEL canary network does not match LOOP_TON_NETWORK_ID")
    if args.network == "mainnet" and not env_flag("LOOP_ALLOW_MAINNET_CANARY"):
        raise SystemExit(
            "set LOOP_ALLOW_MAINNET_CANARY=1 to broadcast a mainnet canary"
        )
    if minimum_balance_nano < 1_000_000_000:
        raise SystemExit("LOOP_DUEL_CANARY_MIN_BALANCE_NANO must be at least 1 GRAM")

    environment = os.environ.copy()
    if args.network == "testnet":
        funded = ensure_testnet_funding(
            environment,
            args.first_wallet,
            args.second_wallet,
            minimum_balance_nano,
        )
    else:
        funded = require_mainnet_funding(
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
    script_path = (
        "scripts/canary-duel-two-wallet.tolk"
        if args.network == "testnet"
        else "scripts/canary-duel-two-wallet-mainnet.tolk"
    )
    script_args = [
        script_path,
        args.contract,
        str(first_offer_id),
        str(second_offer_id),
        str(expires_at),
    ]
    run(
        ["acton", "script", "--fork-net", args.network, *script_args],
        environment,
    )
    live_output = run(
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
        include_stderr=True,
    )
    proof = PROOF_PATTERN.search(live_output)
    if not proof:
        raise SystemExit("canary completed without a parseable settlement proof")

    try:
        reported_balances = wallet_snapshot(environment)
        require_canary_wallets(reported_balances, args.first_wallet, args.second_wallet)
    except SystemExit:
        reported_balances = funded

    proof_response = fetch_settlement_finality(
        args.network,
        proof.group("hash").zfill(64),
        int(proof.group("duel_id")),
    )
    payload = json.dumps(
        {
            "network": network_id,
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
    if not args.evidence_only:
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
                try:
                    proof_response = json.loads(response.read())
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise SystemExit(
                        "canary proof endpoint returned invalid JSON"
                    ) from exc
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"canary proof endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SystemExit("canary proof endpoint is unavailable") from exc
        print(f"DUEL_CANARY_REPORTED duel_id={proof.group('duel_id')}")
    print(
        "DUEL_CANARY_EVIDENCE "
        + json.dumps(
            canary_evidence(
                proof_response,
                reported_balances,
                args.first_wallet,
                args.second_wallet,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
