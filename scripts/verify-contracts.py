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
from tonsdk.boc import Cell  # type: ignore[import-untyped]
from tonsdk.utils import Address  # type: ignore[import-untyped]

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


def raw_address(value: str) -> str:
    return Address(value).to_string(is_user_friendly=False).lower()


def stack_address(item: list[Any]) -> str:
    boc = base64.b64decode(str(item[1]["bytes"]))
    cell = Cell.one_from_boc(boc)
    if isinstance(cell, list):
        cell = cell[0]
    address = cell.begin_parse().read_msg_addr()
    if address is None:
        raise ValueError("contractConfig returned an empty address")
    return address.to_string(is_user_friendly=False).lower()


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
    if raw_address(str(transaction.get("account", ""))) != raw_address(
        str(state["address"])
    ):
        raise ValueError(f"{contract}: deployment transaction account mismatch")
    deployed_state = transaction.get("account_state_after") or {}
    if normalize_hash(str(deployed_state.get("code_hash", ""))) != expected_code:
        raise ValueError(f"{contract}: deployment code hash mismatch")
    if normalize_hash(str(deployed_state.get("data_hash", ""))) != expected_data:
        raise ValueError(f"{contract}: deployment data hash mismatch")

    getter_response = await provider_post(
        client,
        "/api/v2/runGetMethod",
        {"address": address, "method": "contractConfig", "stack": []},
    )
    getter = getter_response.json()
    result = getter.get("result") or {}
    stack = result.get("stack") or []
    if not getter.get("ok") or result.get("exit_code") != 0 or len(stack) < 4:
        raise ValueError(f"{contract}: contractConfig getter failed")
    configuration = manifest["configuration"]
    if stack_address(stack[0]) != raw_address(str(configuration["owner"])):
        raise ValueError(f"{contract}: owner mismatch")
    if stack_address(stack[1]) != raw_address(str(configuration["treasury"])):
        raise ValueError(f"{contract}: treasury mismatch")
    if int(str(stack[2][1]), 0) != int(configuration["fee_bps"]):
        raise ValueError(f"{contract}: fee mismatch")
    if bool(int(str(stack[3][1]), 0)) != bool(configuration["paused"]):
        raise ValueError(f"{contract}: pause state mismatch")

    return {
        "contract": contract,
        "address": address,
        "active": True,
        "local_build_matches": True,
        "code_hash": expected_code,
        "initial_data_hash": expected_data,
        "initial_data_hash_matches": True,
        "configuration_matches": True,
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


async def provider_post(
    client: httpx.AsyncClient, path: str, payload: dict[str, Any]
) -> httpx.Response:
    for attempt in range(4):
        response = await client.post(f"{TONCENTER}{path}", json=payload)
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
