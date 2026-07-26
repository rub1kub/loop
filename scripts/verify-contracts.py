#!/usr/bin/env python3
"""Fail-closed verification of LOOP deployment manifests and live invariants."""

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
BUILD_DIR = ROOT / "build"
NETWORKS = {
    "testnet": {
        "id": -3,
        "toncenter": "https://testnet.toncenter.com",
        "api_key_env": "TONCENTER_TESTNET_API_KEY",
    },
    "mainnet": {
        "id": -239,
        "toncenter": "https://toncenter.com",
        "api_key_env": "TONCENTER_MAINNET_API_KEY",
    },
}
BANK_CREATE_POSITION = 0x4C424E01
BANK_PAYOUT = 0x4C424E11
BANK_PROTOCOL_FEE = 0x4C424E12
DUEL_OPEN_OFFER = 0x4C4F4F01
DUEL_CANCEL_OFFER = 0x4C4F4F02
DUEL_REVEAL = 0x4C4F4F04
DUEL_BOOST = 0x4C4F4F0F
DUEL_OFFER_REFUND = 0x4C4F4F12
DUEL_PAYOUT = 0x4C4F4F11


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


def stack_number(item: list[Any]) -> int:
    if len(item) != 2 or item[0] != "num":
        raise ValueError("contractConfig returned a malformed numeric value")
    return int(str(item[1]), 0)


def validate_live_balance(
    contract: str,
    *,
    live_balance: int,
    live_locked: int,
    min_reserve: int,
) -> None:
    if live_locked < 0 or min_reserve < 0 or live_balance < live_locked + min_reserve:
        raise ValueError(
            f"{contract}: live balance does not cover locked value and reserve"
        )


def body_parser(message: dict[str, Any]) -> Any:
    body = (message.get("message_content") or {}).get("body")
    if not isinstance(body, str) or not body:
        raise ValueError("transaction message body is missing")
    cells = Cell.one_from_boc(base64.b64decode(body))
    cell = cells[0] if isinstance(cells, list) else cells
    return cell.begin_parse()


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


