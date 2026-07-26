#!/usr/bin/env python3
"""Build a deterministic, secret-free contract audit package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
FILES = (
    "Acton.toml",
    "Makefile",
    "contracts/gas-baseline.json",
    "deployments/mainnet/README.md",
    "deployments/mainnet/release.example.json",
    "docs/audits/mainnet-audit-scope.md",
    "docs/contracts.md",
    "docs/security.md",
    "docs/testing.md",
)
GLOBS = (
    "contracts/**/*.tolk",
    "tests/**/*.tolk",
    "scripts/*mainnet*.tolk",
    "scripts/bank_canary/*.tolk",
    "scripts/canary/*.tolk",
    "scripts/check-contract-coverage.py",
    "scripts/check-mainnet-readiness.py",
    "scripts/run-bank-canary.py",
    "scripts/run-duel-canary.py",
    "scripts/verify-contracts.py",
)


def command(*parts: str) -> str:
    result = subprocess.run(
        list(parts),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(result.stderr.strip() or f"{parts[0]} failed")
    return result.stdout.strip()


def selected_files() -> list[Path]:
    files = {ROOT / name for name in FILES}
    for pattern in GLOBS:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise SystemExit(f"audit input is missing: {missing[0].relative_to(ROOT)}")
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(files: list[Path], *, commit: str, dirty: bool) -> dict[str, Any]:
    doctor = command("acton", "doctor", "--color", "never")
    tolk_match = re.search(r"^tolk\.version:\s+(\S+)", doctor, re.MULTILINE)
    if tolk_match is None:
        raise SystemExit("Acton did not report its bundled Tolk version")
    build_hashes = {}
    for contract in ("BankQueue", "DuelEscrow"):
        build = ROOT / "build" / f"{contract}.json"
        if not build.is_file():
            raise SystemExit("run `acton build` before creating the audit package")
        payload = json.loads(build.read_text())
        build_hashes[contract] = str(payload["hash"]).lower()
    return {
        "schema": 1,
        "project": "LOOP",
        "commit": commit,
        "dirty": dirty,
        "toolchain": {
            "acton": command("acton", "--version"),
            "tolk": tolk_match.group(1),
        },
        "contract_build_hashes": build_hashes,
        "files": {
            path.relative_to(ROOT).as_posix(): sha256(path.read_bytes())
            for path in files
        },
    }


def add_bytes(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()

    commit = command("git", "rev-parse", "HEAD")
    dirty = bool(command("git", "status", "--porcelain"))
    if dirty and not args.allow_dirty:
        raise SystemExit("audit package requires a clean worktree")
    files = selected_files()
    evidence = manifest(files, commit=commit, dirty=dirty)
    output = args.output or ROOT / "build" / f"loop-mainnet-audit-{commit}.zip"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for path in files:
            add_bytes(
                archive,
                path.relative_to(ROOT).as_posix(),
                path.read_bytes(),
            )
        add_bytes(
            archive,
            "AUDIT-MANIFEST.json",
            (
                json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n"
            ).encode(),
        )
    print(
        json.dumps(
            {
                "path": str(output),
                "sha256": sha256(output.read_bytes()),
                "commit": commit,
                "dirty": dirty,
                "files": len(files),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
