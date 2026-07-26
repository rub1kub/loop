import base64
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load_runner() -> ModuleType:
    path = ROOT / "scripts" / "run-bank-canary.py"
    spec = importlib.util.spec_from_file_location("run_bank_canary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bank_canary_hash_normalization_accepts_chain_formats() -> None:
    runner = load_runner()
    raw = bytes(range(32))
    expected = raw.hex()
    assert runner.normalize_hash(expected) == expected
    assert runner.normalize_hash(base64.b64encode(raw).decode()) == expected


def test_bank_canary_requires_distinct_preexisting_wallets() -> None:
    runner = load_runner()
    aliases = ("first", "second")
    runner.require_wallets(
        {
            "first": {"address": "0:first"},
            "second": {"address": "0:second"},
        },
        aliases,
    )
    with pytest.raises(SystemExit, match="distinct"):
        runner.require_wallets(
            {
                "first": {"address": "0:same"},
                "second": {"address": "0:same"},
            },
            aliases,
        )


def test_bank_canary_finality_rejects_failed_transaction_shape() -> None:
    runner = load_runner()
    assert runner.successful_transaction(
        {
            "description": {
                "aborted": False,
                "compute_ph": {"success": True},
                "action": {"success": True},
            }
        }
    )
    assert not runner.successful_transaction(
        {
            "description": {
                "aborted": True,
                "compute_ph": {"success": True},
                "action": {"success": True},
            }
        }
    )