async def verify_bank_smoke(
    client: httpx.AsyncClient, manifest: dict[str, Any]
) -> dict[str, Any] | None:
    smoke = manifest.get("verified_smoke")
    if not isinstance(smoke, dict):
        return None
    smoke_address = str(smoke.get("contract_address", manifest["address"]))
    state_response = await provider_get(
        client,
        "/api/v3/accountStates",
        {"address": smoke_address, "include_boc": "false"},
    )
    accounts = state_response.json().get("accounts", [])
    if len(accounts) != 1 or accounts[0].get("status") != "active":
        raise ValueError("BankQueue: smoke contract is not active")
    if normalize_hash(str(accounts[0].get("code_hash", ""))) != normalize_hash(
        str(manifest["code_hash"])
    ):
        raise ValueError("BankQueue: smoke contract code hash mismatch")

    async def transaction_for(
        hash_value: str, logical_time: int, masterchain_seqno: int
    ) -> dict[str, Any]:
        response = await provider_get(
            client,
            "/api/v3/transactions",
            {"hash": hash_value, "limit": 2},
        )
        transactions = response.json().get("transactions", [])
        if len(transactions) != 1:
            raise ValueError("BankQueue: smoke transaction is missing or ambiguous")
        transaction = transactions[0]
        if not successful_transaction(transaction):
            raise ValueError("BankQueue: smoke transaction was not successful")
        if raw_address(str(transaction.get("account", ""))) != raw_address(
            smoke_address
        ):
            raise ValueError("BankQueue: smoke transaction account mismatch")
        if int(transaction.get("lt", 0)) != logical_time:
            raise ValueError("BankQueue: smoke transaction logical time mismatch")
        if int(transaction.get("mc_block_seqno", 0)) != masterchain_seqno:
            raise ValueError("BankQueue: smoke transaction finality mismatch")
        return transaction

    first_transaction = await transaction_for(
        str(smoke["first_transaction"]),
        int(smoke["first_transaction_lt"]),
        int(smoke["first_masterchain_seqno"]),
    )
    funding_transaction = await transaction_for(
        str(smoke["funding_transaction"]),
        int(smoke["funding_transaction_lt"]),
        int(smoke["funding_masterchain_seqno"]),
    )

    expected_positions = (
        (
            first_transaction,
            "first_wallet",
            "position_id",
            "principal_nano",
            "multiplier_bps",
            "gas_nano",
            "fee_nano",
        ),
        (
            funding_transaction,
            "second_wallet",
            "funding_position_id",
            "funding_principal_nano",
            "funding_multiplier_bps",
            "funding_gas_nano",
            "funding_fee_nano",
        ),
    )
    wallets = {
        raw_address(str(smoke["first_wallet"])),
        raw_address(str(smoke["second_wallet"])),
    }
    if len(wallets) != 2:
        raise ValueError("BankQueue: smoke wallets must be distinct")
    for (
        transaction,
        wallet_key,
        position_key,
        principal_key,
        multiplier_key,
        gas_key,
        fee_key,
    ) in expected_positions:
        incoming = transaction.get("in_msg") or {}
        if raw_address(str(incoming.get("source", ""))) != raw_address(
            str(smoke[wallet_key])
        ):
            raise ValueError("BankQueue: smoke transaction sender mismatch")
        if int(incoming.get("value", 0)) != int(smoke[principal_key]) + int(
            smoke[gas_key]
        ):
            raise ValueError("BankQueue: smoke transaction value mismatch")
        parser = body_parser(incoming)
        decoded = {
            "opcode": parser.read_uint(32),
            "query_id": parser.read_uint(64),
            "position_id": parser.read_uint(64),
            "principal_nano": parser.read_coins(),
            "multiplier_bps": parser.read_uint(16),
        }
        if decoded != {
            "opcode": BANK_CREATE_POSITION,
            "query_id": int(smoke[position_key]),
            "position_id": int(smoke[position_key]),
            "principal_nano": int(smoke[principal_key]),
            "multiplier_bps": int(smoke[multiplier_key]),
        }:
            raise ValueError("BankQueue: smoke transaction body mismatch")
        fees = [
            message
            for message in transaction.get("out_msgs", [])
            if str(message.get("opcode", "")).lower()
            == f"0x{BANK_PROTOCOL_FEE:08x}"
        ]
        if len(fees) != 1:
            raise ValueError("BankQueue: smoke fee message is missing or ambiguous")
        fee = fees[0]
        if raw_address(str(fee.get("destination", ""))) != raw_address(
            str(smoke["treasury"])
        ) or int(fee.get("value", 0)) != int(smoke[fee_key]):
            raise ValueError("BankQueue: smoke fee message mismatch")
        fee_parser = body_parser(fee)
        if (
            fee_parser.read_uint(32) != BANK_PROTOCOL_FEE
            or fee_parser.read_uint(64) != int(smoke[position_key])
            or fee_parser.read_uint(64) != int(smoke[position_key])
        ):
            raise ValueError("BankQueue: smoke fee body mismatch")

    payouts = [
        message
        for message in funding_transaction.get("out_msgs", [])
        if str(message.get("opcode", "")).lower() == f"0x{BANK_PAYOUT:08x}"
    ]
    if len(payouts) != 1:
        raise ValueError("BankQueue: smoke payout is missing or ambiguous")
    payout = payouts[0]
    if raw_address(str(payout.get("destination", ""))) != raw_address(
        str(smoke["first_wallet"])
    ) or int(payout.get("value", 0)) != int(smoke["payout_nano"]):
        raise ValueError("BankQueue: smoke payout destination or value mismatch")
    payout_parser = body_parser(payout)
    if (
        payout_parser.read_uint(32) != BANK_PAYOUT
        or payout_parser.read_uint(64) != int(smoke["funding_position_id"])
        or payout_parser.read_uint(64) != int(smoke["position_id"])
        or payout_parser.read_coins() != int(smoke["principal_nano"])
        or payout_parser.read_coins() != int(smoke["payout_nano"])
    ):
        raise ValueError("BankQueue: smoke payout body mismatch")
    return {
        "contract_address": smoke_address,
        "first_transaction": str(smoke["first_transaction"]),
        "funding_transaction": str(smoke["funding_transaction"]),
        "funding_masterchain_seqno": int(smoke["funding_masterchain_seqno"]),
        "position_id": int(smoke["position_id"]),
        "funding_position_id": int(smoke["funding_position_id"]),
        "payout_nano": int(smoke["payout_nano"]),
        "verified": True,
    }


