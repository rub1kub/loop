#!/usr/bin/env python3
"""Fail-closed verification of LOOP testnet deployment manifests."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "deployments" / "testnet"
BUILD_DIR = ROOT / "build"
TONCENTER = "https://testnet.toncenter.com"


def normalize_hash(value: str) -> str:
    raw = value.removeprefix("0x")
    try:
        decoded = bytes.fromhex(raw)
    except ValueError:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_")
    if len(decoded) != 32:
        raise ValueError("TON hash must contain 32 bytes")
    return decoded.hex().upper()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


async def verify_contract(
    client: httpx.AsyncClient, manifest_path: Path
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    contract = str(manifest["contract"])
    address = str(manifest["address"])
    expected_code = normalize_hash(str(manifest["code_hash"]))
    expected_data = normalize_hash(str(manifest["data_hash"]))
    build = load_json(BUILD_DIR / f"{contract}.json")
    build_hash = normalize_hash(str(build["hash"]))
    if build_hash != expected_code:
        raise ValueError(f"{contract}: local build hash differs from manifest")

    state_response = await provider_get(
        client,
        "/api/v3/accountStates",
        {"address": address, "include_boc": "false"},
    )
    accounts = state_response.json().get("accounts", [])
    if len(accounts) != 1:
        raise ValueError(f"{contract}: account state is missing or ambiguous")
    state = accounts[0]
    if state.get("status") != "active":
        raise ValueError(f"{contract}: contract is not active")
    if normalize_hash(str(state.get("code_hash", ""))) != expected_code:
        raise ValueError(f"{contract}: deployed code hash mismatch")
    if normalize_hash(str(state.get("data_hash", ""))) != expected_data:
        raise ValueError(f"{contract}: deployed data hash mismatch")

    tx_response = await provider_get(
        client,
        "/api/v3/transactions",
        {"hash": manifest["deploy_transaction"], "limit": 2},
    )
    transactions = tx_response.json().get("transactions", [])
    if len(transactions) != 1:
        raise ValueError(f"{contract}: deployment transaction is missing or ambiguous")
    transaction = transactions[0]
    description = transaction.get("description") or {}
    compute = description.get("compute_ph") or {}
    action = description.get("action") or {}
    if (
        transaction.get("emulated")
        or description.get("aborted")
        or compute.get("success") is not True
        or action.get("success") is False
    ):
        raise ValueError(f"{contract}: deployment transaction was not successful")
    if int(transaction.get("lt", 0)) != int(manifest["deploy_transaction_lt"]):
        raise ValueError(f"{contract}: deployment logical time mismatch")
    if int(transaction.get("mc_block_seqno", 0)) <= 0:
        raise ValueError(f"{contract}: deployment lacks masterchain finality")

    return {
        "contract": contract,
        "address": address,
        "active": True,
        "local_build_matches": True,
        "code_hash": expected_code,
        "data_hash": expected_data,
        "deployment_transaction": str(manifest["deploy_transaction"]),
        "deployment_lt": int(manifest["deploy_transaction_lt"]),
        "masterchain_seqno": int(transaction["mc_block_seqno"]),
        "verified": True,
    }


async def provider_get(
    client: httpx.AsyncClient, path: str, params: dict[str, Any]
) -> httpx.Response:
    for attempt in range(4):
        response = await client.get(f"{TONCENTER}{path}", params=params)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        await asyncio.sleep(attempt + 1)
    response.raise_for_status()
    raise AssertionError("unreachable")


async def run(selected: list[str]) -> int:
    headers = {}
    if api_key := os.getenv("LOOP_TONCENTER_API_KEY"):
        headers["X-API-Key"] = api_key
    try:
        async with httpx.AsyncClient(headers=headers, timeout=20) as client:
            results = [
                await verify_contract(client, MANIFEST_DIR / f"{name}.json")
                for name in selected
            ]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {"verified": True, "contracts": results}, ensure_ascii=False, indent=2
        )
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contracts", nargs="*", choices=("bank", "duel"))
    args = parser.parse_args()
    selected = args.contracts or ["bank", "duel"]
    raise SystemExit(asyncio.run(run(selected)))


if __name__ == "__main__":
    main()
