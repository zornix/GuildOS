#!/usr/bin/env python3
"""
Check production API health from the CLI.

Usage:
  python scripts/check_prod_status.py
  python scripts/check_prod_status.py --base-url https://guild-os-two.vercel.app
  python scripts/check_prod_status.py --timeout 8
  python scripts/check_prod_status.py --max-attempts 5 --backoff 0.3
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://guild-os-two.vercel.app"
HEALTH_PATH = "/api/health"


def build_health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{HEALTH_PATH}"


def evaluate_health_payload(payload: Any) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "response was not a JSON object"

    status = str(payload.get("status", "")).strip().lower()
    if status not in ("ok", "degraded"):
        status_label = status or "missing"
        return False, f"status={status_label}"

    checks = payload.get("checks")
    if not isinstance(checks, dict):
        return False, "missing or invalid checks"

    db = str(checks.get("database", "")).strip().lower()
    if db != "ok":
        db_label = db or "missing"
        return False, f"checks.database={db_label}"

    return True, f"status={status} checks.database=ok"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check production API health.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of deployment (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts for transient HTTP/DB failures (default: 3)",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=0.25,
        help="Initial backoff in seconds between retries, doubled each time (default: 0.25)",
    )
    return parser.parse_args(argv)


def _http_status_retriable(code: int) -> bool:
    return code in (408, 429) or code >= 500


def run_check(
    base_url: str,
    timeout_s: float,
    *,
    max_attempts: int = 3,
    backoff_sec: float = 0.25,
) -> int:
    url = build_health_url(base_url)
    if max_attempts < 1:
        print("DOWN: invalid max_attempts", file=sys.stderr)
        return 1

    for attempt in range(max_attempts):
        try:
            response = httpx.get(url, timeout=timeout_s)
        except httpx.HTTPError as exc:
            if attempt < max_attempts - 1:
                time.sleep(backoff_sec * (2**attempt))
                continue
            print(f"DOWN: {url} ({exc})")
            return 1

        if response.status_code != 200:
            if _http_status_retriable(response.status_code) and attempt < max_attempts - 1:
                time.sleep(backoff_sec * (2**attempt))
                continue
            print(f"DOWN: {url} (http {response.status_code})")
            return 1

        try:
            payload = response.json()
        except ValueError:
            print(f"DOWN: {url} (invalid JSON payload)")
            return 1

        healthy, reason = evaluate_health_payload(payload)
        if healthy:
            version = payload.get("version", "unknown")
            label = "WARN" if payload.get("status") == "degraded" else "UP"
            print(f"{label}: {url} ({reason}, version={version})")
            return 0

        if attempt < max_attempts - 1:
            time.sleep(backoff_sec * (2**attempt))
            continue

        print(f"DOWN: {url} ({reason})")
        return 1

    print(f"DOWN: {url} (exhausted retries)")
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    return run_check(
        args.base_url,
        args.timeout,
        max_attempts=args.max_attempts,
        backoff_sec=args.backoff,
    )


if __name__ == "__main__":
    raise SystemExit(main())