async def duel_smoke_transaction(
    client: httpx.AsyncClient,
    manifest: dict[str, Any],
    transaction_hash: str,
    transaction_lt: int,
    masterchain_seqno: int,
) -> dict[str, Any]:
    response = await provider_get(
        client,
        "/api/v3/transactions",
        {"hash": transaction_hash, "limit": 2},
    )
    transactions = response.json().get("transactions", [])
    if len(transactions) != 1:
        raise ValueError("DuelEscrow: smoke transaction is missing or ambiguous")
    transaction = transactions[0]
    if not successful_transaction(transaction):
        raise ValueError("DuelEscrow: smoke transaction was not successful")
    if raw_address(str(transaction.get("account", ""))) != raw_address(
        manifest["address"]
    ):
        raise ValueError("DuelEscrow: smoke transaction account mismatch")
    if int(transaction.get("lt", 0)) != transaction_lt:
        raise ValueError("DuelEscrow: smoke transaction logical time mismatch")
    if int(transaction.get("mc_block_seqno", 0)) != masterchain_seqno:
        raise ValueError("DuelEscrow: smoke transaction finality mismatch")
    return transaction


async def verify_duel_smoke(
    client: httpx.AsyncClient, manifest: dict[str, Any]
) -> dict[str, Any] | None:
    smoke = manifest.get("verified_smoke")
    if not isinstance(smoke, dict):
        return None
    open_transaction = await duel_smoke_transaction(
        client,
        manifest,
        str(smoke["open_transaction"]),
        int(smoke["open_transaction_lt"]),
        int(smoke["open_masterchain_seqno"]),
    )
    cancel_transaction = await duel_smoke_transaction(
        client,
        manifest,
        str(smoke["cancel_transaction"]),
        int(smoke["cancel_transaction_lt"]),
        int(smoke["cancel_masterchain_seqno"]),
    )

    owner = raw_address(str(smoke["owner"]))
    open_message = open_transaction.get("in_msg") or {}
    if raw_address(str(open_message.get("source", ""))) != owner:
        raise ValueError("DuelEscrow: smoke open sender mismatch")
    if int(open_message.get("value", 0)) != int(smoke["stake_nano"]) + int(
        smoke["open_gas_nano"]
    ):
        raise ValueError("DuelEscrow: smoke open value mismatch")
    parser = body_parser(open_message)
    decoded_open = {
        "opcode": parser.read_uint(32),
        "query_id": parser.read_uint(64),
        "offer_id": parser.read_uint(64),
        "commitment": f"{parser.read_uint(256):064x}",
        "chance_bps": parser.read_uint(16),
        "total_pool_nano": parser.read_coins(),
        "expires_at": parser.read_uint(32),
        "counter_offer_id": parser.read_uint(64),
    }
    if decoded_open != {
        "opcode": DUEL_OPEN_OFFER,
        "query_id": int(smoke["offer_id"]),
        "offer_id": int(smoke["offer_id"]),
        "commitment": str(smoke["commitment_hex"]).lower(),
        "chance_bps": int(smoke["chance_bps"]),
        "total_pool_nano": int(smoke["total_pool_nano"]),
        "expires_at": int(smoke["expires_at"]),
        "counter_offer_id": 0,
    }:
        raise ValueError("DuelEscrow: smoke open body mismatch")

    cancel_message = cancel_transaction.get("in_msg") or {}
    if raw_address(str(cancel_message.get("source", ""))) != owner:
        raise ValueError("DuelEscrow: smoke cancel sender mismatch")
    if int(cancel_message.get("value", 0)) != int(smoke["cancel_gas_nano"]):
        raise ValueError("DuelEscrow: smoke cancel value mismatch")
    cancel_parser = body_parser(cancel_message)
    if (
        cancel_parser.read_uint(32) != DUEL_CANCEL_OFFER
        or cancel_parser.read_uint(64) != int(smoke["offer_id"])
        or cancel_parser.read_uint(64) != int(smoke["offer_id"])
    ):
        raise ValueError("DuelEscrow: smoke cancel body mismatch")

    refunds = [
        message
        for message in cancel_transaction.get("out_msgs", [])
        if str(message.get("opcode", "")).lower() == f"0x{DUEL_OFFER_REFUND:08x}"
    ]
    if len(refunds) != 1:
        raise ValueError("DuelEscrow: smoke refund is missing or ambiguous")
    refund = refunds[0]
    if raw_address(str(refund.get("destination", ""))) != owner or int(
        refund.get("value", 0)
    ) != int(smoke["refund_nano"]):
        raise ValueError("DuelEscrow: smoke refund destination or value mismatch")
    refund_parser = body_parser(refund)
    if (
        refund_parser.read_uint(32) != DUEL_OFFER_REFUND
        or refund_parser.read_uint(64) != int(smoke["offer_id"])
        or refund_parser.read_uint(64) != int(smoke["offer_id"])
        or refund_parser.read_uint(8) != int(smoke["refund_reason"])
    ):
        raise ValueError("DuelEscrow: smoke refund body mismatch")
    return {
        "offer_id": int(smoke["offer_id"]),
        "open_transaction": str(smoke["open_transaction"]),
        "cancel_transaction": str(smoke["cancel_transaction"]),
        "refund_nano": int(smoke["refund_nano"]),
        "verified": True,
    }


