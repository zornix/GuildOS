#!/usr/bin/env python3
"""Send one real SMS through the app's own Twilio adapter, to prove the wiring.

Usage (from LocalDev/):
  python3 scripts/send_test_sms.py +15555550123 "hello from GuildOS"
  npm run sms:test -- +15555550123 "hello from GuildOS"

Config comes from api/config.py settings (which reads LocalDev/.env), so this
sends exactly what the outbox drain would send. Refuses to run unless
MESSAGE_DELIVERY_MODE=twilio, so dry_run stays the safe default.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

import httpx  # noqa: E402

from api.config import settings  # noqa: E402
from api.announcements.services.twilio_client import send_sms  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    to, body = argv

    if settings.MESSAGE_DELIVERY_MODE != "twilio":
        print(
            f"MESSAGE_DELIVERY_MODE={settings.MESSAGE_DELIVERY_MODE!r} — refusing to "
            "send. Set MESSAGE_DELIVERY_MODE=twilio in LocalDev/.env first."
        )
        return 1

    try:
        sid = send_sms(to, body)
    except httpx.HTTPStatusError as exc:
        print(f"Twilio {exc.response.status_code}: {exc.response.text}")
        return 1
    except Exception as exc:  # RuntimeError from _require, network errors, …
        print(f"{type(exc).__name__}: {exc}")
        return 1

    sender = settings.TWILIO_MESSAGING_SERVICE_SID or settings.TWILIO_FROM_NUMBER
    print(f"sent to {to} from {sender} — message SID {sid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
