#!/usr/bin/env python3
"""
Set or reset an officer's password directly in the database.

Usage:
  DATABASE_URL=postgresql://... python scripts/set_officer_password.py officer@email.com

Prompts for the password interactively (hidden input).
Useful for bootstrapping the first officer before the app is deployed,
or resetting a password without going through the UI.
"""

from __future__ import annotations

import getpass
import os
import sys

import bcrypt
import psycopg2


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <officer-email>", file=sys.stderr)
        sys.exit(1)

    email = sys.argv[1].strip().lower()

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("error: set DATABASE_URL", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass("New password (min 8 chars): ")
    if len(password) < 8:
        print("error: password must be at least 8 characters", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("error: passwords do not match", file=sys.stderr)
        sys.exit(1)

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET password_hash = %s WHERE email = %s AND role = 'officer' RETURNING id",
                (hashed, email),
            )
            row = cur.fetchone()
            if not row:
                print(f"error: no officer found with email '{email}'", file=sys.stderr)
                conn.rollback()
                sys.exit(1)
            conn.commit()
            print(f"Password set for officer {email} (id={row[0]})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
