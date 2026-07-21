import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

import httpx

from .config import get_settings
from .ton import TonClient, TonProviderError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-onchain-audit",
        description="Read-only TON proofs for LOOP operations.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    contract = commands.add_parser("contract", help="Verify active state and deployed code hash")
    contract.add_argument("--mode", choices=("bank", "duel"), default="duel")
    contract.add_argument("--address", help="Contract address; defaults to LOOP configuration")

    wallet = commands.add_parser("wallet", help="Read a native GRAM balance")
    wallet.add_argument("--address", required=True)

    transaction = commands.add_parser(
        "transaction", help="Verify transaction success, account and masterchain inclusion"
    )
    transaction.add_argument("--hash", required=True, dest="transaction_hash")
    transaction.add_argument("--account", required=True)

    jetton = commands.add_parser("jetton", help="Verify Jetton owner, master and balance")
    jetton.add_argument("--owner", required=True)
    jetton.add_argument("--master", required=True)
    return parser


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as http:
        client = TonClient(http, settings)
        try:
            if args.command == "contract":
                configured_address = (
                    settings.bank_contract_address
                    if args.mode == "bank"
                    else settings.effective_duel_contract_address
                )
                expected_hash = (
                    settings.bank_contract_code_hash
                    if args.mode == "bank"
                    else settings.effective_duel_contract_code_hash
                )
                address = str(args.address or configured_address)
                if not address:
                    raise TonProviderError("contract address is required")
                state = await client.get_contract_state(address)
                if expected_hash and state.code_hash != expected_hash.removeprefix("0x").upper():
                    raise TonProviderError(f"{args.mode} contract code hash mismatch")
                result: Any = {"mode": args.mode, **asdict(state)}
            elif args.command == "wallet":
                result = {
                    "address": str(args.address),
                    "balance_nano": await client.get_native_balance(str(args.address)),
                }
            elif args.command == "transaction":
                result = asdict(
                    await client.verify_transaction(str(args.transaction_hash), str(args.account))
                )
            else:
                result = asdict(await client.get_jetton_wallet(str(args.owner), str(args.master)))
        except TonProviderError as exc:
            print(json.dumps({"verified": False, "error": str(exc)}, ensure_ascii=False))
            return 1
    print(
        json.dumps(
            {"verified": True, "result": result},
            ensure_ascii=False,
            indent=2,
            default=json_default,
        )
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == "__main__":
    main()
