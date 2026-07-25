#!/usr/bin/env python3
"""Enforce explicit line and branch thresholds for an LCOV contract report."""

from __future__ import annotations

import argparse
from pathlib import Path


def totals(report: Path) -> tuple[int, int, int, int]:
    lines_found = lines_hit = branches_found = branches_hit = 0
    for raw_line in report.read_text().splitlines():
        key, separator, value = raw_line.partition(":")
        if not separator:
            continue
        if key == "LF":
            lines_found += int(value)
        elif key == "LH":
            lines_hit += int(value)
        elif key == "BRF":
            branches_found += int(value)
        elif key == "BRH":
            branches_hit += int(value)
    if lines_found <= 0 or branches_found <= 0:
        raise ValueError("LCOV report has no line or branch totals")
    return lines_hit, lines_found, branches_hit, branches_found


def percentage(hit: int, found: int) -> float:
    return hit * 100 / found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--minimum-lines", type=float, required=True)
    parser.add_argument("--minimum-branches", type=float, required=True)
    args = parser.parse_args()

    lines_hit, lines_found, branches_hit, branches_found = totals(args.report)
    line_percent = percentage(lines_hit, lines_found)
    branch_percent = percentage(branches_hit, branches_found)
    print(
        f"contract coverage: lines {lines_hit}/{lines_found} ({line_percent:.2f}%), "
        f"branches {branches_hit}/{branches_found} ({branch_percent:.2f}%)"
    )
    failures = []
    if line_percent < args.minimum_lines:
        failures.append(f"line coverage is below {args.minimum_lines:.2f}%")
    if branch_percent < args.minimum_branches:
        failures.append(f"branch coverage is below {args.minimum_branches:.2f}%")
    if failures:
        raise SystemExit("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
