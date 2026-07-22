#!/usr/bin/env python3
"""Fail-closed health check for production DUEL projection metrics."""

from __future__ import annotations

import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

METRIC_LINE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\s+"
    r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[+-]Inf|NaN)$"
)
REQUIRED_METRICS = (
    "loop_duel_worker_healthy",
    "loop_duel_worker_heartbeat_age_seconds",
    "loop_duel_overdue_reveals",
    "loop_duel_stale_funding",
    "loop_duel_unbound_direct",
    "loop_duel_canary_success",
    "loop_duel_canary_age_seconds",
)


class DuelHealthError(RuntimeError):
    """Raised when a monitored DUEL invariant is not healthy."""


def parse_metrics(payload: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in payload.splitlines():
        match = METRIC_LINE.fullmatch(line.strip())
        if match:
            metrics[match.group("name")] = float(match.group("value"))
    return metrics


def evaluate_metrics(
    metrics: dict[str, float], *, require_canary: bool, canary_max_age: float
) -> dict[str, float | bool | None]:
    missing = [name for name in REQUIRED_METRICS if name not in metrics]
    if missing:
        raise DuelHealthError(f"missing metrics: {', '.join(missing)}")

    failures: list[str] = []
    if metrics["loop_duel_worker_healthy"] != 1:
        failures.append("projection worker heartbeat is stale")
    if metrics["loop_duel_overdue_reveals"] > 0:
        failures.append("one or more reveals are overdue")
    if metrics["loop_duel_stale_funding"] > 0:
        failures.append("one or more funding intents are stale")
    if metrics["loop_duel_unbound_direct"] > 0:
        failures.append("one or more direct matches are unbound")
    if require_canary and (
        metrics["loop_duel_canary_success"] != 1
        or not math.isfinite(metrics["loop_duel_canary_age_seconds"])
        or metrics["loop_duel_canary_age_seconds"] > canary_max_age
    ):
        failures.append("two-wallet canary is missing, failed or stale")
    if failures:
        raise DuelHealthError("; ".join(failures))

    canary_age = metrics["loop_duel_canary_age_seconds"]
    return {
        "healthy": True,
        "worker_heartbeat_age_seconds": round(
            metrics["loop_duel_worker_heartbeat_age_seconds"], 3
        ),
        "canary_required": require_canary,
        "canary_success": metrics["loop_duel_canary_success"] == 1,
        "canary_age_seconds": canary_age if math.isfinite(canary_age) else None,
    }


def fetch_metrics(origin: str, token: str) -> str:
    if not token:
        raise DuelHealthError("LOOP_METRICS_TOKEN is required")
    request = urllib.request.Request(
        f"{origin.rstrip('/')}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise DuelHealthError(f"metrics endpoint returned HTTP {response.status}")
            return response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DuelHealthError(f"metrics endpoint is unavailable: {exc}") from exc


def env_flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    try:
        max_age = float(os.getenv("LOOP_DUEL_CANARY_MAX_AGE_SECONDS", "7200"))
        if not math.isfinite(max_age) or max_age <= 0:
            raise DuelHealthError("LOOP_DUEL_CANARY_MAX_AGE_SECONDS must be positive")
        payload = fetch_metrics(
            os.getenv("LOOP_DUEL_METRICS_ORIGIN", "http://127.0.0.1:8000"),
            os.getenv("LOOP_METRICS_TOKEN", ""),
        )
        result = evaluate_metrics(
            parse_metrics(payload),
            require_canary=env_flag("LOOP_REQUIRE_DUEL_CANARY"),
            canary_max_age=max_age,
        )
    except (DuelHealthError, ValueError) as exc:
        print(json.dumps({"healthy": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