async def verify_duel_canary(
    client: httpx.AsyncClient, manifest: dict[str, Any]
) -> dict[str, Any] | None:
    canary = manifest.get("verified_canary")
    if not isinstance(canary, dict):
        return None
    first_wallet = raw_address(str(canary["first_wallet"]))
    second_wallet = raw_address(str(canary["second_wallet"]))
    if first_wallet == second_wallet:
        raise ValueError("DuelEscrow: canary wallets must be distinct")
    duel_id = int(canary["duel_id"])
    if not 0 < duel_id < 2**64:
        raise ValueError("DuelEscrow: canary duel id is invalid")
    if manifest["configuration"].get("version") == "1.3.0":
        boost_transaction = await duel_smoke_transaction(
            client,
            manifest,
            str(canary["boost_transaction"]),
            int(canary["boost_transaction_lt"]),
            int(canary["boost_masterchain_seqno"]),
        )
        boost_message = boost_transaction.get("in_msg") or {}
        if raw_address(str(boost_message.get("source", ""))) != first_wallet:
            raise ValueError("DuelEscrow: canary boost sender mismatch")
        boost_parser = body_parser(boost_message)
        decoded_boost = {
            "opcode": boost_parser.read_uint(32),
            "query_id": boost_parser.read_uint(64),
            "duel_id": boost_parser.read_uint(64),
            "offer_id": boost_parser.read_uint(64),
            "amount_nano": boost_parser.read_coins(),
            "expected_revision": boost_parser.read_uint(16),
            "min_chance_bps": boost_parser.read_uint(16),
            "valid_until": boost_parser.read_uint(32),
        }
        if decoded_boost != {
            "opcode": DUEL_BOOST,
            "query_id": int(canary["boost_query_id"]),
            "duel_id": duel_id,
            "offer_id": int(canary["first_offer_id"]),
            "amount_nano": int(canary["boost_nano"]),
            "expected_revision": 0,
            "min_chance_bps": int(canary["min_chance_bps"]),
            "valid_until": int(canary["boost_valid_until"]),
        }:
            raise ValueError("DuelEscrow: canary boost input mismatch")
        if int(boost_message.get("value", 0)) != int(canary["boost_nano"]) + int(
            canary["boost_gas_nano"]
        ):
            raise ValueError("DuelEscrow: canary boost value mismatch")
    transaction = await duel_smoke_transaction(
        client,
        manifest,
        str(canary["settlement_transaction"]),
        int(canary["settlement_transaction_lt"]),
        int(canary["masterchain_seqno"]),
    )
    incoming = transaction.get("in_msg") or {}
    if raw_address(str(incoming.get("source", ""))) not in {
        first_wallet,
        second_wallet,
    }:
        raise ValueError("DuelEscrow: canary settlement sender mismatch")
    parser = body_parser(incoming)
    if (
        parser.read_uint(32) != DUEL_REVEAL
        or parser.read_uint(64) != int(canary["query_id"])
        or parser.read_uint(64) != duel_id
    ):
        raise ValueError("DuelEscrow: canary settlement input mismatch")

    payouts = []
    for message in transaction.get("out_msgs", []):
        try:
            payout_parser = body_parser(message)
            if payout_parser.read_uint(32) != DUEL_PAYOUT:
                continue
            payout_parser.read_uint(64)
            payout_duel_id = payout_parser.read_uint(64)
        except Exception:
            continue
        if payout_duel_id == duel_id:
            payouts.append(message)
    if len(payouts) != 1:
        raise ValueError("DuelEscrow: canary payout proof is missing or ambiguous")
    if (
        raw_address(str(payouts[0].get("destination", "")))
        not in {
            first_wallet,
            second_wallet,
        }
        or int(payouts[0].get("value", 0)) <= 0
    ):
        raise ValueError("DuelEscrow: canary payout destination or value mismatch")
    return {
        "duel_id": duel_id,
        "boost_transaction": canary.get("boost_transaction"),
        "settlement_transaction": str(canary["settlement_transaction"]),
        "masterchain_seqno": int(canary["masterchain_seqno"]),
        "verified": True,
    }


