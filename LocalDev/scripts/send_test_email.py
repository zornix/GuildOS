#!/usr/bin/env python3
"""Send one real email through the app's own SMTP adapter, to prove the wiring.

Usage (from LocalDev/):
  python3 scripts/send_test_email.py someone@example.com
  npm run email:test -- someone@example.com

Config comes from api/config.py settings (which reads LocalDev/.env), so this
sends exactly what the outbox drain would send. Refuses to run unless
EMAIL_DELIVERY_MODE=smtp, so dry_run stays the safe default.
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from api.config import settings  # noqa: E402
from api.platform.email import send_email  # noqa: E402

SUBJECT = "GuildOS test email"
BODY = "This is a test from GuildOS. If you got it, SMTP is wired up correctly."


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    (to,) = argv

    if settings.EMAIL_DELIVERY_MODE != "smtp":
        print(
            f"EMAIL_DELIVERY_MODE={settings.EMAIL_DELIVERY_MODE!r} — refusing to "
            "send. Set EMAIL_DELIVERY_MODE=smtp in LocalDev/.env first."
        )
        return 1

    try:
        send_email(to, SUBJECT, BODY)
    except Exception as exc:  # RuntimeError from _require, SMTP errors, …
        print(f"{type(exc).__name__}: {exc}")
        return 1

    print(f"sent to {to} from {settings.EMAIL_FROM} via {settings.SMTP_HOST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
