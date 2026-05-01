#!/usr/bin/env python3
"""
Check production API health from the CLI.

Usage:
  python scripts/check_prod_status.py
  python scripts/check_prod_status.py --base-url https://guild-os-two.vercel.app
  python scripts/check_prod_status.py --timeout 8
"""

from __future__ import annotations

import argparse
import sys
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
    if status != "ok":
        status_label = status or "missing"
        return False, f"status={status_label}"

    return True, "status=ok"


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
    return parser.parse_args(argv)


def run_check(base_url: str, timeout_s: float) -> int:
    url = build_health_url(base_url)
    try:
        response = httpx.get(url, timeout=timeout_s)
    except httpx.HTTPError as exc:
        print(f"DOWN: {url} ({exc})")
        return 1

    if response.status_code != 200:
        print(f"DOWN: {url} (http {response.status_code})")
        return 1

    try:
        payload = response.json()
    except ValueError:
        print(f"DOWN: {url} (invalid JSON payload)")
        return 1

    healthy, reason = evaluate_health_payload(payload)
    if not healthy:
        print(f"DOWN: {url} ({reason})")
        return 1

    version = payload.get("version", "unknown")
    print(f"UP: {url} ({reason}, version={version})")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    return run_check(args.base_url, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