async def verify_contract(
    client: httpx.AsyncClient,
    manifest_path: Path,
    *,
    network: str,
    network_id: int,
    require_smoke: bool,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    contract = str(manifest["contract"])
    address = str(manifest["address"])
    if manifest.get("network") != network:
        raise ValueError(f"{contract}: manifest network mismatch")
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
    configuration = manifest["configuration"]
    version = str(configuration.get("version", ""))
    duel_address_bound = contract == "DuelEscrow" and "network_id" in configuration
    # v1.4 appends `holderFeeSupported` to the DUEL contractConfig view.
    duel_holder_fee = duel_address_bound and not version.startswith("1.3")
    # The extended BANK contractConfig view has been stable since 1.3.0;
    # pinning the exact string made every later version fail the shape check.
    bank_extended = contract == "BankQueue" and version not in {"", "1.0.0", "1.1.0", "1.2.0"}
    expected_stack_size = (
        (9 if duel_holder_fee else 8)
        if duel_address_bound
        else 9
        if bank_extended
        else 7
        if contract == "BankQueue"
        else 5
    )
    if (
        not getter.get("ok")
        or result.get("exit_code") != 0
        or len(stack) != expected_stack_size
    ):
        raise ValueError(f"{contract}: contractConfig getter failed")
    if stack_address(stack[0]) != raw_address(str(configuration["owner"])):
        raise ValueError(f"{contract}: owner mismatch")
    if stack_address(stack[1]) != raw_address(str(configuration["treasury"])):
        raise ValueError(f"{contract}: treasury mismatch")
    if stack_number(stack[2]) != int(configuration["fee_bps"]):
        raise ValueError(f"{contract}: fee mismatch")
    if duel_address_bound:
        configured_network_id = int(configuration["network_id"])
        if configured_network_id != network_id or stack_number(stack[3]) != network_id:
            raise ValueError(f"{contract}: network domain mismatch")
        if (
            f"{stack_number(stack[4]):064x}"
            != str(configuration["invite_signer_public_key"]).lower()
        ):
            raise ValueError(f"{contract}: invite signer mismatch")
        if stack_address(stack[5]) != raw_address(address):
            raise ValueError(f"{contract}: self address mismatch")
        if bool(stack_number(stack[6])) != bool(configuration["paused"]):
            raise ValueError(f"{contract}: pause state mismatch")
        live_locked = stack_number(stack[7])
        # TVM returns -1 for true.
        if duel_holder_fee and stack_number(stack[8]) not in {-1, 1}:
            raise ValueError(f"{contract}: holder fee support flag mismatch")
        if duel_holder_fee and not bool(configuration.get("holder_fee_supported")):
            raise ValueError(f"{contract}: manifest does not declare holder fee support")
    else:
        if bool(stack_number(stack[3])) != bool(configuration["paused"]):
            raise ValueError(f"{contract}: pause state mismatch")
        if bank_extended:
            head_queue_index = stack_number(stack[4])
            next_queue_index = stack_number(stack[5])
            completed_positions = stack_number(stack[6])
            principal_limit = stack_number(stack[7])
            live_locked = stack_number(stack[8])
            if (
                "head_queue_index" in configuration
                and head_queue_index != int(configuration["head_queue_index"])
            ):
                raise ValueError("BankQueue: head queue index mismatch")
            if (
                "next_queue_index" in configuration
                and next_queue_index != int(configuration["next_queue_index"])
            ):
                raise ValueError("BankQueue: next queue index mismatch")
            if completed_positions != int(configuration["completed_positions"]):
                raise ValueError("BankQueue: completed position count mismatch")
            if principal_limit != int(configuration["principal_limit_nano"]):
                raise ValueError("BankQueue: principal limit mismatch")
        elif contract == "BankQueue" and "locked_nano" in configuration:
            live_locked = stack_number(stack[6])
        else:
            live_locked = 0

    live_balance = int(state.get("balance", 0))
    min_reserve = int(configuration.get("min_retained_reserve_nano", 0))
    validate_live_balance(
        contract,
        live_balance=live_balance,
        live_locked=live_locked,
        min_reserve=min_reserve,
    )

    if version in {"1.2.0", "1.3.0"}:
        admin_response = await provider_post(
            client,
            "/api/v2/runGetMethod",
            {"address": address, "method": "adminState", "stack": []},
        )
        admin_getter = admin_response.json()
        admin_result = admin_getter.get("result") or {}
        admin_stack = admin_result.get("stack") or []
        expected_admin_size = 7 if bank_extended else 5
        if (
            not admin_getter.get("ok")
            or admin_result.get("exit_code") != 0
            or len(admin_stack) != expected_admin_size
        ):
            raise ValueError(f"{contract}: adminState getter failed")
        common_admin_mismatch = (
            stack_address(admin_stack[0]) != raw_address(str(configuration["owner"]))
            or stack_address(admin_stack[1])
            != raw_address(str(configuration["treasury"]))
            or stack_number(admin_stack[2]) != int(configuration["fee_bps"])
            or bool(stack_number(admin_stack[3])) != bool(configuration["paused"])
        )
        bank_admin_mismatch = bank_extended and (
            stack_number(admin_stack[4]) != int(configuration["completed_positions"])
            or stack_number(admin_stack[5])
            != int(configuration["principal_limit_nano"])
            or stack_number(admin_stack[6]) != live_locked
        )
        duel_or_legacy_admin_mismatch = (
            not bank_extended and stack_number(admin_stack[4]) != live_locked
        )
        if (
            common_admin_mismatch
            or bank_admin_mismatch
            or duel_or_legacy_admin_mismatch
        ):
            raise ValueError(f"{contract}: adminState mismatch")

    result = {
        "contract": contract,
        "address": address,
        "active": True,
        "local_build_matches": True,
        "code_hash": expected_code,
        "initial_data_hash": expected_data,
        "initial_data_hash_matches": True,
        "configuration_matches": True,
        "live_balance_nano": live_balance,
        "live_locked_nano": live_locked,
        "min_retained_reserve_nano": min_reserve,
        "reserve_covered": True,
        "deployment_transaction": str(manifest["deploy_transaction"]),
        "deployment_lt": int(manifest["deploy_transaction_lt"]),
        "masterchain_seqno": int(transaction["mc_block_seqno"]),
        "verified": True,
    }
    if contract == "BankQueue":
        result["smoke"] = await verify_bank_smoke(client, manifest)
    elif contract == "DuelEscrow":
        result["smoke"] = await verify_duel_smoke(client, manifest)
        result["canary"] = await verify_duel_canary(client, manifest)
    if require_smoke and result.get("smoke") is None:
        raise ValueError(f"{contract}: finalized smoke proof is required")
    if (
        network == "mainnet"
        and contract == "DuelEscrow"
        and result.get("canary") is None
    ):
        raise ValueError("DuelEscrow: finalized two-wallet canary proof is required")
    return result


async def provider_get(
    client: httpx.AsyncClient, path: str, params: dict[str, Any]
) -> httpx.Response:
    for attempt in range(4):
        response = await client.get(path, params=params)
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
        response = await client.post(path, json=payload)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        await asyncio.sleep(attempt + 1)
    response.raise_for_status()
    raise AssertionError("unreachable")


async def run(selected: list[str], network: str, require_smoke: bool) -> int:
    network_config = NETWORKS[network]
    manifest_dir = ROOT / "deployments" / network
    headers = {}
    api_key = os.getenv("LOOP_TONCENTER_API_KEY") or os.getenv(
        str(network_config["api_key_env"])
    )
    if api_key:
        headers["X-API-Key"] = api_key
    try:
        async with httpx.AsyncClient(
            base_url=str(network_config["toncenter"]),
            headers=headers,
            timeout=20,
        ) as client:
            results = [
                await verify_contract(
                    client,
                    manifest_dir / f"{name}.json",
                    network=network,
                    network_id=int(str(network_config["id"])),
                    require_smoke=require_smoke,
                )
                for name in selected
            ]
    except (FileNotFoundError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
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
    parser.add_argument("--network", choices=tuple(NETWORKS), default="testnet")
    parser.add_argument(
        "--require-smoke",
        action="store_true",
        help="require a finalized open/settle or open/cancel proof in every manifest",
    )
    args = parser.parse_args()
    selected = args.contracts or ["bank", "duel"]
    require_smoke = args.require_smoke or args.network == "mainnet"
    raise SystemExit(asyncio.run(run(selected, args.network, require_smoke)))


if __name__ == "__main__":
    main()
